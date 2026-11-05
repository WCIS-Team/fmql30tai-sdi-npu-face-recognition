"""Bounded ModelBackend ownership test; static packed frames, not SDI capture.

Interleave real NPU inference and PL JPEG on a single retained source. Keep
the established global lock and drain current operations on SIGINT/SIGTERM.
"""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(directory):
    """Raw NPU output hashes include every selected face and detector head."""
    result={}
    for path in sorted((Path(directory)/'timing').glob('*.json')):
        value=json.loads(path.read_text())
        result[path.name]=[q['sha256'] for q in value['outputs']]
    if not result:raise RuntimeError('No raw NPU evidence')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,default=Path('/root/wcis-face/video-stream-current.json'))
    p.add_argument('--jpeg-binary',type=Path,required=True)
    p.add_argument('--seeds',type=Path,nargs='+',required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cycles',type=int,default=1)
    p.add_argument('--stop-after-jpeg',action='store_true',help='Deterministic graceful-stop acceptance: signal self after a completed JPEG')
    p.add_argument('--stop-during-jpeg',action='store_true',help='Signal this test process while a synchronous JPEG command is in flight')
    a=p.parse_args()
    if not 1<=a.cycles<=10:p.error('Use 1..10 bounded cycles')
    import fcntl
    import cv2
    import numpy as np
    from run_frame_replay import load_seed
    from model_backend_runtime import ModelBackend
    from pl_preprocess import PLPreprocessor
    from recognize_frame import infer_prepared
    from leased_jpeg import LeasedJPEG
    cfg=json.loads(a.config.read_text());root=Path(cfg['release']);app=Path(cfg['app'])
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if cfg.get('verified_boot_id')!=boot:raise RuntimeError('Unverified boot')
    for record in cfg['files']:
        if sha(app/record['file'])!=record['sha256']:raise RuntimeError('Active app checksum mismatch')
    marker=a.config.parent/'hardware-review-required.json'
    if marker.exists() and json.loads(marker.read_text()).get('boot_id')==boot:raise RuntimeError('Hardware review required')
    seeds=[load_seed(path) for path in a.seeds]
    if not 1<=len(seeds)*a.cycles<=120:raise ValueError('Use at most 120 retained frames')
    if any((s['width'],s['height'])!=(1920,1080) or s['pitch_bytes']!=1920*(2 if s['pixel_format']=='RGB565LE' else 4) for s in seeds):
        raise ValueError('Use unchanged tightly packed native 1080p input')
    recording_root=Path('/mnt/wcis-emmc/wcis-face/recording-tests').resolve()
    if not Path('/mnt/wcis-emmc').is_mount() or recording_root not in a.out.resolve().parents:
        raise RuntimeError('Use the existing eMMC recording-tests mount')
    v=__import__('os').statvfs(recording_root)
    required_bytes=512*1024*1024+len(seeds)*a.cycles*2*8*1024*1024
    if v.f_bavail*v.f_frsize<required_bytes:raise RuntimeError('Insufficient worst-case JPEG space plus reserve')
    config=json.loads((root/'models.json').read_text());evidence=json.loads((root/'run-01/verification.json').read_text())
    pipeline='yunet-mf-'+config['precision']+'-npu:'+sha(root/'models.json')
    fs=cfg['filesystem'];mount=Path(fs['mount'])
    mount_info=json.loads(subprocess.run(['findmnt','-J','-T',str(mount),'-o','TARGET,UUID,FSTYPE'],
        check=True,capture_output=True,text=True).stdout)['filesystems'][0]
    if mount_info['uuid']!=fs['uuid'] or mount_info['target']!=str(mount) or mount_info['fstype']!='ext4':
        raise RuntimeError('Recording/gallery mount identity changed')
    gallery_path=mount/'wcis-face/galleries'/sha(root/'models.json')[:16]/'gallery.json'
    gallery_digest=sha(gallery_path);gallery_device=gallery_path.stat().st_dev
    database=json.loads(gallery_path.read_text())
    if database['schema_version']!=2 or database['pipeline_id']!=pipeline:raise RuntimeError('Gallery snapshot incompatible')
    # Reuse only the pure template calculation. Avoid constructors that can
    # seed a store or recover/delete orphan files in the personnel database.
    from gallery import Gallery
    from types import SimpleNamespace
    templates=Gallery.templates_from_db(SimpleNamespace(pipeline=pipeline),database)
    def gallery_guard():
        if not mount.is_mount() or gallery_path.stat().st_dev!=gallery_device or sha(gallery_path)!=gallery_digest:
            raise RuntimeError('Read-only gallery snapshot changed during test')
    if not evidence['all_passed'] or evidence['pipeline_id']!=pipeline or templates['pipeline_id']!=pipeline:
        raise RuntimeError('Unvalidated model/gallery contract')
    a.out.mkdir(parents=True,exist_ok=False)
    stop=threading.Event();old={}
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):old[sig]=signal.signal(sig,lambda *_:stop.set())
    report=dict(passed=False,mode='sequential_device_handoff',camera_input=False,parallel_hardware=False,
        boot_id=boot,requested_frames=len(seeds)*a.cycles,frames=[],stopped=False,max_inflight=1)
    backend=prep=jpeg=None
    with (root/'npu.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            backend=ModelBackend(root,app/'wcis_face_cached')
            prep=PLPreprocessor(app/'wcis_face_pl_retained',a.out/'pl',marker,True)
            jpeg=LeasedJPEG(a.jpeg_binary,a.out/'jpeg-worker',marker)
            report['cpu_only_worker_ready']=all(w.ready['device_opened'] is False for w in backend.workers.values()) and jpeg.ready['device_opened'] is False
            for sequence in range(1,len(seeds)*a.cycles+1):
                if stop.is_set():break
                seed=seeds[(sequence-1)%len(seeds)];started=time.monotonic()
                directory=a.out/('frame-'+str(sequence));directory.mkdir()
                gallery_guard();backend.validate_release();prep.timings.clear()
                padded,sx,sy=prep.prepare_packed(seed['path'],1920,1080,seed['pitch_bytes'],seed['pixel_format'],frame_id=sequence)
                lease=dict(prep.retained_frame)
                def infer(label,tensor):
                    out=directory/label;out.mkdir()
                    result=infer_prepared(tensor,sx,sy,root=root,out=out,config=config,evidence=evidence,gallery=templates,
                        preprocessor=prep,model_backend=backend,save_aligned=False,
                        identity=dict(frame_id=sequence,frame_token=lease['frame_token'],source_sha256=seed['sha256'],pts_us=(sequence-1)*40000))
                    return result,fingerprint(out)
                before,before_hashes=infer('before',padded)
                timer=None
                if a.stop_during_jpeg:
                    # The JPEG worker is in a separate process group. The
                    # signal requests a stop; it never reaches SDK/DMA code.
                    timer=threading.Timer(0.02,lambda:__import__('os').kill(__import__('os').getpid(),signal.SIGTERM))
                    timer.start()
                try:j1=jpeg.compress(lease,(sequence-1)*40000,seed['sha256'],directory/'a.jpg')
                finally:
                    if timer is not None:timer.cancel();timer.join()
                if a.stop_after_jpeg:__import__('os').kill(__import__('os').getpid(),signal.SIGTERM)
                if stop.is_set():
                    prep.verify_retained_source()
                    report['drained_frame']=dict(frame_id=sequence,frame_token=lease['frame_token'],source_equal=True,jpeg=j1,
                        stop_during_command=a.stop_during_jpeg)
                    break
                # Repeat both stages after the JPEG device owner has exited.
                padded2,_,_=prep.resize_retained()
                after,after_hashes=infer('after',padded2)
                j2=jpeg.compress(lease,(sequence-1)*40000,seed['sha256'],directory/'b.jpg')
                full=prep.verify_retained_source()
                if before_hashes!=after_hashes:raise RuntimeError('JPEG handoff changed raw NPU outputs')
                def identities(value):
                    return [{k:person[k] for k in ('face_index','face','status','name','similarity','scores')} for person in value['identities']]
                if identities(before)!=identities(after):raise RuntimeError('JPEG changed face/identity result')
                if sha(directory/'a.jpg')!=sha(directory/'b.jpg'):raise RuntimeError('NPU handoff changed JPEG bytes')
                for item in (j1,j2):
                    if item['read_blocks']!=seed['pitch_bytes']*1080//64 or item['write_blocks']!=(item['jpeg_bytes']+63)//64:
                        raise RuntimeError('JPEG source/output block count mismatch')
                for filename in ('a.jpg','b.jpg'):
                    decoded=cv2.imread(str(directory/filename))
                    if decoded is None or decoded.shape!=(1080,1920,3):raise RuntimeError('Incomplete JPEG decode')
                # Distinct source contents must not silently reuse an older JPEG.
                digest=sha(directory/'a.jpg')
                for old_frame in report['frames']:
                    if old_frame['source_sha256']!=seed['sha256'] and old_frame['jpeg_sha256']==digest:
                        raise RuntimeError('Different source returned stale JPEG')
                one=dict(sequence=sequence,frame_id=lease['frame_id'],frame_token=lease['frame_token'],pts_us=(sequence-1)*40000,
                    pixel_format=seed['pixel_format'],source_sha256=seed['sha256'],source_uploads=1,
                    source_bytes=seed['pitch_bytes']*1080,source_equal=full['full_source_equal'],face_count=before['face_count'],
                    identities=identities(before),raw_npu_outputs_equal=True,jpeg_bytes_equal=True,jpeg_sha256=digest,
                    jpeg=[j1,j2],elapsed_ms=(time.monotonic()-started)*1000)
                report['frames'].append(one)
                (directory/'verification.json').write_text(json.dumps(one,indent=2))
                print('COEXIST_FRAME '+json.dumps(dict(sequence=sequence,pixel_format=seed['pixel_format'],faces=before['face_count'],jpeg_bytes=j1['jpeg_bytes'],source_uploads=1,passed=True)),flush=True)
            gallery_guard()
            report.update(passed=True,stopped=stop.is_set(),completed_frames=len(report['frames']))
        except BaseException as error:
            report.update(error=str(error),error_type=type(error).__name__)
            if (jpeg is not None and jpeg.broken) or (backend is not None and backend.broken) or (prep is not None and prep.worker.broken):
                marker.write_text(json.dumps(dict(boot_id=boot,source='coexist_test',error=str(error),automatic_retry=False)))
            raise
        finally:
            errors=[]
            for obj in (jpeg,prep,backend):
                if obj is not None:
                    try:obj.close()
                    except BaseException as e:errors.append(str(e))
            # Model/PL workers retain process objects; keep the global lock
            # held if a previous normal drain deadline expired.
            workers=[]
            if jpeg is not None:workers.append(jpeg.process)
            if prep is not None and prep.worker is not None:workers.append(prep.worker.process)
            if backend is not None:workers.extend(w.process for w in backend.workers.values())
            for worker in workers:
                if worker.poll() is None:
                    marker.write_text(json.dumps(dict(boot_id=boot,source='coexist_drain',automatic_retry=False)))
                    worker.wait()
            report['worker_exit_codes']=[worker.returncode for worker in workers]
            if any(code!=0 for code in report['worker_exit_codes']):errors.append('Worker exit was not clean')
            if errors:report.update(passed=False,close_errors=errors)
            (a.out/'verification.json').write_text(json.dumps(report,indent=2))
            for sig,handler in old.items():signal.signal(sig,handler)
            if errors:raise RuntimeError('Coexist worker drain failed: '+str(errors))
    print('COEXIST_DONE '+json.dumps(dict(passed=report['passed'],stopped=report['stopped'],frames=len(report['frames']),out=str(a.out))),flush=True)


if __name__=='__main__':main()
