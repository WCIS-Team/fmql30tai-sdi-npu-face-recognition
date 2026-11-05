"""Boot admission for a fresh-board handoff. No network or partition changes."""
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(*a):return subprocess.run(a,check=True,capture_output=True,text=True,timeout=30).stdout
def main():
    q=json.loads((R/'deployment.json').read_text());app=Path(q['app'])
    if Path('/download.bit').exists() or not Path('/root/live.disabled').exists():raise RuntimeError('Conflicting vendor autoload configuration')
    cfgpath=Path('/root/wcis-face/video-stream-current.json');cfg=json.loads(cfgpath.read_text())
    if cfg['app']!=str(app):raise RuntimeError('App configuration changed')
    marker=Path('/root/wcis-face/hardware-review-required.json')
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if marker.exists() and json.loads(marker.read_text()).get('boot_id')==boot:raise RuntimeError('Hardware review required')
    for x in cfg['files']:
        if sha(app/x['file'])!=x['sha256']:raise RuntimeError('App checksum mismatch: '+x['file'])
    mounted=subprocess.run(['findmnt','-rn','-S',q['sd_device']],capture_output=True,text=True,check=False)
    if mounted.stdout.strip():raise RuntimeError('SD boot partition already mounted; review and unmount first')
    run('mount','-t','vfat','-o','ro,nosuid,nodev,noexec',q['sd_device'],str(R/'sd'))
    try:
        files={n:sha(R/'sd'/n) for n in q['boot_files']}
        if files!=q['boot_files']:raise RuntimeError('BOOT/DTB/uEnv differs from delivered baseline')
    finally:run('umount',str(R/'sd'))
    # This confirms boot-medium contents for admission, not an inference result.
    proof=R/'live/boot-proof.json';proof.write_text(json.dumps(dict(boot_id=boot,boot_files=files)))
    cfg['verified_boot_id']=boot;cfg['photo_service_sha256']=sha(Path('/etc/systemd/system/wcis-face-photo.service'))
    pending=cfgpath.with_suffix('.install.tmp');pending.write_text(json.dumps(cfg,indent=2));pending.replace(cfgpath)
    print('Boot-medium and app integrity passed; hardware function still requires acceptance')
if __name__=='__main__':main()
