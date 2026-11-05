"""Install the photo interface after the board model verification has passed."""
import argparse,hashlib,json,sys,uuid
from pathlib import Path
from ssh_transport import board_connection,ROOT
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
out=ROOT/'outputs/photo-board-20261014'
parser=argparse.ArgumentParser();parser.add_argument('--update',action='store_true')
parser.add_argument('--pl-executable',type=Path,required=True,help='School-built wcis_face_pl for the verified FAC1 firmware')
parser.add_argument('--npu-cache-executable',type=Path,required=True,help='School-built resident model process backend')
parser.add_argument('--output-dir',type=Path,default=Path('D:/yzd/tmp')/('face-web-pl-deploy-'+uuid.uuid4().hex[:8]))
args=parser.parse_args()
if not args.pl_executable.is_file():raise RuntimeError('PL executable is missing; no CPU fallback')
if not args.npu_cache_executable.is_file():raise RuntimeError('Resident NPU executable is missing')
args.output_dir.mkdir(parents=True,exist_ok=False)
release=json.loads((out/'board-staged-release.json').read_text())['release']
files=[ROOT/'npu_photo'/n for n in ('recognize_photo.py','recognize_frame.py','serve_photos.py','gallery.py','persistent_gallery.py','migrate_gallery.py','run_photos.py','pl_preprocess.py','model_backend_runtime.py')]+[args.pl_executable,args.npu_cache_executable,ROOT/'photo_reference/web/index.html']
app='/root/wcis-face/apps/photo-cache-'+hashlib.sha256(b''.join(p.read_bytes() for p in files)).hexdigest()[:12]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
with board_connection() as client:
    s=client.open_sftp()
    verification=json.loads(s.open(release+'/run-01/verification.json','r').read())
    assert verification['all_passed']
    _,o,_=client.exec_command('ss -ltnp | grep ":8091 "',timeout=10)
    port=o.read().decode(errors='replace')
    target='/etc/systemd/system/wcis-face-photo.service'
    previous=None
    if args.update:
        previous=s.open(target,'r').read().decode()
        assert 'Description=WCIS photo face recognition' in previous and ' --root '+release+' ' in previous
        _,o,_=client.exec_command('systemctl is-active wcis-face-photo.service',timeout=10)
        assert o.read().decode().strip()=='active'
    else:assert not port,'Port 8091 is already owned; inspect before changing it'
    def mkdir(p):
        try:s.stat(p)
        except FileNotFoundError:
            mkdir(p.rsplit('/',1)[0]);s.mkdir(p)
    mkdir(app)
    if previous:
        with s.open(app+'/previous-unit.txt','w') as f:f.write(previous)
        with s.open(app+'/previous-index.html','wb') as f:f.write(s.open(release+'/run-01/site/index.html','rb').read())
    checks=[]
    for p in files:
        dest=app+'/'+p.name;s.put(str(p),dest)
        assert hashlib.sha256(s.open(dest,'rb').read()).hexdigest()==sha(p)
        checks.append({'file':dest,'sha256':sha(p)})
    unit='[Unit]\nDescription=WCIS photo face recognition\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nWorkingDirectory='+app+'\nExecStart=/usr/bin/python3 -u '+app+'/serve_photos.py --root '+release+' --site '+release+'/run-01/site --host 192.168.1.113 --port 8091\nRestart=on-failure\nRestartSec=5\nKillMode=mixed\nTimeoutStopSec=75\nEnvironment=OPENCV_IO_MAX_IMAGE_PIXELS=16000000\n\n[Install]\nWantedBy=multi-user.target\n'
    s.chmod(app+'/'+args.pl_executable.name,0o755)
    s.chmod(app+'/'+args.npu_cache_executable.name,0o755)
    unit=unit.replace('--port 8091','--port 8091 --pl-executable '+app+'/'+args.pl_executable.name+' --npu-cache-executable '+app+'/'+args.npu_cache_executable.name)
    if previous:
        # Preserve verified storage UUID, required mount and runtime settings.
        # An application update must never silently switch personnel back to SD.
        old_app=next(x.split('=',1)[1] for x in previous.splitlines() if x.startswith('WorkingDirectory='))
        unit=previous.replace(old_app,app)
        import re
        unit=re.sub(r'--pl-executable \S+','--pl-executable '+app+'/'+args.pl_executable.name,unit)
        unit=re.sub(r'--npu-cache-executable \S+','--npu-cache-executable '+app+'/'+args.npu_cache_executable.name,unit)
    if not args.update:
        try:s.stat(target);raise RuntimeError('Service unit already exists; inspect before overwriting')
        except FileNotFoundError:pass
    _,o,_=client.exec_command('pgrep -x wcis_face_npu',timeout=10)
    assert not o.read().strip(),'Wait for the active NPU request before updating'
    if args.update:
        _,o,e=client.exec_command('systemctl stop wcis-face-photo.service',timeout=85)
        assert o.channel.recv_exit_status()==0
    s.put(str(files[-1]),release+'/run-01/site/index.html')
    with s.open(target,'w') as f:f.write(unit)
    _,o,e=client.exec_command('systemctl daemon-reload && systemctl enable --now wcis-face-photo.service && systemctl is-active wcis-face-photo.service',timeout=20)
    result=o.read().decode(errors='replace')+e.read().decode(errors='replace');code=o.channel.recv_exit_status()
    print(result,flush=True);assert code==0
    report={'release':release,'app':app,'service':'wcis-face-photo.service','url':'http://192.168.1.113:8091/','backend':'zg330_npu_pl_and_host','model_lifecycle':'resident_process_per_model','files':checks,'validation':verification,'unit':unit}
    if args.update:
        (args.output_dir/'gallery-interface-deployment.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    else:(args.output_dir/'photo-interface-deployment.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(report['url'],flush=True)
