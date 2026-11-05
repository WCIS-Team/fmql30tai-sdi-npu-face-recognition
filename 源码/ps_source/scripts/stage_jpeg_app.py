"""Stage a checksum-pinned JPEG test app and read-only baseline snapshots."""
import argparse,hashlib,json,shlex,sys
from pathlib import Path
from ssh_transport import board_connection,ROOT
OUT=Path('D:/yzd/tmp/pl-jpeg-board-20261016')
FILES={
 'wcis_jpeg':OUT/'school-build/wcis_jpeg',
 'receive_jpeg_stream.py':ROOT/'npu_photo/receive_jpeg_stream.py',
 'frame_stream_protocol.py':ROOT/'npu_photo/frame_stream_protocol.py',
 'receive_video_stream.py':ROOT/'npu_photo/receive_video_stream.py'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app-only',action='store_true',help='Reuse the immutable pre-deployment snapshot; never overwrite it')
    args=p.parse_args()
    records=[dict(file=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for name,path in FILES.items()]
    token=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()[:12]
    app='/root/wcis-face/apps/jpeg-input-'+token
    task='/root/wcis-face/candidates/jpeg-20261016'
    remote=r'''
from pathlib import Path
import hashlib,json,os,shutil,subprocess,urllib.request
task=Path('/root/wcis-face/candidates/jpeg-20261016');task.mkdir(exist_ok=True)
def run(*args):
 p=subprocess.run(args,capture_output=True,text=True);return dict(code=p.returncode,out=p.stdout,err=p.stderr)
cfg=json.loads(Path('/root/wcis-face/video-stream-current.json').read_text())
unit=Path('/etc/systemd/system/wcis-face-photo.service').read_bytes()
library=''
for line in unit.decode().splitlines():
 if line.startswith('Environment=LD_LIBRARY_PATH='):library=line.split('=',2)[2].strip('"')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://192.168.1.113:8091/api/health',timeout=5) as r:health=json.loads(r.read())
report=dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),root=cfg['release'],
 photo_service_sha256=hashlib.sha256(unit).hexdigest(),library_path=library,health=health,
 photo_health_url=cfg['photo_health_url'],live_fdt_sha256=hashlib.sha256(Path('/sys/firmware/fdt').read_bytes()).hexdigest(),
 gallery_sha256={})
for p in Path('/mnt/wcis-emmc/wcis-face/galleries').rglob('*'):
 if p.is_file():
  report['gallery_sha256'][str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
existing=run('findmnt','-rn','-S','/dev/mmcblk0p1','-o','TARGET')['out'].strip()
if existing:raise RuntimeError('Boot partition already mounted; inspect owner')
mount=task/'sd-inspect';mount.mkdir(exist_ok=True)
assert run('mount','-t','vfat','-o','ro,nosuid,nodev,noexec','/dev/mmcblk0p1',str(mount))['code']==0
try:
 report['boot_files']={}
 for name in ['BOOT.bin','fmqlmp-verify.dtb','uEnv.txt']:
  data=(mount/name).read_bytes();dest=task/('before-'+name)
  if dest.exists():assert dest.read_bytes()==data,'Baseline changed; do not overwrite backup'
  else:dest.write_bytes(data)
  report['boot_files'][name]=dict(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
finally:assert run('umount',str(mount))['code']==0
(task/'before.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
'''
    with board_connection() as c:
        s=c.open_sftp()
        if args.app_only:
            baseline=json.loads((OUT/'board-before.json').read_text())
            with s.open('/etc/systemd/system/wcis-face-photo.service','rb') as f:
                assert hashlib.sha256(f.read()).hexdigest()==baseline['photo_service_sha256']
        else:
            _,out,err=c.exec_command("python3 - <<'PY'\n"+remote+'\nPY',timeout=40)
            data=out.read();error=err.read()
            if out.channel.recv_exit_status():raise RuntimeError(error.decode())
            baseline=json.loads(data)
            (OUT/'board-before.json').write_text(json.dumps(baseline,indent=2))
            for name in ('BOOT.bin','fmqlmp-verify.dtb','uEnv.txt'):
                s.get(task+'/before-'+name,str(OUT/('before-'+name)))
        try:s.mkdir(app)
        except FileExistsError:pass
        for name,local in FILES.items():
            remote_path=app+'/'+name
            try:
                with s.open(remote_path,'rb') as f:existing=f.read()
                if hashlib.sha256(existing).hexdigest()!=hashlib.sha256(local.read_bytes()).hexdigest():raise RuntimeError('Existing app differs')
            except FileNotFoundError:s.put(str(local),remote_path)
        s.chmod(app+'/wcis_jpeg',0o755)
        config=dict(app=app,files=records,root=baseline['root'],photo_service_sha256=baseline['photo_service_sha256'],
                    photo_health_url=baseline['photo_health_url'],library_path=baseline['library_path'])
        with s.open('/root/wcis-face/jpeg-stream-current.json','wb') as f:f.write(json.dumps(config,indent=2).encode())
        s.put(str(ROOT/'scripts/launch_jpeg_stream.py'),'/root/wcis-face/run-jpeg-stream.py')
        command="python3 - <<'PY'\nimport os,subprocess,json\nenv=os.environ.copy()\nenv['LD_LIBRARY_PATH']="+repr(baseline['library_path'])+"\np=subprocess.run(["+repr(app+'/wcis_jpeg')+",'--help'],env=env,capture_output=True,text=True)\nprint(json.dumps(dict(code=p.returncode,out=p.stdout,err=p.stderr)))\nPY"
        _,out,err=c.exec_command(command,timeout=15)
        help_result=json.loads(out.read());assert help_result['code']==0,help_result
        config['help']=help_result
        (OUT/'app-deployment.json').write_text(json.dumps(config,indent=2))
        print(json.dumps(dict(app=app,boot_id=baseline['boot_id'],boot_files=baseline['boot_files'],help=help_result),indent=2))
if __name__=='__main__':main()
