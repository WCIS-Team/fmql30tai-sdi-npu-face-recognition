"""Temporary hardware ownership for the bounded JPEG video test; restore photos."""
import argparse,fcntl,hashlib,json,os,signal,subprocess,sys,time,urllib.request,uuid
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stream',action='store_true',required=True)
    p.add_argument('--frames',type=int,default=30)
    p.add_argument('--replay',type=int,default=0)
    p.add_argument('--config',type=Path,default=Path('/root/wcis-face/jpeg-stream-current.json'))
    a=p.parse_args()
    if not 1<=a.frames<=300 or not 0<=a.replay<=300:p.error('Invalid bounded test count')
    cfg=json.loads(a.config.read_text());app=Path(cfg['app']);root=Path(cfg['root'])
    for f in cfg['files']:
        if hashlib.sha256((app/f['file']).read_bytes()).hexdigest()!=f['sha256']:raise RuntimeError('JPEG artifact changed')
    unit=Path('/etc/systemd/system/wcis-face-photo.service')
    if hashlib.sha256(unit.read_bytes()).hexdigest()!=cfg['photo_service_sha256']:raise RuntimeError('Photo service changed')
    marker=Path('/root/wcis-face/hardware-review-required.json')
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if marker.exists() and json.loads(marker.read_text()).get('boot_id')==boot:raise RuntimeError('Hardware quarantined')
    was_active=subprocess.run(['systemctl','is-active','--quiet','wcis-face-photo.service']).returncode==0
    paused=False;child=None;stop=False
    def stop_test(*_):
        nonlocal stop
        stop=True
        if child is not None and child.poll() is None:child.send_signal(signal.SIGTERM)
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,stop_test)
    try:
        with (root/'npu.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if was_active:
                subprocess.run(['systemctl','stop','wcis-face-photo.service'],check=True,timeout=75);paused=True
        if stop:return 0
        out=Path('/mnt/wcis-emmc/wcis-face/recording-tests')/('jpeg-'+uuid.uuid4().hex)
        print(json.dumps(dict(event='launch',out=str(out))),flush=True)
        env=os.environ.copy()
        if cfg.get('library_path'):env['LD_LIBRARY_PATH']=cfg['library_path']
        child=subprocess.Popen([sys.executable,'-u',str(app/'receive_jpeg_stream.py'),'--root',str(root),
            '--out',str(out),'--binary',str(app/'wcis_jpeg'),'--frames',str(a.frames),'--replay',str(a.replay)],
            start_new_session=True,env=env)
        if stop:child.send_signal(signal.SIGTERM)
        return child.wait()
    finally:
        if paused:
            if child is not None and child.poll() is None:
                raise RuntimeError('JPEG process still owns hardware; photo service left stopped')
            if marker.exists() and json.loads(marker.read_text()).get('boot_id')==boot:
                raise RuntimeError('Hardware review required; photo service left stopped')
            subprocess.run(['systemctl','start','wcis-face-photo.service'],check=True,timeout=45)
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(100):
                try:
                    with opener.open(cfg['photo_health_url'],timeout=2) as r:h=json.loads(r.read())
                    if h.get('status')=='ready':break
                except OSError:pass
                time.sleep(.25)
            else:raise RuntimeError('Photo service did not recover')
            print(json.dumps(dict(event='restored',status='ready')),flush=True)
if __name__=='__main__':raise SystemExit(main())
