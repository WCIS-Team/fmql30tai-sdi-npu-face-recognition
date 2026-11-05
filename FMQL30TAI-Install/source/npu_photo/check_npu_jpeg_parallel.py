"""Paired serial/overlap hardware verification. No service/camera integration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import threading
import time


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Worker:
    def __init__(self,binary,manifest,work):
        self.buffer=b'';self.log=(work/'worker.stdout.log').open('wb');self.err=(work/'worker.stderr.log').open('wb')
        self.process=subprocess.Popen([str(binary),'--serve',str(manifest)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,start_new_session=True)
        self.ready=self.read()
        if self.ready.get('status')!='ready' or self.ready.get('device_opened') is not False:raise RuntimeError('Expected CPU-only startup')
    def read(self):
        end=time.monotonic()+45
        while time.monotonic()<end:
            if b'\n' in self.buffer:
                line,self.buffer=self.buffer.split(b'\n',1)
                if b'WCIS_PARALLEL_RESULT ' in line:
                    q=json.loads(line.split(b'WCIS_PARALLEL_RESULT ',1)[1])
                    if q.get('status')=='error':raise RuntimeError(q.get('message','Parallel worker failed'))
                    return q
                continue
            if select.select([self.process.stdout],[],[],max(0,end-time.monotonic()))[0]:
                data=os.read(self.process.stdout.fileno(),65536)
                if not data:raise RuntimeError('Parallel worker exited before result')
                self.log.write(data);self.log.flush();self.buffer+=data
        raise TimeoutError('Parallel command deadline; drain before releasing ownership')
    def command(self,q):
        self.process.stdin.write((json.dumps(q)+'\n').encode());self.process.stdin.flush();return self.read()
    def close(self):
        if not self.process.stdin.closed:self.process.stdin.close()
        # No forced kill or release while any hardware command is in flight.
        self.process.wait();self.process.stdout.close();self.log.close();self.err.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',required=True,type=Path)
    p.add_argument('--seeds',required=True,nargs='+',type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--pairs',type=int,default=3)
    p.add_argument('--stop-during-command',action='store_true')
    a=p.parse_args()
    if not 1<=a.pairs<=5 or not 1<=len(a.seeds)<=6:p.error('Bound test to 1..6 seeds and 1..5 pairs')
    import fcntl
    import cv2
    import numpy as np
    from run_frame_replay import load_seed
    from pl_preprocess import PLPreprocessor
    from run_photos import decode
    cfg=json.loads(Path('/root/wcis-face/video-stream-current.json').read_text());root=Path(cfg['release']);app=Path(cfg['app'])
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if cfg['verified_boot_id']!=boot:raise RuntimeError('Unverified boot')
    marker=Path('/root/wcis-face/hardware-review-required.json')
    if marker.exists() and json.loads(marker.read_text()).get('boot_id')==boot:raise RuntimeError('Quarantined boot')
    for q in cfg['files']:
        if sha(app/q['file'])!=q['sha256']:raise RuntimeError('Active app changed')
    config=json.loads((root/'models.json').read_text())
    for q in config['models'].values():
        for key in ('json','raw'):
            if sha(root/q[key])!=q[key+'_sha256']:raise RuntimeError('Model checksum mismatch')
    seeds=[load_seed(path) for path in a.seeds]
    if any((s['width'],s['height'])!=(1920,1080) for s in seeds):raise ValueError('Native 1080p tensors required')
    if Path('/mnt/wcis-emmc/wcis-face/recording-tests') not in a.out.resolve().parents or not Path('/mnt/wcis-emmc').is_mount():
        raise RuntimeError('Use eMMC recording-tests output')
    if os.statvfs('/mnt/wcis-emmc').f_bavail*os.statvfs('/mnt/wcis-emmc').f_frsize<512*1024*1024:raise RuntimeError('Not enough test space reserve')
    a.out.mkdir(parents=True,exist_ok=False)
    stop=threading.Event();old={s:signal.signal(s,lambda *_:stop.set()) for s in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)}
    report=dict(passed=False,boot_id=boot,parallel_hardware=True,camera_input=False,checks=[],frames=[],stopped=False)
    worker=prep=None
    with (root/'npu.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            prep=PLPreprocessor(app/'wcis_face_pl_retained',a.out/'pl',marker,True)
            worker=Worker(a.binary,root/'models.json',a.out)
            for sequence,seed in enumerate(seeds,1):
                if stop.is_set():break
                directory=a.out/('frame-'+str(sequence));directory.mkdir()
                padded,sx,sy=prep.prepare_packed(seed['path'],1920,1080,seed['pitch_bytes'],seed['pixel_format'],frame_id=sequence)
                lease=dict(prep.retained_frame);roles=[('yunet',padded.astype(np.float32))];reference_jpeg=None
                idx=0
                while idx<len(roles) and not stop.is_set():
                    role,tensor=roles[idx];idx+=1
                    file=directory/(role+'.f32');np.ascontiguousarray(tensor,dtype='<f4').tofile(file)
                    base_outputs=None
                    for pair in range(a.pairs):
                        if stop.is_set():break
                        pair_results={}
                        # Reverse mode order on alternating pairs; every graph
                        # recreates the same session and takes the same witness.
                        for mode in (('serial','overlap') if pair%2==0 else ('overlap','serial')):
                            out=directory/(role+'-'+str(pair)+'-'+mode)
                            q=dict(mode=mode,role=role,retained_frame=lease,input_f32=str(file),output_directory=str(out),fault_marker=str(marker))
                            timer=None
                            if a.stop_during_command and mode=='overlap':
                                timer=threading.Timer(0.02,lambda:os.kill(os.getpid(),signal.SIGTERM));timer.start()
                            try:result=worker.command(q)
                            finally:
                                if timer is not None:timer.cancel();timer.join()
                            if result.get('status')!='completed' or result.get('device_closed') is not True or result.get('frame_id')!=sequence or result.get('frame_token')!=lease['frame_token'] or result.get('frame_preserved') is not True:
                                raise RuntimeError('Incorrect shared-device completion')
                            hashes=[];arrays=[]
                            for record in result['outputs']:
                                values=np.fromfile(record['file'],dtype='<f4')
                                if values.size!=record['elements'] or not np.all(np.isfinite(values)):raise RuntimeError('Invalid NPU output')
                                hashes.append(sha(record['file']));arrays.append(values)
                            if base_outputs is None:base_outputs=hashes
                            if hashes!=base_outputs:raise RuntimeError('Overlap changed NPU tensor bytes')
                            image=Path(result['jpeg']['file']);image_hash=sha(image)
                            if reference_jpeg is None:reference_jpeg=image_hash
                            if image_hash!=reference_jpeg:raise RuntimeError('NPU overlap changed JPEG bytes')
                            decoded=cv2.imread(str(image))
                            if decoded is None or decoded.shape!=(1080,1920,3):raise RuntimeError('JPEG decode incomplete')
                            if result['jpeg']['read_blocks']!=seed['pitch_bytes']*1080//64:raise RuntimeError('JPEG read coverage mismatch')
                            if mode=='overlap' and not result['overlap_proven']:raise RuntimeError('No convolution completion while JPG1 busy; overlap not proved')
                            result.update(role=role,sequence=sequence,pair=pair,pixel_format=seed['pixel_format'],source_sha256=seed['sha256'],output_sha256=hashes,jpeg_sha256=image_hash)
                            report['checks'].append(result);pair_results[mode]=result
                            (out/'verification.json').write_text(json.dumps(result,indent=2))
                            if role=='yunet' and pair==0 and mode=='serial':
                                faces=decode(arrays,sx,sy,logits=config.get('detector_activation')=='host_sigmoid')
                                if faces:
                                    face=max(faces,key=lambda f:f['score']);crop=prep.align_retained(face)
                                    roles.append(('mobilefacenet',(crop[:,:,::-1].astype(np.float32)-127.5)/127.5))
                            if stop.is_set():break
                        if len(pair_results)==2:
                            print('PARALLEL_PAIR '+json.dumps(dict(sequence=sequence,role=role,pair=pair,serial_ms=pair_results['serial']['both_ready_ms'],overlap_ms=pair_results['overlap']['both_ready_ms'],overlap_proven=True)),flush=True)
                equal=prep.verify_retained_source()['full_source_equal']
                report['frames'].append(dict(frame_id=sequence,frame_token=lease['frame_token'],source_sha256=seed['sha256'],full_source_equal=equal,source_uploads=1))
            report.update(passed=True,stopped=stop.is_set())
        except BaseException as e:
            report.update(error_type=type(e).__name__,error=str(e));raise
        finally:
            errors=[]
            for obj in (worker,prep):
                if obj is not None:
                    try:obj.close()
                    except BaseException as e:errors.append(str(e))
            processes=[]
            if worker is not None:processes.append(worker.process)
            if prep is not None and prep.worker is not None:processes.append(prep.worker.process)
            for process in processes:
                if process.poll() is None:
                    marker.write_text(json.dumps(dict(boot_id=boot,source='parallel_drain',automatic_retry=False)));process.wait()
            report['worker_exit_codes']=[v.returncode for v in processes]
            if errors or any(v.returncode!=0 for v in processes):report.update(passed=False,close_errors=errors)
            (a.out/'verification.json').write_text(json.dumps(report,indent=2))
            for sig,handler in old.items():signal.signal(sig,handler)
    if not report['passed']:raise RuntimeError('Parallel verification failed')
    print('PARALLEL_DONE '+json.dumps(dict(passed=True,stopped=stop.is_set(),commands=len(report['checks']),out=str(a.out))),flush=True)


if __name__=='__main__':main()
