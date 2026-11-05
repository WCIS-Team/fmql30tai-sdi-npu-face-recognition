"""Read-only current board inspection; writes evidence only to --out locally."""
import argparse
import json
from pathlib import Path
import sys

REMOTE = r'''
import hashlib,json,subprocess,time,urllib.request,urllib.error
from pathlib import Path
def command(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=15)
 return dict(code=p.returncode,stdout=p.stdout,stderr=p.stderr)
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(port,path):
 try:
  with opener.open('http://127.0.0.1:'+str(port)+path,timeout=6) as f:return dict(status=f.status,body=json.load(f))
 except urllib.error.HTTPError as e:return dict(status=e.code,body=e.read().decode())
 except Exception as e:return dict(error=str(e))
r={'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'monotonic':time.monotonic()}
for name,path in [('config','/root/wcis-face/video-stream-current.json'),('marker','/root/wcis-face/hardware-review-required.json'),('control','/root/wcis-face/candidates/pad-owner-20261026/owner-current.json'),('startup','/root/wcis-face/candidates/face-camera-ready-20261020/deployment.json')]:
 try:r[name]=json.loads(Path(path).read_text())
 except Exception as e:r[name]={'error':str(e)}
r['units']=command(['systemctl','cat','wcis-face-photo.service','wcis-sdi-vpu-view.service','wcis-face-recording.service'])
r['services']=command(['systemctl','show','wcis-face-photo.service','wcis-sdi-vpu-view.service','wcis-face-recording.service','-p','Id','-p','ActiveState','-p','SubState','-p','MainPID'])
r['processes']=command(['ps','-eo','pid,ppid,etimes,pcpu,rss,comm,args'])
r['kernel']=command(['dmesg'])
r['journal']=command(['journalctl','-u','wcis-face-photo.service','--no-pager','-n','100'])
r['health']=get(8091,'/api/health');r['camera']=get(8091,'/api/camera/status');r['recorder']=get(8093,'/api/status')
r['hashes']=[]
cfg=r['config'];app=cfg.get('app')
if app:
 for row in cfg.get('files',[]):
  relative=Path(row['file'])
  if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unexpected managed file path')
  p=Path(app)/relative
  if p.is_file() and not p.is_symlink():r['hashes'].append(dict(path=str(p),size=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),expected=row['sha256']))
time.sleep(3)
r['camera_after']=get(8091,'/api/camera/status');r['monotonic_after']=time.monotonic()
print(json.dumps(r))
'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--direct-helper')
    args=p.parse_args();out=Path(args.out)
    if out.exists():raise FileExistsError(out)
    if args.direct_helper:
        sys.path.insert(0,args.direct_helper)
        from direct_board import direct_board_connection as connection
    else:
        from ssh_transport import board_connection as connection
    try:
        with connection() as c:
            i,o,e=c.exec_command('env PYTHONDONTWRITEBYTECODE=1 python3 -',timeout=55)
            i.write(REMOTE);i.channel.shutdown_write();raw=o.read();err=e.read()
            if o.channel.recv_exit_status():raise RuntimeError(err.decode(errors='replace'))
            result=json.loads(raw)
    except Exception as e:
        result={'connection_error':type(e).__name__+': '+str(e)}
    with out.open('x',encoding='utf-8') as f:f.write(json.dumps(result,indent=2))
    print(json.dumps({k:result.get(k) for k in ('connection_error','boot_id','health','camera','camera_after','recorder')},ensure_ascii=False,indent=2))
    if 'connection_error' in result:raise SystemExit(1)

if __name__=='__main__':main()
