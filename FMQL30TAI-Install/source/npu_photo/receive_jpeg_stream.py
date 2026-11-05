"""Bounded board test: raw SSH frames -> persistent JPG1 client -> eMMC MJPEG.

Reuses the existing frame packet validator/deadline reader. No CPU JPEG codec.
Resident replay is explicitly labelled and is never counted as new capture.
"""
import argparse,fcntl,hashlib,json,os,signal,subprocess,sys,tempfile,threading,time
from pathlib import Path
from frame_stream_protocol import read_packet
from receive_video_stream import DeadlineInput

def emit(event,**values):print(json.dumps(dict(event=event,**values)),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--frames',type=int,default=30)
    p.add_argument('--replay',type=int,default=0)
    a=p.parse_args()
    if not 1<=a.frames<=300 or not 0<=a.replay<=300:p.error('Bounded 1..300 source frames / 0..300 replay iterations')
    if not os.path.ismount('/mnt/wcis-emmc'):raise RuntimeError('eMMC mount absent')
    if not str(a.out).startswith('/mnt/wcis-emmc/wcis-face/recording-tests/'):
        raise RuntimeError('Unexpected test output directory')
    a.out.mkdir(parents=True,exist_ok=False)
    if os.statvfs(a.out).f_bavail*os.statvfs(a.out).f_frsize<512*1024*1024:
        raise RuntimeError('Not enough reserved free recording space')
    marker=Path('/root/wcis-face/hardware-review-required.json')
    cfg=dict(record_path=str(a.out/'output.mjpeg'),fault_marker=str(marker))
    (a.out/'worker.json').write_text(json.dumps(cfg))
    stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,lambda *_:stop.set())
    report=dict(source='local_decoded_video',backend='JPG1_FPGA',camera_input=False,
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),frames=[],benchmarks=[],passed=False)
    worker=None
    with (a.root/'npu.lock').open('a') as lock,(a.out/'worker.stderr.log').open('wb') as stderr:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        worker=subprocess.Popen([str(a.binary),'--serve',str(a.out/'worker.json')],stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,stderr=stderr,text=True,bufsize=1)
        def reply():
            while True:
                line=worker.stdout.readline()
                if not line:raise RuntimeError('JPEG client exited before reply')
                if line.startswith('WCIS_JPEG_RESULT '):
                    value=json.loads(line[len('WCIS_JPEG_RESULT '):])
                    if value.get('status')=='error':raise RuntimeError(value['message'])
                    return value
                print(line.rstrip(),file=sys.stderr,flush=True)
        def command(value):
            worker.stdin.write(json.dumps(value)+'\n');worker.stdin.flush();return reply()
        try:
            ready=reply()
            if ready.get('status')!='ready':raise RuntimeError('JPEG client not ready')
            report['worker_ready']=ready
            emit('ready',backend='JPG1_FPGA',width=1920,height=1080,quality=ready['quality'],max_inflight=1)
            source_id=None;last_seq=0;last_pts=-1;started=time.monotonic()
            with tempfile.TemporaryDirectory(prefix='wcis-jpeg-',dir='/dev/shm') as temp:
                raw=Path(temp)/'input.raw'
                reader=DeadlineInput(0,stop,90)
                for index in range(a.frames):
                    if stop.is_set():break
                    reader.begin()
                    packet=read_packet(reader)
                    if packet is None:break
                    meta,payload,receive_ms=packet
                    if source_id is None:source_id=meta['stream_id']
                    if meta['stream_id']!=source_id:raise ValueError('Stream identity changed')
                    if meta['kind']=='finish':break
                    bpp=2 if meta['pixel_format']=='RGB565LE' else 4
                    if (meta['width'],meta['height'],meta['pitch_bytes'])!=(1920,1080,1920*bpp):
                        raise ValueError('JPG1 requires unchanged 1920x1080 tightly packed frames')
                    if meta['sequence']<=last_seq or meta['pts_us']<last_pts:raise ValueError('Out-of-order frame')
                    t=time.monotonic();raw.write_bytes(payload);del payload
                    result=command(dict(op='frame',input=str(raw),sequence=meta['sequence'],
                        pixel_format=meta['pixel_format'],verify_source=True,readback=True,record=True))
                    one=result['results'][0]
                    ack=dict(sequence=meta['sequence'],pts_us=meta['pts_us'],stream_id=source_id,
                        frame_sha256=meta['sha256'],pixel_format=meta['pixel_format'],width=1920,height=1080,
                        status='compressed',backend='JPG1_FPGA',jpeg_bytes=one['jpeg_bytes'],hardware=one,
                        timing=dict(board_receive_ms=receive_ms,pipeline_ms=(time.monotonic()-t)*1000))
                    report['frames'].append(ack)
                    with (a.out/'frames.jsonl').open('a') as f:f.write(json.dumps(ack)+'\n')
                    last_seq,last_pts=meta['sequence'],meta['pts_us']
                    emit('result',**ack)
                # Sender transmits an explicit finish after its bounded count.
                # If the last iteration used all credits, the small finish packet
                # can remain unread; SSH EOF is still safe after full frames.
                report['source_session_ms']=(time.monotonic()-started)*1000
                report['source_flush']=command(dict(op='flush'))
                emit('source_flushed',**report['source_flush'])
                if a.replay and report['frames'] and not stop.is_set():
                    for name,readback,record in [('DDR_encode_only',False,False),('DDR_readback_eMMC',True,True)]:
                        bench=command(dict(op='replay',repeat=a.replay,readback=readback,record=record,sync=record))
                        bench['kind']=name;report['benchmarks'].append(bench)
                        emit('benchmark',**bench)
            closed=command(dict(op='finish'))
            worker.stdin.close()
            code=worker.wait(timeout=30)
            if code:raise RuntimeError('JPEG client exit code '+str(code))
            report.update(passed=True,closed=closed,device_closed=True)
            emit('done',frames_processed=len(report['frames']),out=str(a.out),
                 record_path=str(a.out/'output.mjpeg'),record_bytes=closed['record_bytes'],fsync_ms=closed['fsync_ms'])
        finally:
            if worker.poll() is None:
                # A complete in-flight command must drain. Never KILL a process
                # that could own an outstanding AXI transaction.
                try:
                    worker.stdin.write('{"op":"finish"}\n');worker.stdin.flush()
                    report['close_on_error']=reply();worker.stdin.close();worker.wait(timeout=30)
                except Exception as e:
                    marker.write_text(json.dumps(dict(boot_id=report['boot_id'],source='JPEG_test',message=type(e).__name__,automatic_retry=False)))
                    raise RuntimeError('JPEG client requires hardware review; service must remain stopped') from e
            (a.out/'summary.json').write_text(json.dumps(report,indent=2))

if __name__=='__main__':main()
