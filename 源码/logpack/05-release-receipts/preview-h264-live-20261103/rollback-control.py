"""Task-local staged visual candidate switch; never reboot or clear quarantine."""
import json,hashlib,shutil,subprocess,time,sys,shlex,urllib.request
from pathlib import Path
T=Path(__file__).parent
CFG=Path('/root/wcis-face/video-stream-current.json')
DEP=Path('/root/wcis-face/candidates/face-camera-ready-20261020/deployment.json')
CONTROL=Path('/root/wcis-face/candidates/pad-owner-20261026/owner-current.json')
UNITS=['wcis-face-photo.service','wcis-sdi-vpu-view.service','wcis-face-recording.service']
MARKER=Path('/root/wcis-face/hardware-review-required.json')
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def api(port,path,data=None):
 req=urllib.request.Request('http://127.0.0.1:'+str(port)+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
 with op.open(req,timeout=15) as f:return json.load(f)
def run(*args):return subprocess.run(args,check=True,capture_output=True,text=True,timeout=100).stdout
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def save(p,q):
 p=Path(p);tmp=p.with_suffix('.pending');tmp.write_text(json.dumps(q,indent=2));tmp.replace(p)
def boot():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
def safe():
 assert boot()==meta['boot_id'],'Boot changed'
 assert not MARKER.exists() or json.loads(MARKER.read_text()).get('boot_id')!=boot(),'Current boot quarantined'
def process_exists(pid):
 try:return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[0] not in ('Z','X')
 except FileNotFoundError:return False
def others():
 rows=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   argv=(p/'cmdline').read_bytes().split(b'\0')
   if any(a.endswith((b'/voice_gateway.py',b'/klar_asr.py')) for a in argv):rows.append((int(p.name),(p/'stat').read_text().rsplit(')',1)[1].split()[19]))
  except OSError:pass
 return sorted(rows)
def hashes(root):
 return {str(p):sha(p) for p in Path(root).rglob('*') if p.is_file() and not p.is_symlink() and (p.suffix in ('.mp4','.mjpeg') or p.name.endswith(('.frames.jsonl','.json'))) and p.name not in ('service-stop.json',) and not p.name.endswith('.compression.json') and '.compression-work' not in p.parts}
def wait_ready():
 end=time.monotonic()+45
 while time.monotonic()<end:
  try:
   h=api(8091,'/api/health');s=api(8091,'/api/camera/status')
   if h.get('hardware_admission_ready') and h.get('model_cache_ready') and s.get('ready') and s.get('boot_id')==boot():return s
  except Exception:pass
  time.sleep(.3)
 raise RuntimeError('Visual readiness timeout')
def start():
 run('systemctl','start',UNITS[0]);first=wait_ready()
 run('systemctl','start',UNITS[1]);run('systemctl','start',UNITS[2])
 end=time.monotonic()+30
 while time.monotonic()<end:
  try:
   r=api(8093,'/api/status');s=api(8091,'/api/camera/status')
   if r['source_ready'] and r['error'] is None and s['session']==first['session'] and s['encoded']>first['encoded']:
    info=api(8092,'/h264/manifest.json?session='+s['session'])
    if len(info['segments'])<4:continue
    expected=meta.get('segment_seconds',0.5) if action=='switch' else meta.get('prior_seconds',1.0)
    if any(abs(x['duration']-expected)>0.002 for x in info['segments'][-4:]):
     raise ValueError('Actual fragment cadence differs from requested cadence')
    ctl=json.loads(CONTROL.read_text());root=Path(ctl['directory']);hls=root/'hls'
    if action=='switch' and expected<1:
     assert ('WCIS_MVX_GOP_APPLIED '+str(round(30*expected))) in (root/'h264-encoder.log').read_text(),'Missing vendor GOP receipt'
    evidence=[]
    for item in info['segments'][-4:]:
     sample=out/(action+'-'+item['name']+'.mp4');sample.write_bytes((hls/'init.mp4').read_bytes()+(hls/item['name']).read_bytes())
     run('ffmpeg','-v','error','-i',str(sample),'-f','null','-')
     probe=json.loads(run('ffprobe','-v','error','-select_streams','v','-show_frames','-show_entries','frame=key_frame,pict_type','-of','json',str(sample)))
     assert len(probe['frames'])==round(30*expected) and probe['frames'][0]['key_frame']==1,probe
     capture=json.loads((hls/item['name']).with_suffix('.capture.json').read_text())
     assert capture['samples']==round(30*expected) and capture['session']==s['session'] and capture['boot_id']==boot()
     evidence.append(dict(segment=item,capture=capture,probe=probe))
    if action=='switch' and label.endswith('live'):
     live=api(8091,'/api/camera/h264/live-status');assert live['ready'] and live['session']==s['session'],live
    save(out/(action+'-media-gate.json'),evidence);return s
  except Exception as error:save(out/(action+'-last-media-error.json'),dict(error=repr(error)))
  time.sleep(.3)
 raise RuntimeError('Recorder or advancing media readiness timeout')
def stop(app):
 ctl=json.loads(CONTROL.read_text());pid=ctl['pid'];s=api(8091,'/api/camera/status');children=[s.get(k) for k in ('encoder_pid','muxer_pid')]
 api(8093,'/api/mode',{'mode':'off'})
 deadline=time.monotonic()+20
 while time.monotonic()<deadline:
  q=api(8093,'/api/status')
  if q['state']=='idle' and q['current'] is None and not q['queue_bytes']:break
  time.sleep(.2)
 else:raise RuntimeError('Recording did not finish')
 for u in reversed(UNITS):run('systemctl','stop',u)
 receipt=json.loads((Path(app)/(str(pid)+'-owner-stop.json')).read_text())
 assert receipt['sdk_closed'] and not receipt['camera_pending'] and receipt['exit_code']==0,receipt
 assert receipt.get('boot_id',boot())==boot()
 assert not any(process_exists(p) for p in [pid]+[p for p in children if p]),'Old worker still alive'
 safe();return receipt

action=sys.argv[1]
if action=='prepare':
 label=sys.argv[2];out=T/label;out.mkdir(exist_ok=False)
 cfg=json.loads(CFG.read_text());old=Path(cfg['app']);recunit=Path('/etc/systemd/system')/UNITS[2]
 units={u:(Path('/etc/systemd/system')/u).read_text() for u in UNITS}
 args=shlex.split(next(x[10:] for x in units[UNITS[2]].splitlines() if x.startswith('ExecStart=')))
 rec=next(Path(x).parent for x in args if x.endswith('/recording_service.py'))
 main=Path('/root/wcis-face/apps')/('camera-low-latency-'+label)
 newrec=Path('/root/wcis-face/candidates')/('recording-low-latency-'+label)
 assert not main.exists() and not newrec.exists()
 status=api(8093,'/api/status')
 assert status['current'] is None,'Wait for current recording to finish before freezing'
 meta=dict(boot_id=boot(),label=label,old_app=str(old),new_app=str(main),old_recorder=str(rec),new_recorder=str(newrec),units=units,cfg=cfg,dep=json.loads(DEP.read_text()),mode=status['mode'],other_processes=others())
 meta['segment_seconds']=1.0 if label.endswith(('webjpeg','live')) else 0.2 if label.endswith('mvx6') else 0.5
 meta['prior_seconds']=float(next((line.split('=',2)[2] for line in units[UNITS[0]].splitlines() if line.startswith('Environment=WCIS_H264_SEGMENT_SECONDS=')),'1'))
 safe()
 for x in cfg['files']:assert sha(old/x['file'])==x['sha256'],x['file']
 main.mkdir()
 copy_files=[x for x in cfg['files'] if not (label.endswith('webjpeg') and x['file']=='libwcis_mvx_gop.so')]
 for x in copy_files:
  p=main/x['file'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/x['file'],p)
 # Recorder runtime closure from the current idle-compression release; preserve its code.
 manifest=json.loads((T/'recorder-manifest.json').read_text())
 if manifest['app']!=str(rec):
  prior=[json.loads(p.read_text()) for p in T.glob('*/prepared.json')]
  prior=[q for q in prior if q.get('new_recorder')==str(rec)]
  assert len(prior)==1,'No unique frozen recorder manifest'
  manifest=dict(app=str(rec),files=prior[0]['recorder_files'])
 newrec.mkdir()
 for x in manifest['files']:
  assert sha(rec/x['file'])==x['sha256'],x['file']
  p=newrec/x['file'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(rec/x['file'],p)
 if label.endswith('live'):
  for name in ('external_h264.py','h264_player.js','h264_live.py','serve_photos.py','vpu_live_server.py'):shutil.copy2(T/'stage'/name,main/name)
 elif label.endswith('webjpeg'):
  for name in ('external_h264.py','h264_media.py','h264_fragments.py','h264_player.js','vpu_live_server.py','serve_photos.py','wcis_camera_owner','camera-owner-build.json'):shutil.copy2(T/'web-stage'/name,main/name)
  (main/'wcis_camera_owner').chmod(0o755)
  for name in ('h264_media.py','h264_fragments.py','vpu_live_server.py'):shutil.copy2(T/'web-recorder-stage'/name,newrec/name)
 else:
  for name in ('external_h264.py','h264_media.py','h264_fragments.py','h264_player.js'):shutil.copy2(T/'stage'/name,main/name)
  shutil.copy2(T/'libwcis_mvx_gop.so',main/'libwcis_mvx_gop.so')
  for name in ('h264_media.py','h264_fragments.py'):shutil.copy2(T/'stage'/name,newrec/name)
 meta['files']=[dict(file=x['file'],sha256=sha(main/x['file'])) for x in copy_files]
 if not label.endswith(('webjpeg','live')) and not any(x['file']=='libwcis_mvx_gop.so' for x in meta['files']):meta['files'].append(dict(file='libwcis_mvx_gop.so',sha256=sha(main/'libwcis_mvx_gop.so')))
 if label.endswith('live'):meta['files'].append(dict(file='h264_live.py',sha256=sha(main/'h264_live.py')))
 meta['recorder_files']=[dict(file=x['file'],sha256=sha(newrec/x['file'])) for x in manifest['files']]
 meta['gallery_hashes']={str(p):sha(p) for p in Path('/mnt/wcis-emmc/wcis-face/galleries').rglob('*') if p.is_file()}
 meta['recording_hashes']=hashes('/mnt/wcis-emmc/wcis-face/recordings')
 meta['kernel']=run('dmesg')
 save(out/'prepared.json',meta)
 print(json.dumps({'prepared':label,'main_files':len(meta['files']),'recorder_files':len(meta['recorder_files']),'mode':meta['mode']}))
elif action in ('switch','rollback'):
 label=sys.argv[2];out=T/label;meta=json.loads((out/'prepared.json').read_text());safe()
 assert others()==[tuple(x) for x in meta['other_processes']],'Other workloads changed before switch'
 report={'passed':False,'action':action,'safe_to_reopen':False};save(out/(action+'.json'),report)
 app=meta['old_app'] if action=='switch' else meta['new_app']
 report['stop']=stop(app);report['safe_to_reopen']=True;save(out/(action+'.json'),report)
 try:
  if action=='switch':
   uploads=Path(meta['old_app'])/'site'/'uploads'
   if uploads.is_dir() and not uploads.is_symlink():shutil.copytree(uploads,Path(meta['new_app'])/'site'/'uploads',dirs_exist_ok=True)
   for u,text in meta['units'].items():
    text=text.replace(meta['old_app'],meta['new_app']).replace(meta['old_recorder'],meta['new_recorder'])
    if u==UNITS[0]:
     text='\n'.join(line for line in text.split('\n') if not line.startswith('Environment=WCIS_H264_SEGMENT_SECONDS='))
     text=text.replace('[Service]','[Service]\nEnvironment=WCIS_H264_SEGMENT_SECONDS='+str(meta['segment_seconds']))
     if label.endswith('webjpeg'):
      text=text.replace('[Service]','[Service]\nEnvironment=WCIS_WEB_PREVIEW_JPEG_FPS=15')
      old_sha=next(x['sha256'] for x in meta['cfg']['files'] if x['file']=='wcis_camera_owner')
      new_sha=next(x['sha256'] for x in meta['files'] if x['file']=='wcis_camera_owner')
      text=text.replace('--camera-owner-sha256 '+old_sha,'--camera-owner-sha256 '+new_sha)
    (Path('/etc/systemd/system')/u).write_text(text)
   cfg=dict(meta['cfg'],app=meta['new_app'],files=meta['files'],verification=str(out/'acceptance.json'))
   dep=dict(meta['dep'],app=meta['new_app']);save(CFG,cfg);save(DEP,dep)
  else:
   for u,text in meta['units'].items():(Path('/etc/systemd/system')/u).write_text(text)
   save(CFG,meta['cfg']);save(DEP,meta['dep'])
  run('systemctl','daemon-reload');report['safe_to_reopen']=False
  report['camera']=start();report['passed']=True
  api(8093,'/api/mode',{'mode':meta['mode']});safe()
  assert others()==[tuple(x) for x in meta['other_processes']],'Other workload process changed'
 except BaseException as e:
  report['error']=repr(e);save(out/(action+'.json'),report)
  # Do not reopen devices automatically without the candidate's own successful close.
  raise
 finally:save(out/(action+'.json'),report)
 print(json.dumps(report))
else:raise ValueError(action)
