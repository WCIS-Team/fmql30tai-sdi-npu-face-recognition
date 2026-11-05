"""Check the bounded SDK allocation before starting any JPEG CustomOp."""
import argparse,json
from pathlib import Path
from ssh_transport import board_connection

REMOTE = r'''
from pathlib import Path
import fcntl,hashlib,json,os,subprocess,urllib.request,time
cfg=json.loads(Path('/root/wcis-face/jpeg-stream-current.json').read_text())
app=Path(cfg['app']);root=Path(cfg['root'])
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
marker=Path('/root/wcis-face/hardware-review-required.json')
assert not marker.exists() or json.loads(marker.read_text()).get('boot_id')!=boot,'Hardware quarantined'
for item in cfg['files']:
 assert hashlib.sha256((app/item['file']).read_bytes()).hexdigest()==item['sha256']
unit=Path('/etc/systemd/system/wcis-face-photo.service')
assert hashlib.sha256(unit.read_bytes()).hexdigest()==cfg['photo_service_sha256']
active=subprocess.run(['systemctl','is-active','--quiet','wcis-face-photo.service']).returncode==0
report=dict(boot_id=boot,passed=False,customop_started=False)
paused=False
with (root/'npu.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  if active:
   subprocess.run(['systemctl','stop','wcis-face-photo.service'],check=True,timeout=75)
   paused=True
  env=os.environ.copy()
  if cfg.get('library_path'):env['LD_LIBRARY_PATH']=cfg['library_path']
  # No timeout kill: retain ownership until the SDK process has exited.
  result=subprocess.run([str(app/'wcis_jpeg'),'--memory-probe'],capture_output=True,text=True,env=env)
  report.update(code=result.returncode,out=result.stdout,err=result.stderr)
  lines=[x[len('WCIS_JPEG_RESULT '):] for x in result.stdout.splitlines() if x.startswith('WCIS_JPEG_RESULT ')]
  if result.returncode==0 and len(lines)==1:
   probe=json.loads(lines[0]);report['probe']=probe
   report['passed']=(probe['status']=='memory_probe' and not probe['customop_started']
    and len(probe['results'])==4 and all(x['mismatches']==0 and x['second_read_mismatches']==0
    and x['changed_between_reads']==0 for x in probe['results']))
 finally:
  if not report['passed']:
   marker.write_text(json.dumps(dict(boot_id=boot,reason='Bounded SDK DDR preflight failed')))
if report['passed'] and paused:
 subprocess.run(['systemctl','start','wcis-face-photo.service'],check=True,timeout=45)
if report['passed'] and active:
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 for _ in range(100):
  try:
   with opener.open(cfg['photo_health_url'],timeout=2) as response:health=json.loads(response.read())
   if health.get('status')=='ready':break
  except OSError:pass
  time.sleep(.25)
 else:raise RuntimeError('Photo service did not recover')
 report['photo_restored']=True
print(json.dumps(report))
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    with board_connection() as client:
        _,stdout,stderr=client.exec_command("python3 - <<'PY'\n"+REMOTE+'\nPY',timeout=100)
        data=stdout.read();error=stderr.read()
        if stdout.channel.recv_exit_status():raise RuntimeError(error.decode())
    report=json.loads(data)
    args.out.write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(passed=report['passed'],boot_id=report['boot_id'],
        customop_started=False,photo_restored=report.get('photo_restored',False)),indent=2))
    if not report['passed']:raise SystemExit(3)

if __name__=='__main__':main()
