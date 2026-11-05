"""Read-only post-test service, gallery and hardware-owner audit."""
import hashlib,json
from pathlib import Path
from ssh_transport import board_connection

TASK=Path('D:/yzd/tmp/pl-jpeg-board-20261016')

def main():
    before=json.loads((TASK/'board-before.json').read_text())
    accepted=json.loads((TASK/'accepted.json').read_text())
    code=r'''
from pathlib import Path
import fcntl,hashlib,json,os,subprocess,urllib.request
def run(*args):
 p=subprocess.run(args,capture_output=True,text=True)
 return dict(code=p.returncode,out=p.stdout.strip(),err=p.stderr.strip())
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://192.168.1.113:8091/api/health',timeout=5) as r:health=json.loads(r.read())
hardware=[];caches=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:exe=str((p/'exe').resolve())
 except OSError:continue
 if any(exe.endswith('/'+name) for name in ('wcis_jpeg','wcis_face_pl_retained','wcis_face_pl')):
  hardware.append(dict(pid=int(p.name),exe=exe))
 if exe.endswith('/wcis_face_cached'):caches.append(dict(pid=int(p.name),exe=exe))
gallery={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
 for p in Path('/mnt/wcis-emmc/wcis-face/galleries').rglob('*') if p.is_file()}
cfg=json.loads(Path('/root/wcis-face/jpeg-stream-current.json').read_text())
with (Path(cfg['root'])/'npu.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 lock_available=True
artifacts=[dict(file=q['file'],matches=hashlib.sha256((Path(cfg['app'])/q['file']).read_bytes()).hexdigest()==q['sha256']) for q in cfg['files']]
v=os.statvfs('/mnt/wcis-emmc')
marker=Path('/root/wcis-face/hardware-review-required.json')
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
q=dict(boot_id=boot,health=health,gallery_sha256=gallery,
 photo_service_sha256=hashlib.sha256(Path('/etc/systemd/system/wcis-face-photo.service').read_bytes()).hexdigest(),
 hardware_processes=hardware,idle_model_cache_workers=caches,hardware_lock_available=lock_available,
 tmpfs_leftovers=[str(p) for p in Path('/dev/shm').glob('wcis-jpeg-*')],
 quarantine_current_boot=marker.exists() and json.loads(marker.read_text()).get('boot_id')==boot,
 rollback_timer=run('systemctl','is-enabled','wcis-jpeg-trial-20261016.timer'),
 boot_partition_owner=run('findmnt','-rn','-S','/dev/mmcblk0p1'),
 emmc_free_bytes=v.f_bavail*v.f_frsize,app=cfg['app'],app_files=artifacts,
 recordings=[dict(path=str(p),bytes=p.stat().st_size) for p in Path('/mnt/wcis-emmc/wcis-face/recording-tests').glob('jpeg-*/output.mjpeg')],
 mmc_ios={str(p):p.read_text() for p in Path('/sys/kernel/debug').glob('mmc*/ios')})
print(json.dumps(q))
'''
    with board_connection() as c:
        _,out,err=c.exec_command("python3 - <<'PY'\n"+code+'\nPY',timeout=30)
        data=out.read();error=err.read()
        if out.channel.recv_exit_status():raise RuntimeError(error.decode())
    q=json.loads(data)
    assert q['boot_id']==accepted['boot_id']
    assert q['gallery_sha256']==before['gallery_sha256']
    assert q['photo_service_sha256']==before['photo_service_sha256']
    assert q['health']['status']=='ready' and q['health']['gallery_storage_ready']
    assert not q['hardware_processes'] and q['hardware_lock_available'] and not q['tmpfs_leftovers'] and not q['quarantine_current_boot']
    assert q['rollback_timer']['out']=='disabled' and not q['boot_partition_owner']['out']
    assert all(x['matches'] for x in q['app_files'])
    q.update(passed=True,gallery_unchanged=True,photo_service_unit_unchanged=True)
    (TASK/'final-state.json').write_text(json.dumps(q,indent=2))
    print(json.dumps(dict(passed=True,boot_id=q['boot_id'],health=q['health']['status'],
        gallery_files_unchanged=len(q['gallery_sha256']),emmc_free_bytes=q['emmc_free_bytes']),indent=2))

if __name__=='__main__':main()
