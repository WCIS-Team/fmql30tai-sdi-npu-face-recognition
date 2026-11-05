"""Direct ModelBackend entry: bounded replay of one packed seed in PL DDR.

No HTTP photo endpoint or compressed image decoder is involved. The one-time
seed is already packed off-board. This is explicitly static replay, not new
camera frames or a continuous PL capture producer. SIGINT/SIGTERM drain the
current inference before returning ownership; never terminate the DMA worker.
"""
import argparse
import hashlib
import json
import signal
import threading
import time
import tempfile
from pathlib import Path


def load_seed(manifest):
    manifest=Path(manifest).resolve(strict=True)
    value=json.loads(manifest.read_text(encoding='utf-8'))
    if value.get('schema_version')!=1 or value.get('source')!='static_packed_frame':
        raise ValueError('Only explicit static packed replay seeds are accepted')
    if value.get('pixel_format') not in ('BGRX8','RGB565LE'):
        raise ValueError('Unsupported replay pixel format')
    w,h,pitch=(value.get(k) for k in ('width','height','pitch_bytes'))
    bpp=2 if value['pixel_format']=='RGB565LE' else 4
    if any(type(v) is not int for v in (w,h,pitch)):
        raise ValueError('Replay geometry must use integers')
    if not (1<=w<=8192 and 1<=h<=8192) or pitch%8 or pitch<w*bpp or pitch>65536:
        raise ValueError('Replay geometry outside the FAC1 contract')
    if 128+((pitch*h+63)//64)*64+640*640*4>64*1024*1024:
        raise ValueError('Replay seed exceeds the bounded allocation')
    path=(manifest.parent/value['file']).resolve(strict=True)
    path.relative_to(manifest.parent)
    if not path.is_file() or path.stat().st_size!=h*pitch:
        raise ValueError('Replay seed length mismatch')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=value.get('sha256'):
        raise ValueError('Replay seed checksum mismatch')
    value['path']=path
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--seed',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--frames',type=int,default=30)
    parser.add_argument('--period-ms',type=int,default=0)
    parser.add_argument('--gallery-store',required=True,type=Path)
    parser.add_argument('--gallery-mount',required=True,type=Path)
    parser.add_argument('--gallery-uuid',required=True)
    parser.add_argument('--verify-source',action='store_true',help='Full validation readback after replay only')
    args=parser.parse_args()
    if not 1<=args.frames<=300 or not 0<=args.period_ms<=5000:
        parser.error('Use 1..300 processing iterations and a period of 0..5000 ms')
    seed=load_seed(args.seed)
    # Platform/SDK dependencies are imported after validating CPU-only inputs.
    import fcntl
    from model_backend_runtime import ModelBackend
    from pl_preprocess import PLPreprocessor
    from persistent_gallery import PersistentGallery
    from recognize_frame import infer_prepared
    from run_photos import save,sha
    app=Path(__file__).resolve().parent
    stop=threading.Event()
    old_signals={}
    for sig in (signal.SIGTERM,signal.SIGINT):
        old_signals[sig]=signal.signal(sig,lambda signum,frame:stop.set())
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
        raise RuntimeError('Unvalidated frame/model/gallery combination')
    args.out.mkdir(parents=True,exist_ok=False)
    state=dict(source='static_PL_DDR_replay',camera_input=False,photo_upload_input=False,
               content_updates=False,boot_id=boot,requested_iterations=args.frames,
               completed_iterations=0,stopped=False,status='starting',source_uploads=0,
               seed_format=seed['pixel_format'],seed_sha256=seed['sha256'])
    save(args.out/'latest.json',state)
    backend=None;prep=None
    with (args.root/'npu.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            backend=ModelBackend(args.root,app/'wcis_face_cached')
            with tempfile.TemporaryDirectory(prefix='wcis-face-replay-',dir='/dev/shm') as work:
                prep=PLPreprocessor(app/'wcis_face_pl_retained',Path(work)/'PL',marker,True)
                start=time.monotonic()
                prep.prepare_packed(seed['path'],seed['width'],seed['height'],
                                    seed['pitch_bytes'],seed['pixel_format'])
                state.update(one_time_load_ms=(time.monotonic()-start)*1000,
                             source_uploads=1,source_builds=prep.source_builds,
                             frame_lease=prep.retained_frame,status='running')
                save(args.out/'latest.json',state)
                print('STATIC_DDR_REPLAY_READY '+json.dumps(state),flush=True)
                try:
                    for sequence in range(1,args.frames+1):
                        if stop.is_set():break
                        gallery.guard();backend.validate_release()
                        prep.timings.clear()
                        with tempfile.TemporaryDirectory(prefix='frame-',dir=work) as exchange:
                            started=time.monotonic()
                            padded,sx,sy=prep.resize_retained()
                            host={'prepare_ms':(time.monotonic()-started)*1000}
                            result=infer_prepared(padded,sx,sy,root=args.root,out=Path(exchange),
                                config=config,evidence=evidence,gallery=templates,preprocessor=prep,
                                model_backend=backend,host=host,start=started,save_aligned=False,
                                identity={'source':'static_PL_DDR_replay','sequence':sequence,
                                          'frame_id':prep.frame,'boot_id':boot,
                                          'frame_token':prep.retained_frame['frame_token']})
                            for job in result['timing']['preprocessing']:
                                if job['source_uploaded_this_command'] or not job['ddr_frame_reused']:
                                    raise RuntimeError('Replay unexpectedly rebuilt/uploaded its source')
                            state.update(completed_iterations=sequence,last_result=result)
                            save(args.out/'latest.json',state)
                            with (args.out/'timings.jsonl').open('a') as log:
                                log.write(json.dumps(dict(sequence=sequence,elapsed_ms=result['elapsed_ms'],
                                    face_count=result['face_count'],status=result['status'],
                                    source_uploaded=False))+'\n')
                            print('FRAME_RESULT '+json.dumps(dict(sequence=sequence,
                                source=state['source'],status=result['status'],
                                name=result.get('name'),face_count=result['face_count'],
                                identities=result['identities'],
                                processed_face_count=result['processed_face_count'],
                                skipped_face_count=result['skipped_face_count'],
                                elapsed_ms=result['elapsed_ms'],source_uploaded=False),ensure_ascii=False),flush=True)
                        if args.period_ms:stop.wait(max(0,args.period_ms/1000-(time.monotonic()-started)))
                    if args.verify_source:state['full_source_equal']=prep.verify_retained_source()['full_source_equal']
                finally:
                    prep.close();prep=None
            state.update(status='stopped' if stop.is_set() else 'complete',stopped=stop.is_set())
        except BaseException as error:
            state.update(status='failed',error_type=type(error).__name__,error=str(error))
            if ((prep is not None and prep.worker is not None and prep.worker.broken)
                    or (backend is not None and backend.broken)):
                save(marker,dict(boot_id=boot,error_type=type(error).__name__,message=str(error),automatic_retry=False))
            raise
        finally:
            try:
                if prep is not None:prep.close()
            finally:
                try:
                    if backend is not None:backend.close()
                finally:
                    save(args.out/'latest.json',state)
                    for sig,handler in old_signals.items():signal.signal(sig,handler)


if __name__=='__main__':
    main()
