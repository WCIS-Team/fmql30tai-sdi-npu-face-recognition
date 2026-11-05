"""Decode a local video, send raw frames over one binary SSH channel, infer.

latest: pace the video, keep one latest local frame, send only on board credit.
all: process every decoded frame in order, at the board's processing rate.
Neither mode drives SDI pins or bypasses the PS transport/upload adapter.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]


class VideoReader:
    def __init__(self,cv2,path,seconds):
        self.cv2=cv2;self.capture=cv2.VideoCapture(str(path))
        if not self.capture.isOpened():raise ValueError('Cannot open video: '+str(path))
        fps=float(self.capture.get(cv2.CAP_PROP_FPS))
        self.fps=fps if math.isfinite(fps) and fps>0 else 30.0
        self.fps_fallback=self.fps!=fps
        self.width=int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH));self.height=int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.seconds=seconds;self.index=0;self.decoded=0;self.last_pts=-1
        self.timestamp_fallbacks=0;self.decode_total_ms=0.0
    def read(self):
        started=time.monotonic();ok,pixels=self.capture.read();decoded_at=time.monotonic()
        if not ok:
            if not self.index:raise ValueError('Video has no decodable frames')
            return None
        self.index+=1
        pos=float(self.capture.get(self.cv2.CAP_PROP_POS_MSEC))
        pts=int(round(pos*1000)) if math.isfinite(pos) and pos>=0 else -1
        if pts<0 or (self.index>1 and pts<=self.last_pts):
            pts=max(self.last_pts+1,round((self.index-1)/self.fps*1000000));self.timestamp_fallbacks+=1
        if self.seconds and pts>=self.seconds*1000000:return None
        self.last_pts=pts;self.decoded+=1;decode_ms=(decoded_at-started)*1000;self.decode_total_ms+=decode_ms
        return dict(sequence=self.index,pts_us=pts,pixels=pixels,decoded_at=decoded_at,decode_ms=decode_ms)
    def close(self):self.capture.release()


class LatestFrames:
    def __init__(self,reader,stop):
        self.reader,self.stop=reader,stop;self.condition=threading.Condition()
        self.slot=None;self.done=False;self.error=None
        self.thread=threading.Thread(target=self.run,name='video-decoder',daemon=True)
    def start(self):self.thread.start()
    def run(self):
        started=time.monotonic();first_pts=None
        try:
            while not self.stop.is_set():
                frame=self.reader.read()
                if frame is None:break
                if first_pts is None:first_pts=frame['pts_us']
                due=started+(frame['pts_us']-first_pts)/1000000
                if self.stop.wait(max(0,due-time.monotonic())):break
                with self.condition:
                    self.slot=frame;self.condition.notify_all()
        except BaseException as error:self.error=error
        finally:
            self.reader.close()
            with self.condition:self.done=True;self.condition.notify_all()
    def take(self):
        with self.condition:
            while self.slot is None and not self.done and not self.stop.is_set():self.condition.wait(.25)
            if self.error:raise self.error
            frame=self.slot;self.slot=None
            return frame
    def close(self):
        self.stop.set();self.thread.join(timeout=5)
        if self.thread.is_alive():raise RuntimeError('Local video decoder did not stop')


def pack_frame(pixels,pixel_format,np):
    if pixels.dtype!=np.uint8 or pixels.ndim!=3 or pixels.shape[2]!=3:
        raise ValueError('Expected decoded uint8 BGR pixels')
    h,w=pixels.shape[:2];bpp=2 if pixel_format=='RGB565LE' else 4;pitch=(w*bpp+7)//8*8
    if pixel_format=='BGRX8':
        packed=np.zeros((h,pitch//4,4),np.uint8);packed[:,:w,:3]=pixels
    else:
        p=pixels.astype(np.uint16);packed=np.zeros((h,pitch//2),'<u2')
        packed[:,:w]=((p[:,:,2]>>3)<<11)|((p[:,:,1]>>2)<<5)|(p[:,:,0]>>3)
    return packed.tobytes(),w,h,pitch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video',type=Path)
    parser.add_argument('--mode',choices=('latest','all'),default='latest')
    parser.add_argument('--backend',choices=('face','jpeg'),default='face')
    parser.add_argument('--jpeg-replay',type=int,default=0,help='After upload, benchmark resident DDR frames without a 20 FPS cap')
    parser.add_argument('--pixel-format',choices=('RGB565LE','BGRX8'),default='RGB565LE')
    parser.add_argument('--max-frames',type=int,default=30)
    parser.add_argument('--seconds',type=float,default=0,help='Limit source-video duration, 0 reads to EOF')
    parser.add_argument('--out',type=Path)
    parser.add_argument('--runtime-config',type=Path,default=ROOT/'ps_app/configs/video-stream-local.json')
    args=parser.parse_args()
    if not 0<=args.jpeg_replay<=300 or (args.jpeg_replay and args.backend!='jpeg'):
        parser.error('JPEG replay requires --backend jpeg and 0..300 iterations')
    if not 1<=args.max_frames<=300 or not math.isfinite(args.seconds) or args.seconds<0:
        parser.error('Use 1..300 transmitted frames and a nonnegative source duration')
    cfg=json.loads(args.runtime_config.read_text(encoding='utf-8')) if args.runtime_config.is_file() else {}
    args.video=args.video or (Path(cfg['default_video']) if cfg.get('default_video') else None)
    if args.video is None or not args.video.is_file():parser.error('Provide a local --video file')
    sys.stdout.reconfigure(encoding='utf-8')
    cache=Path('D:/yzd/tmp/pl-jpeg-board-20261016/pycache' if args.backend=='jpeg' else 'D:/yzd/tmp/face-video-input/cache')
    cache.mkdir(parents=True,exist_ok=True)
    sys.pycache_prefix=str(cache)
    try:
        import cv2
        import numpy as np
    except ImportError as error:
        python=Path(cfg.get('python_executable',''))
        if python.is_file() and python.resolve()!=Path(sys.executable).resolve():
            os.environ['PYTHONPYCACHEPREFIX']=str(cache)
            child=subprocess.Popen([str(python),str(Path(__file__).resolve()),*sys.argv[1:]],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
            def forward_stop(signum,frame):
                if child.poll() is None:
                    child.send_signal(signal.CTRL_BREAK_EVENT if os.name=='nt' else signal.SIGINT)
            control_signals=(signal.SIGINT,signal.SIGBREAK) if os.name=='nt' else (signal.SIGINT,)
            signals={sig:signal.signal(sig,forward_stop) for sig in control_signals}
            try:raise SystemExit(child.wait())
            finally:
                for sig,handler in signals.items():signal.signal(sig,handler)
        raise RuntimeError('Install opencv-python-headless in a private local environment or configure python_executable') from error
    sys.path.insert(0,str(ROOT/'npu_photo'))
    from frame_stream_protocol import encode_header,validate_header
    from ssh_transport import board_connection
    run_root=Path('D:/yzd/tmp/pl-jpeg-board-20261016/runs' if args.backend=='jpeg' else 'D:/yzd/tmp/face-video-input/runs')
    out=args.out or run_root/uuid.uuid4().hex[:12]
    out.mkdir(parents=True,exist_ok=False)
    sys.pycache_prefix=str(out/'pycache')
    reader=VideoReader(cv2,args.video,args.seconds)
    probe=dict(version=1,kind='frame',stream_id='0'*32,sequence=1,pts_us=0,
               pixel_format=args.pixel_format,width=reader.width,height=reader.height,
               pitch_bytes=(reader.width*(2 if args.pixel_format=='RGB565LE' else 4)+7)//8*8,sha256='0'*64)
    validate_header(probe,probe['pitch_bytes']*probe['height'])
    if args.backend=='jpeg' and (reader.width,reader.height)!=(1920,1080):
        reader.close();parser.error('JPEG board firmware requires native 1920x1080; input is never resized')
    stop=threading.Event()
    stop_signals=(signal.SIGINT,signal.SIGBREAK) if os.name=='nt' else (signal.SIGINT,)
    old={sig:signal.signal(sig,lambda s,f:stop.set()) for sig in stop_signals}
    stream_id=uuid.uuid4().hex;source=None;channel=None;stderr_thread=None
    report=dict(passed=False,source='local_video_over_SSH',video=str(args.video.resolve()),mode=args.mode,
                backend=args.backend,benchmarks=[],
                stream_id=stream_id,pixel_format=args.pixel_format,source_fps=reader.fps,
                fps_fallback=reader.fps_fallback,opencv_version=cv2.__version__,frames_sent=0,results=[])
    stderr_log=(out/'board.stderr.log').open('wb')
    protocol_log=(out/'board.events.jsonl').open('w',encoding='utf-8')

    def response(stream):
        data=stream.readline(1024*1024+1)
        if not data:raise EOFError('Board stream closed before completion')
        if len(data)>1024*1024:raise ValueError('Board reply exceeds limit')
        value=json.loads(data.decode('utf-8') if isinstance(data,bytes) else data)
        protocol_log.write(json.dumps(value,ensure_ascii=False)+'\n');protocol_log.flush()
        if value.get('event')=='error':raise RuntimeError(value.get('error','Board stream failed'))
        return value

    try:
        with board_connection() as client:
            command=shlex.join(['python3','-u',('/root/wcis-face/run-jpeg-stream.py' if args.backend=='jpeg' else '/root/wcis-face/run-video-stream.py'),
                               '--stream','--frames',str(args.max_frames)]+(['--replay',str(args.jpeg_replay)] if args.backend=='jpeg' else []))
            # No PTY: terminal translation would corrupt raw binary frames.
            stdin,stdout,stderr=client.exec_command(command,get_pty=False,timeout=100)
            channel=stdout.channel
            stdout=channel.makefile('rb');stderr=channel.makefile_stderr('rb')
            def drain_stderr():
                while True:
                    data=stderr.read(4096)
                    if not data:break
                    stderr_log.write(data);stderr_log.flush()
            stderr_thread=threading.Thread(target=drain_stderr,name='ssh-stderr',daemon=True);stderr_thread.start()
            try:
                while True:
                    value=response(stdout)
                    if value.get('event')=='launch':report['board_out']=value['out']
                    if value.get('event')=='ready':break
                if args.mode=='latest':source=LatestFrames(reader,stop);source.start()
                started=time.monotonic()
                for unused in range(args.max_frames):
                    if stop.is_set():break
                    frame=source.take() if source else reader.read()
                    if frame is None:break
                    pack_started=time.monotonic()
                    payload,w,h,pitch=pack_frame(frame.pop('pixels'),args.pixel_format,np)
                    pack_ms=(time.monotonic()-pack_started)*1000
                    meta=dict(version=1,kind='frame',stream_id=stream_id,sequence=frame['sequence'],pts_us=frame['pts_us'],
                              pixel_format=args.pixel_format,width=w,height=h,pitch_bytes=pitch,
                              sha256=hashlib.sha256(payload).hexdigest())
                    header=encode_header(meta,len(payload));sent_at=time.monotonic()
                    channel.sendall(header);channel.sendall(payload);send_ms=(time.monotonic()-sent_at)*1000
                    del payload
                    value=response(stdout);received_at=time.monotonic()
                    if (value.get('event')!='result' or value.get('stream_id')!=stream_id
                            or value.get('sequence')!=meta['sequence'] or value.get('pts_us')!=meta['pts_us']
                            or value.get('frame_sha256')!=meta['sha256']):
                        raise RuntimeError('Recognition result belongs to another source frame')
                    value['local_timing']=dict(decode_ms=frame['decode_ms'],pack_ms=pack_ms,
                        source_age_at_send_ms=(sent_at-frame['decoded_at'])*1000,send_ms=send_ms,
                        round_trip_ms=(received_at-sent_at)*1000,decode_to_result_ms=(received_at-frame['decoded_at'])*1000)
                    report['frames_sent']+=1;report['results'].append(value)
                    with (out/'results.jsonl').open('a',encoding='utf-8') as log:log.write(json.dumps(value,ensure_ascii=False)+'\n')
                    if args.backend=='jpeg':
                        print('帧',value['sequence'],'JPEG',value['jpeg_bytes'],'字节 / FPGA',round(value['hardware']['hardware_ms'],2),
                              'ms / 往返',round(value['local_timing']['round_trip_ms'],1),'ms',flush=True)
                    else:
                        print('帧',value['sequence'],'视频时间',round(value['pts_us']/1000000,3),'s',
                              value['status'],'人脸',value['face_count'],'板端处理',round(value['timing']['pipeline_ms'],1),
                              'ms / 往返',round(value['local_timing']['round_trip_ms'],1),'ms',flush=True)
                report['source_session_ms']=(time.monotonic()-started)*1000
                channel.sendall(encode_header(dict(version=1,kind='finish',stream_id=stream_id),0))
                channel.shutdown_write()
                while True:
                    value=response(stdout)
                    if value.get('event')=='source_flushed':
                        report['source_flush']=value
                        report['source_committed_ms']=(time.monotonic()-started)*1000
                    if value.get('event')=='benchmark':
                        report['benchmarks'].append(value)
                        print('板端测试',value['kind'],round(value['batch_fps'],2),'FPS',flush=True)
                    if value.get('event')=='done':report['board_done']=value
                    if value.get('event')=='restored':report['photo_service_restored']=value['status']=='ready';break
                code=channel.recv_exit_status()
                if code:raise RuntimeError('Board video input exited with code '+str(code))
                report.update(passed=True,session_ms=(time.monotonic()-started)*1000)
            except BaseException:
                # EOF rejects a partial packet before SDK use; a current full
                # frame drains normally before the receiver releases ownership.
                channel.shutdown_write()
                try:
                    while True:
                        data=stdout.readline(1024*1024+1)
                        if not data:break
                        protocol_log.write(data.decode('utf-8','replace') if isinstance(data,bytes) else data);protocol_log.flush()
                except (OSError,EOFError):pass
                raise
    except BaseException as error:
        report.update(passed=False,error_type=type(error).__name__,error=str(error))
        raise
    finally:
        interrupted=stop.is_set()
        stop.set()
        try:
            if source is not None:source.close()
            else:reader.close()
        except BaseException as error:
            report.update(passed=False,error_type=type(error).__name__,error=str(error))
            raise
        finally:
            if stderr_thread is not None:stderr_thread.join(timeout=5)
            stderr_log.close();protocol_log.close()
            for sig,handler in old.items():signal.signal(sig,handler)
            report.update(decoded_frames=reader.decoded,dropped_or_unsent_frames=max(0,reader.decoded-report['frames_sent']),
                          timestamp_fallbacks=reader.timestamp_fallbacks,decode_total_ms=reader.decode_total_ms,stopped=interrupted)
            (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.backend=='jpeg' and report.get('passed'):
        print('本地新帧至eMMC落盘：',round(report['frames_sent']*1000/report['source_committed_ms'],2),
              'FPS（包含解码、传输、DDR校验和末次fsync）',flush=True)
    print('运行记录：'+str(out/'summary.json'))


if __name__=='__main__':
    main()
