"""Transactional JPEG firmware trial and boot-time recovery (board-side only)."""
import argparse,fcntl,hashlib,json,os,shutil,subprocess
from pathlib import Path
TASK=Path('/root/wcis-face/candidates/jpeg-20261016')
UNIT='wcis-jpeg-trial-20261016'
def run(*args):return subprocess.run(args,check=True,capture_output=True,text=True,timeout=90)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def copy_new(src,dst):
    with src.open('rb') as r,dst.open('xb') as w:
        shutil.copyfileobj(r,w);w.flush();os.fsync(w.fileno())
def mounted():return subprocess.run(['findmnt','-rn','-S','/dev/mmcblk0p1'],capture_output=True).stdout.strip()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--recover',action='store_true');a=p.parse_args()
    cfg=json.loads((TASK/'deploy.json').read_text())
    current=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    report=dict(boot_id=current,firmware_replaced=False,rollback=False)
    accepted=TASK/'accepted.json'
    if a.recover and accepted.exists() and json.loads(accepted.read_text()).get('boot_id')==current:
        run('systemctl','disable',UNIT+'.timer');return
    if a.recover and current==cfg['boot_id_before']:raise RuntimeError('Recovery is only for a subsequent trial boot')
    if not a.recover:
        assert current==cfg['boot_id_before'],'Starting boot changed'
        assert cfg['ps_partitions_identical']
        assert sha(Path('/etc/systemd/system/wcis-face-photo.service'))==cfg['photo_service_sha256']
        assert not Path('/download.bit').exists(),'download.bit would override BOOT'
        assert Path('/root/live.disabled').exists(),'Factory auto-run must remain disabled'
        assert sha(TASK/'candidate-BOOT.bin')==cfg['new_sha256']
        assert subprocess.run(['systemctl','is-active','--quiet','wcis-face-photo.service']).returncode==0
    assert not mounted(),'Boot partition already has an owner'
    mount=TASK/('sd-recover' if a.recover else 'sd-deploy');mount.mkdir(exist_ok=True)
    paused=False;is_mounted=False;changed=False
    lock=(Path(cfg['release'])/'npu.lock').open('a')
    try:
        if not a.recover:
            # Admission lock first: never stop a service in the middle of DMA.
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        run('systemctl','stop','wcis-face-photo.service');paused=True
        if not a.recover:
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit():continue
                try:exe=str((proc/'exe').resolve())
                except OSError:continue
                assert not any(exe.endswith('/'+name) for name in ('wcis_face_pl','wcis_face_pl_retained','wcis_face_npu','wcis_face_cached','wcis_jpeg','sdicamera+yolov5+hdmi')),'Hardware process remains'
        run('mount','-t','vfat','-o','rw,nosuid,nodev,noexec','/dev/mmcblk0p1',str(mount));is_mounted=True
        assert sha(mount/'fmqlmp-verify.dtb')==cfg['dtb_sha256']
        assert sha(mount/'uEnv.txt')==cfg['uenv_sha256']
        boot=mount/'BOOT.bin';backup=mount/'JPG1016.BAK'
        if a.recover:
            assert sha(boot) in (cfg['old_sha256'],cfg['new_sha256'])
            assert sha(backup)==cfg['old_sha256']
            pending=mount/'JPGRBACK.NEW';copy_new(backup,pending)
            assert sha(pending)==cfg['old_sha256'];os.replace(pending,boot);os.sync()
            assert sha(boot)==cfg['old_sha256'];report['rollback']=True
        else:
            assert sha(boot)==cfg['old_sha256']
            free=os.statvfs(mount).f_bavail*os.statvfs(mount).f_frsize
            assert free>2*(TASK/'candidate-BOOT.bin').stat().st_size+1024*1024
            if backup.exists():assert sha(backup)==cfg['old_sha256']
            else:copy_new(boot,backup)
            assert sha(backup)==cfg['old_sha256']
            pending=mount/'JPGBOOT.NEW';copy_new(TASK/'candidate-BOOT.bin',pending)
            assert sha(pending)==cfg['new_sha256'];os.replace(pending,boot);changed=True;os.sync()
            assert sha(boot)==cfg['new_sha256'];report['firmware_replaced']=True
        run('umount',str(mount));is_mounted=False
        if a.recover:run('systemctl','disable',UNIT+'.timer')
        else:
            run('systemctl','daemon-reload');run('systemctl','enable',UNIT+'.timer')
    except BaseException:
        if changed:
            if not is_mounted:
                run('mount','-t','vfat','-o','rw,nosuid,nodev,noexec','/dev/mmcblk0p1',str(mount));is_mounted=True
            pending=mount/'JPGERROR.NEW';copy_new(mount/'JPG1016.BAK',pending)
            os.replace(pending,mount/'BOOT.bin');os.sync();report['rollback']=True
        if is_mounted:run('umount',str(mount));is_mounted=False
        if paused and not a.recover:run('systemctl','start','wcis-face-photo.service')
        raise
    finally:
        lock.close()
        (TASK/('recovery.json' if a.recover else 'deployment.json')).write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)
    if a.recover:run('systemctl','reboot')
if __name__=='__main__':main()
