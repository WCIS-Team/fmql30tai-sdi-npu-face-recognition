"""Receive changing raw video frames from stdin and use the shared ModelBackend.

This injects at the packed-frame/DDR adapter, after the SDI capture boundary.
PS receives SSH data and uploads each new frame; no SDI pins/clock/RX logic are
exercised. One completed frame is acknowledged before the next is accepted.
"""
import argparse
import json
import os
import select
import signal
import tempfile
import threading
import time
from pathlib import Path
from frame_stream_protocol import read_packet


class DeadlineInput:
    def __init__(self,fd,stop,timeout):
        self.fd,self.stop,self.timeout=fd,stop,timeout
        self.deadline=time.monotonic()+timeout
    def begin(self):self.deadline=time.monotonic()+self.timeout
    def read(self,size):
        while True:
            if self.stop.is_set():raise InterruptedError('Stream stopping')
            remaining=self.deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Video packet input deadline exceeded')
            if select.select([self.fd],[],[],min(.25,remaining))[0]:return os.read(self.fd,size)


def emit(event,**values):
    print(json.dumps(dict(event=event,**values),ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--max-frames',type=int,default=30)
    parser.add_argument('--gallery-store',type=Path,required=True)
    parser.add_argument('--gallery-mount',type=Path,required=True)
    parser.add_argument('--gallery-uuid',required=True)
    args=parser.parse_args()
    if not 1<=args.max_frames<=300:parser.error('Use 1..300 frames per bounded test')
    import fcntl
    from model_backend_runtime import ModelBackend
    from pl_preprocess import PLPreprocessor
    from persistent_gallery import PersistentGallery
    from recognize_frame import infer_prepared
    from run_photos import save,sha
    app=Path(__file__).resolve().parent
    stop=threading.Event()
    old={sig:signal.signal(sig,lambda s,f:stop.set()) for sig in (signal.SIGINT,signal.SIGTERM)}
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    marker=args.root.parents[1]/'hardware-review-required.json'
    if marker.exists() and json.loads(marker.read_text()).get('boot_id')==boot:
        raise RuntimeError('Current boot requires hardware review')
    config=json.loads((args.root/'models.json').read_text())
    evidence=json.loads((args.root/'run-01/verification.json').read_text())
    pipeline='yunet-mf-'+config['precision']+'-npu:'+sha(args.root/'models.json')
    gallery=PersistentGallery(args.root,args.gallery_store,args.gallery_mount,args.gallery_uuid)
    templates=gallery.templates()
    if not evidence['all_passed'] or evidence['pipeline_id']!=pipeline or templates['pipeline_id']!=pipeline:
        raise RuntimeError('Frame/model/gallery mismatch')
    args.out.mkdir(parents=True,exist_ok=False)
    state=dict(source='SSH_decoded_video',camera_input=False,content_updates=True,
               status='starting',boot_id=boot,frames_processed=0,stream_id=None)
    backend=None;prep=None;last_seq=0;last_pts=-1
    save(args.out/'latest.json',state)
    with (args.root/'npu.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            backend=ModelBackend(args.root,app/'wcis_face_cached')
            with tempfile.TemporaryDirectory(prefix='wcis-face-stream-',dir='/dev/shm') as work:
                prep=PLPreprocessor(app/'wcis_face_pl_retained',Path(work)/'PL',marker,True)
                source=Path(work)/'input.raw'
                reader=DeadlineInput(0,stop,30)
                state['status']='running'
                emit('ready',source=state['source'],camera_input=False,max_inflight=1,max_frames=args.max_frames)
                try:
                    for index in range(args.max_frames):
                        if stop.is_set():break
                        reader.begin()
                        try:packet=read_packet(reader)
                        except InterruptedError:
                            if stop.is_set():break
                            raise
                        if packet is None:break
                        meta,payload,receive_ms=packet
                        if state['stream_id'] is None:state['stream_id']=meta['stream_id']
                        if meta['stream_id']!=state['stream_id']:raise ValueError('Stream identity changed')
                        if meta['kind']=='finish':break
                        if meta['sequence']<=last_seq or meta['pts_us']<last_pts:
                            raise ValueError('Video frames arrived out of order')
                        started=time.monotonic();gallery.guard();backend.validate_release()
                        source.write_bytes(payload);del payload
                        prep.timings.clear()
                        padded,sx,sy=prep.prepare_packed(source,meta['width'],meta['height'],
                            meta['pitch_bytes'],meta['pixel_format'],frame_id=meta['sequence'])
                        host={'prepare_ms':(time.monotonic()-started)*1000}
                        with tempfile.TemporaryDirectory(prefix='frame-',dir=work) as exchange:
                            result=infer_prepared(padded,sx,sy,root=args.root,out=Path(exchange),
                                config=config,evidence=evidence,gallery=templates,preprocessor=prep,
                                model_backend=backend,host=host,start=started,save_aligned=False,
                                identity=dict(source=state['source'],stream_id=meta['stream_id'],
                                    frame_id=meta['sequence'],video_pts_us=meta['pts_us'],
                                    pixel_format=meta['pixel_format'],frame_sha256=meta['sha256'],boot_id=boot))
                            jobs=result['timing']['preprocessing']
                            if not jobs[0]['source_uploaded_this_command'] or any(j['source_uploaded_this_command'] for j in jobs[1:]):
                                raise RuntimeError('New-frame upload/alignment reuse contract failed')
                            timing=dict(board_receive_ms=receive_ms,pipeline_ms=result['elapsed_ms'],
                                        ps_receive_to_PL_and_resize_ms=host['prepare_ms'])
                            ack=dict(sequence=meta['sequence'],pts_us=meta['pts_us'],
                                     stream_id=meta['stream_id'],frame_sha256=meta['sha256'],
                                     pixel_format=meta['pixel_format'],width=meta['width'],height=meta['height'],
                                     status=result['status'],face_count=result['face_count'],
                                     name=result.get('name'),faces=result['faces'],timing=timing,
                                     identities=result['identities'],
                                     processed_face_count=result['processed_face_count'],
                                     skipped_face_count=result['skipped_face_count'],face_limit=result['face_limit'],
                                     source_uploads=1,frame_token=prep.retained_frame['frame_token'],
                                     outputs={role:[v['sha256'] for v in result['timing'][role]['outputs']]
                                         for role in ('detector','recognizer') if role in result['timing']})
                            last_seq,last_pts=meta['sequence'],meta['pts_us']
                            state.update(frames_processed=index+1,last_result=ack)
                            save(args.out/'latest.json',state)
                            with (args.out/'frames.jsonl').open('a') as log:log.write(json.dumps(ack,ensure_ascii=False)+'\n')
                            emit('result',**ack)
                    state['status']='stopped' if stop.is_set() else 'complete'
                finally:
                    prep.close();prep=None
        except BaseException as error:
            state.update(status='failed',error_type=type(error).__name__,error=str(error))
            if ((prep is not None and prep.worker is not None and prep.worker.broken)
                    or (backend is not None and backend.broken)):
                save(marker,dict(boot_id=boot,message=str(error),automatic_retry=False))
            emit('error',error_type=type(error).__name__,error=str(error))
            raise
        finally:
            try:
                if prep is not None:prep.close()
            finally:
                try:
                    if backend is not None:backend.close()
                finally:
                    save(args.out/'latest.json',state)
                    for sig,handler in old.items():signal.signal(sig,handler)
    emit('done',status=state['status'],frames_processed=state['frames_processed'])


if __name__=='__main__':
    main()
