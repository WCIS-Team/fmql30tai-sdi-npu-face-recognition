"""Accept the trial only after real JPEG decode/golden proof and NPU regression."""
import argparse,hashlib,json
from pathlib import Path
from ssh_transport import board_connection
TASK=Path('D:/yzd/tmp/pl-jpeg-board-20261016')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    perf=json.loads((a.run/'performance.json').read_text())
    face=json.loads((TASK/'face-after-summary.json').read_text())
    proof=json.loads((TASK/'boot-candidate/manifest.json').read_text())
    assert perf['passed'] and perf['first_full_frame_coefficient_max_error']<=1 and face['model_outputs_equal_before']
    assert perf['board_boot_id']==face['board_boot_id'],'Face and JPEG proofs must come from this same boot'
    expected=dict(boot_id=perf['board_boot_id'],boot_sha256=proof['boot_sha256'],
        jpeg_performance_sha256=hashlib.sha256((a.run/'performance.json').read_bytes()).hexdigest(),
        face_regression_sha256=hashlib.sha256((TASK/'face-after-summary.json').read_bytes()).hexdigest())
    code='''
from pathlib import Path
import hashlib,json,os,subprocess,urllib.request
task=Path('/root/wcis-face/candidates/jpeg-20261016')
expected=json.loads((task/'accept-input.json').read_text())
cfg=json.loads((task/'deploy.json').read_text())
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot==expected['boot_id'] and boot!=cfg['boot_id_before']
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://192.168.1.113:8091/api/health',timeout=5) as r:health=json.loads(r.read())
assert health['status']=='ready' and health['gallery_storage_ready'] and health['preprocessing_backend']=='FAC1_customop_PL'
mount=task/'sd-accept';mount.mkdir(exist_ok=True)
assert not subprocess.run(['findmnt','-rn','-S','/dev/mmcblk0p1'],capture_output=True).stdout.strip()
subprocess.run(['mount','-t','vfat','-o','ro,nosuid,nodev,noexec','/dev/mmcblk0p1',str(mount)],check=True)
try:
 assert hashlib.sha256((mount/'BOOT.bin').read_bytes()).hexdigest()==expected['boot_sha256']
 assert hashlib.sha256((mount/'fmqlmp-verify.dtb').read_bytes()).hexdigest()==cfg['dtb_sha256']
 assert hashlib.sha256((mount/'uEnv.txt').read_bytes()).hexdigest()==cfg['uenv_sha256']
finally:subprocess.run(['umount',str(mount)],check=True)
expected['refreshed_configs']=[]
for name in ('video-stream-current.json','replay-current.json'):
 path=Path('/root/wcis-face')/name
 if not path.exists():continue
 data=path.read_bytes();q=json.loads(data)
 assert q['release']==cfg['release']
 backup=task/('before-'+name)
 if not backup.exists():backup.write_bytes(data)
 old=q['verified_boot_id'];q['verified_boot_id']=boot
 pending=path.with_name(path.name+'.jpeg-new')
 with pending.open('x') as f:f.write(json.dumps(q,indent=2));f.flush();os.fsync(f.fileno())
 os.replace(pending,path)
 expected['refreshed_configs'].append(dict(file=name,before_boot_id=old,after_boot_id=boot))
expected['health']=health
(task/'accepted.json').write_text(json.dumps(expected,indent=2))
subprocess.run(['systemctl','disable','--now','wcis-jpeg-trial-20261016.timer'],check=True)
print(json.dumps(expected))
'''
    with board_connection() as c:
        s=c.open_sftp()
        with s.open('/root/wcis-face/candidates/jpeg-20261016/accept-input.json','wb') as f:f.write(json.dumps(expected).encode())
        _,out,err=c.exec_command("python3 - <<'PY'\n"+code+'\nPY',timeout=35)
        data=out.read();error=err.read()
        if out.channel.recv_exit_status():raise RuntimeError(error.decode())
        accepted=json.loads(data);(TASK/'accepted.json').write_text(json.dumps(accepted,indent=2))
        print(json.dumps(dict(accepted=True,boot_id=accepted['boot_id'],health=accepted['health']['status']),indent=2))
if __name__=='__main__':main()
