"""Real HTTP contract / bounded C++ transport tests; does not access hardware."""
import argparse
import http.client
import json
from pathlib import Path
import socket
import struct
import subprocess
import threading
import time
from server import FrameHub, handler_type, ThreadingHTTPServer
from raw_protocol import RawHub, pack


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sender', type=Path)
    parser.add_argument('--wait-test', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    hub = RawHub(stale_seconds=.35)
    server = ThreadingHTTPServer(('127.0.0.1',0), handler_type(FrameHub(), hub))
    server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def request(method,path,body=None):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        try:
            conn.request(method,path,body=body); reply=conn.getresponse();return reply.status,reply.read()
        finally:
            conn.close()
    meta=dict(schema_version=1,stream_id='test-1',frame_id='9007199254740993',timestamp_us='9007199254740993',
        timestamp_basis='ps_dma_done_monotonic',source='demo',pixel_format='RGB565LE',width=2,height=1,stride_bytes=6)
    pixels=b'\x00\xf8\xe0\x07\xaa\xbb' # red, green and stride padding
    checks=[]
    try:
        assert request('GET','/api/frame')[0]==503
        assert request('POST','/api/frame',b'bad')[0]==400
        assert request('POST','/api/frame',pack(dict(meta,pixel_format='YUYV'),pixels))[0]==400
        assert request('POST','/api/frame',pack(meta,pixels[:-1]))[0]==400
        assert request('POST','/api/frame',struct.pack('!I',999999)+b'a')[0]==400
        checks += ['missing/invalid frame is not displayed','format/stride/truncation limits']
        assert request('POST','/api/frame',pack(meta,pixels))[0]==204
        persistent=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        persistent.request('GET','/api/status');reply=persistent.getresponse();assert reply.status==200
        reply.read();first_socket=persistent.sock
        persistent.request('GET','/api/status');reply=persistent.getresponse();reply.read()
        assert reply.status==200 and persistent.sock is first_socket
        persistent.close()
        checks+=['HTTP keep-alive reuses receive connection']
        code,packet=request('GET','/api/frame');assert code==200
        n=struct.unpack_from('!I',packet)[0];shown=json.loads(packet[4:4+n])
        assert packet[4+n:]==pixels and shown['frame_id']=='9007199254740993'
        assert shown['models']=={'face':'not_connected','voice':'not_connected'} and shown['faces']==[]
        assert request('GET','/api/frame?after='+str(shown['revision']))[0]==204
        assert request('POST','/api/frame',pack(meta,pixels))[0]==409
        checks+=['pixel identity with padded stride and uint64 ids','no model dependency','unchanged frame 204 / stale sequence rejected']
        result=dict(schema_version=1,stream_id=meta['stream_id'],frame_id=meta['frame_id'],models={'face':'ready','voice':'ready'},
            faces=[dict(box=[.1,.1,.3,.4],name='<script>test</script>',confidence=.9)],
            subtitles=[dict(start_us='9007199254740992',end_us='9007199254740994',text='同步测试字幕'),
                       dict(start_us='0',end_us='1',text='expired')])
        assert request('POST','/api/results',json.dumps(dict(result,frame_id='1')).encode())[0]==409
        assert request('POST','/api/results',json.dumps(result).encode())[0]==204
        code,packet=request('GET','/api/frame');n=struct.unpack_from('!I',packet)[0];shown=json.loads(packet[4:4+n])
        assert len(shown['subtitles'])==1 and shown['subtitles'][0]['text']=='同步测试字幕'
        assert packet[4+n:]==pixels and shown['faces'][0]['confidence']==.9
        bad=dict(result,faces=[dict(box=[.9,.1,.5,.1],name='bad',confidence=.9)])
        assert request('POST','/api/results',json.dumps(bad).encode())[0]==400
        assert request('POST','/api/results',json.dumps(dict(result,faces=[dict(box=[0,0,1,1],name='bad',confidence=float('nan'))])).encode())[0]==400
        checks+=['exact frame/result pairing','subtitle interval filtering','invalid box / NaN rejected']
        next_meta=dict(meta,frame_id='9007199254740994',timestamp_us='9007199254740994')
        assert request('POST','/api/frame',pack(next_meta,pixels))[0]==204
        assert request('POST','/api/results',json.dumps(result).encode())[0]==409
        code,packet=request('GET','/api/frame');n=struct.unpack_from('!I',packet)[0];shown=json.loads(packet[4:4+n])
        assert shown['faces']==[] and shown['subtitles']==[]
        checks+=['old results never leak into next frame']
        atomic=dict(next_meta,frame_id='9007199254740995',timestamp_us='9007199254740995')
        atomic.update(dict(result,frame_id=atomic['frame_id']))
        assert request('POST','/api/frame',pack(atomic,pixels))[0]==204
        code,packet=request('GET','/api/frame');n=struct.unpack_from('!I',packet)[0];shown=json.loads(packet[4:4+n])
        assert shown['faces'][0]['confidence']==.9 and shown['subtitles']==[]
        checks+=['atomic CPU frame/result envelope']
        assert request('POST','/api/frame',pack(dict(meta,stream_id='restarted',frame_id='0'),pixels))[0]==204
        assert request('POST','/api/frame',pack(next_meta,pixels))[0]==409
        time.sleep(.4);assert request('GET','/api/frame')[0]==503
        checks+=['stream restart isolates prior session','stale stream suppression']
        if args.sender:
            started=time.monotonic()
            done=subprocess.run([str(args.sender),'127.0.0.1',str(server.server_port),'1'],capture_output=True,text=True,timeout=3)
            assert done.returncode==0 and 'sent=0 ' not in done.stdout and time.monotonic()-started<3
            checks+=['real C++ raw transport HTTP encoding']
            # A receiver that accepts but never answers cannot cause an unbounded worker/queue.
            stall=socket.socket();stall.bind(('127.0.0.1',0));stall.listen(20)
            connections=[];halt=threading.Event()
            def silent():
                stall.settimeout(.1)
                while not halt.is_set():
                    try: connections.append(stall.accept()[0])
                    except socket.timeout: pass
            sleeper=threading.Thread(target=silent,daemon=True);sleeper.start()
            try:
                started=time.monotonic()
                done=subprocess.run([str(args.sender),'127.0.0.1',str(stall.getsockname()[1]),'1'],capture_output=True,text=True,timeout=3)
                values=dict(v.split('=') for v in done.stdout.split())
                assert done.returncode==0 and int(values['failed'])>0 and int(values['replaced'])>0 and time.monotonic()-started<2.5
                checks+=['silent receiver bounded shutdown / latest frame replacement']
            finally:
                halt.set();sleeper.join(1);stall.close()
                for conn in connections: conn.close()
        if args.wait_test:
            done=subprocess.run([str(args.wait_test)],capture_output=True,text=True,timeout=2)
            assert done.returncode==0 and 'PASS' in done.stdout
            checks+=['PS capture wait states and bounded polling']
        report=dict(passed=True,checks=checks,board_accessed=False,camera_opened=False,models_loaded=False)
        args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        server.shutdown();server.server_close();thread.join(2)


if __name__=='__main__':main()
