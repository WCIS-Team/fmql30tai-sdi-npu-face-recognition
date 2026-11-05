"""Deploy the supplied September PL platform for the user's face project.

The three PS payloads are identical to the current board image. Keep verified
local and SD backups, replace atomically, unmount, then request a normal reboot.
"""
import hashlib
import json
from pathlib import Path
import sys
from ssh_transport import ROOT, board_connection

sys.stdout.reconfigure(encoding='utf-8',errors='replace')
OLD='0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca'
NEW='b87024cef9ee06936ac7123c2c976552beb0938d255abf27036dc9bbafeddc94'
OUT=ROOT/'outputs/redeploy-20261014'
SOURCE=OUT/'vendor/BIT/30tai_detpost/BOOT.bin'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==NEW
assert json.loads((OUT/'partition-validation.json').read_text())['ps_partitions_identical']
TASK='/root/wcis-face/redeploy-20261014/boot-b87024ce'
REMOTE=r'''
from pathlib import Path
import hashlib,json,os,shutil,subprocess
here=Path(__file__).resolve().parent
assert str(here)=='/root/wcis-face/redeploy-20261014/boot-b87024ce'
old='0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca'
new='b87024cef9ee06936ac7123c2c976552beb0938d255abf27036dc9bbafeddc94'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def copy(src,dst):
 with src.open('rb') as r,dst.open('xb') as w:
  shutil.copyfileobj(r,w);w.flush();os.fsync(w.fileno())
report={'firmware_replaced':False,'old_sha256':old,'new_sha256':new,'ps_payloads_identical':True}
def save():(here/'receipt.json').write_text(json.dumps(report,indent=2))
assert sha(here/'BOOT.candidate.bin')==new
if subprocess.run(['findmnt','-rn','-S','/dev/mmcblk0p1'],capture_output=True).stdout.strip():raise RuntimeError('Boot partition already mounted')
for p in Path('/proc').iterdir():
 if p.name.isdigit():
  try:exe=str((p/'exe').resolve())
  except OSError:continue
  if exe.endswith('/wcis_face_npu') or exe.endswith('/sdicamera+yolov5+hdmi'):raise RuntimeError('Hardware process is running')
mount=here/'sd';mount.mkdir(exist_ok=True)
subprocess.run(['mount','-t','vfat','-o','rw,nosuid,nodev,noexec','/dev/mmcblk0p1',str(mount)],check=True)
boot=mount/'BOOT.bin';backup=mount/'FB202614.BAK';pending=mount/'FACEBOOT.BIN';changed=False
try:
 assert sha(boot)==old,'Starting BOOT differs from reviewed image'
 if backup.exists():assert sha(backup)==old
 else:copy(boot,backup)
 assert sha(backup)==old
 if (here/'BOOT.before.bin').exists():assert sha(here/'BOOT.before.bin')==old
 else:copy(boot,here/'BOOT.before.bin')
 assert sha(here/'BOOT.before.bin')==old
 copy(here/'BOOT.candidate.bin',pending);assert sha(pending)==new
 os.replace(pending,boot);changed=True;os.sync();assert sha(boot)==new
 report.update(firmware_replaced=True,sd_backup=backup.name,final_sha256=sha(boot),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
 disabled=Path('/root/live.disabled');report['live_disabled_before']=disabled.exists()
 disabled.touch();save()
except BaseException as error:
 report['error_type']=type(error).__name__
 if changed:
  rollback=mount/'FBROLL.BIN';copy(backup,rollback);assert sha(rollback)==old;os.replace(rollback,boot);os.sync()
  report['rolled_back']=sha(boot)==old;report['firmware_replaced']=not report['rolled_back']
 save();raise
finally:subprocess.run(['umount',str(mount)],check=True)
report['boot_partition_unmounted']=True;save();print(json.dumps(report),flush=True)
'''
with board_connection() as client:
 s=client.open_sftp()
 try:s.mkdir(TASK)
 except OSError:s.stat(TASK)
 s.put(str(SOURCE),TASK+'/BOOT.candidate.bin')
 with s.open(TASK+'/deploy.py','wb') as f:f.write(REMOTE.encode())
 _,stdout,_=client.exec_command('python3 '+TASK+'/deploy.py',timeout=30)
 stdout.channel.set_combine_stderr(True);log=stdout.read().decode(errors='replace');code=stdout.channel.recv_exit_status();print(log,flush=True)
 (OUT/'boot-deploy.log').write_text(log,encoding='utf-8')
 assert code==0
 with s.open(TASK+'/receipt.json','r') as f:receipt=json.loads(f.read())
 assert receipt['firmware_replaced'] and receipt['boot_partition_unmounted']
 receipt['reboot_requested']=True;(OUT/'boot-deployment.json').write_text(json.dumps(receipt,indent=2))
 client.exec_command('systemctl reboot',timeout=5)
 print('Verified new PL platform written; reboot requested.',flush=True)
