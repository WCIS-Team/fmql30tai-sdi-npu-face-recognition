"""Finite, isolated board acceptance; restore formal services after clean drain.

No FPGA programming, no guessed physical addresses, no permanent service switch.
Run only after staging a checked school build and the existing Python sources.
"""
from pathlib import Path
import argparse,hashlib,json,os,shlex,shutil,subprocess,sys,tempfile,threading,time

parser=argparse.ArgumentParser();parser.add_argument('--task',type=Path,required=True);args=parser.parse_args()
T=args.task.resolve();sys.path.insert(0,str(T/'src'));sys.path.insert(0,str(T/'viewer'))
import cv2
import numpy as np
from camera_interlock import CameraInterlock
from camera_owner_runtime import CameraOwner
from gallery import Gallery
from model_backend_runtime import ModelBackend
from pl_preprocess import PLPreprocessor
from recognize_frame import infer_prepared
from run_photos import save,sha
from vpu_live_server import Frames,handler
from http.server import ThreadingHTTPServer

assert T.parent==Path('/root/wcis-face/candidates') and T.name=='face-camera-owner-20261020'
cfg=json.loads(Path('/root/wcis-face/video-stream-current.json').read_text());app=Path(cfg['app']);release=Path(cfg['release'])
old=CameraInterlock('/root/wcis-face/candidates/face-camera-ready-20261020/camera-control.json',release);boot=old.guard()
assert cfg['verified_boot_id']==boot and old.config['boot_sha256']=='f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297'
for record in cfg['files']:assert sha(app/record['file'])==record['sha256']
receipt=json.loads((T/'build-receipt.json').read_text());assert sha(T/'wcis_camera_owner')==receipt['binary_sha256']
def run(*a,timeout=85):return subprocess.run(a,capture_output=True,text=True,check=True,timeout=timeout).stdout.strip()
def gallery_hashes():return {str(p):sha(p) for p in Path('/mnt/wcis-emmc/wcis-face/galleries').rglob('*') if p.is_file()}
before=dict(boot_id=boot,gallery=gallery_hashes(),files={n['file']:sha(app/n['file']) for n in cfg['files']})
save(T/'before.json',before)
gallery_path=Path('/mnt/wcis-emmc/wcis-face/galleries')/sha(release/'models.json')[:16]/'gallery.json'
db=json.loads(gallery_path.read_text());templates=Gallery.templates_from_db(type('Readonly',(),dict(pipeline=db['pipeline_id']))(),db)
config=json.loads((release/'models.json').read_text());evidence=json.loads((release/'run-01/verification.json').read_text())
assert templates['pipeline_id']==evidence['pipeline_id'] and evidence['all_passed']
# Reuse only the prior service's non-secret library path; never dump environment.
for line in Path('/etc/systemd/system/wcis-face-photo.service').read_text().splitlines():
 if line.startswith('Environment='):
  for pair in shlex.split(line[len('Environment='):]):
   key,_,value=pair.partition('=')
   if key=='LD_LIBRARY_PATH':os.environ[key]=value

owner=None;server=None;monitor_thread=None;monitor_stop=threading.Event();observed=[];comparisons=[];cases=[];selected=[]
result=dict(passed=False,boot_id=boot,prototype=True)
def signatures(q):
 return dict(face_count=q['face_count'],faces=q['faces'],status=q['status'],detector=[r['sha256'] for r in q['timing']['detector']['outputs']],
             identities=[dict(name=p['name'],status=p['status'],similarity=p['similarity'],feature=[r['sha256'] for r in p['timing']['recognizer']['outputs']]) for p in q['identities']])
def packed_infer(backend,raw,out,frame_id,verify=True):
 out.mkdir();pre=(backend.preprocessor(out/'preprocessing') if isinstance(backend,CameraOwner) else PLPreprocessor(app/'wcis_face_pl_retained',out/'preprocessing',old.marker,memory_transport=True))
 try:
  padded,sx,sy=pre.prepare_packed(raw,960,540,1920,'RGB565LE',frame_id=frame_id)
  q=infer_prepared(padded,sx,sy,root=release,out=out,config=config,evidence=evidence,gallery=templates,preprocessor=pre,model_backend=backend,
                   identity=dict(boot_id=boot,source_rgb565_sha256=sha(raw)),save_aligned=False)
  if verify:q['source_verified']=pre.verify_retained_source()['full_source_equal']
  return q
 finally:pre.close()

try:
 run('systemctl','stop','wcis-face-photo.service');control,_=old.fresh_snapshot(boot)
 run('systemctl','stop','wcis-sdi-camera-live.service',timeout=25)
 assert json.loads((old.root/(control['session']+'-result.json')).read_text())['exit_code']==0
 old.guard();old.cleanup(control)
 print('Formal services drained; starting finite single-owner camera trial.',flush=True)
 # Verify both models with only one live session before enabling SDI.
 with tempfile.TemporaryDirectory(prefix='wcis-owner-',dir='/dev/shm') as workspace:
  owner=CameraOwner(release,T/'wcis_camera_owner',receipt['binary_sha256'],Path(workspace),seconds=120,camera_enabled=False)
  try:
   checked=[]
   for index,(name,count) in enumerate([('single.jpg',1),('multi.png',2)]):
    image=cv2.imread(str(T/'samples'/name));h,w=image.shape[:2];scale=min(960/w,540/h)
    resized=cv2.resize(image,(max(1,int(w*scale)),max(1,int(h*scale))));image=np.zeros((540,960,3),np.uint8);image[:resized.shape[0],:resized.shape[1]]=resized
    raw=Path(workspace)/(name+'.rgb565');cv2.cvtColor(image,cv2.COLOR_BGR2BGR565).tofile(raw)
    values=[]
    for repeat in range(2):
     q=packed_infer(owner,raw,Path(workspace)/('job-'+str(index)+'-'+str(repeat)),100+index*2+repeat)
     assert q['face_count']==count,(name,q['face_count']);values.append(signatures(q))
    assert values[0]==values[1];checked.append(name)
    print('Persistent-device model preflight passed: '+name,flush=True)
   save(T/'model-preflight.json',dict(passed=True,boot_id=boot,cases=checked))
  finally:owner.close()
  assert owner.process.returncode==0;owner=None
 with tempfile.TemporaryDirectory(prefix='wcis-owner-',dir='/dev/shm') as workspace:
  work=Path(workspace);owner=CameraOwner(release,T/'wcis_camera_owner',receipt['binary_sha256'],work,seconds=180)
  try:
   current=dict(source='camera',boot_id=boot,pid=owner.process.pid,session=work.name[len('wcis-owner-'):],directory=str(work))
   save(T/'current.json',current);frames=Frames(T/'current.json')
   server=ThreadingHTTPServer(('192.168.1.113',8094),handler(frames));threading.Thread(target=server.serve_forever,daemon=True).start()
   def monitor():
    last=None
    while not monitor_stop.is_set():
     state,jpeg=frames.read()
     if state['ready'] and state['frame_id']!=last:
      observed.append(dict(observed_at=time.monotonic(),frame_id=state['frame_id'],captured_at=state['captured_at'],encoded=state['encoded']))
      last=state['frame_id']
     monitor_stop.wait(.02)
   monitor_thread=threading.Thread(target=monitor);monitor_thread.start()
   deadline=time.monotonic()+8
   while not observed:
    if time.monotonic()>deadline:raise RuntimeError('Owner did not publish camera frames')
    time.sleep(.04)
   for i in range(8):
    with tempfile.TemporaryDirectory(prefix='request-',dir=work) as request:
     started=time.monotonic();q,jpeg=owner.infer_camera(Path(request)/'job',templates,verify=i in (0,7));finished=time.monotonic()
     image=cv2.imdecode(np.frombuffer(jpeg.read_bytes(),np.uint8),cv2.IMREAD_COLOR);assert image is not None and image.shape==(540,960,3)
     raw=jpeg.parent/'source.rgb565';reference=cv2.cvtColor(np.fromfile(raw,np.uint8).reshape(540,960,2),cv2.COLOR_BGR5652BGR)
     psnr=float(cv2.PSNR(reference,image));assert psnr>=20
     progressed=[r for r in observed if started<=r['observed_at']<=finished and r['frame_id']>q['camera_frame']['frame_id']]
     one=dict(index=i,frame_id=q['camera_frame']['frame_id'],face_count=q['face_count'],elapsed_ms=1000*(finished-started),preview_frames_during_request=len(progressed),jpeg_psnr=psnr)
     cases.append(one);print(json.dumps(one),flush=True)
     if i in (0,7):
      dest=T/('camera-source-'+str(i)+'.rgb565');shutil.copy2(raw,dest);selected.append((dest,signatures(q),'camera-'+str(i)))
      shutil.copy2(jpeg,T/('camera-preview-'+str(i)+'.jpg'));save(T/('camera-result-'+str(i)+'.json'),q)
   # Two repetitions exercise real detector/recognizer switching in one CPU owner.
   for name,count in [('single.jpg',1),('multi.png',2),('no-face.png',0)]:
    image=cv2.imread(str(T/'samples'/name));assert image is not None
    h,w=image.shape[:2];scale=min(960/w,540/h);resized=cv2.resize(image,(max(1,int(w*scale)),max(1,int(h*scale))))
    image=np.zeros((540,960,3),np.uint8);image[:resized.shape[0],:resized.shape[1]]=resized
    raw=T/(name+'.rgb565');cv2.cvtColor(image,cv2.COLOR_BGR2BGR565).tofile(raw)
    stable=[]
    for repeat in range(2):
     with tempfile.TemporaryDirectory(prefix='fixture-',dir=work) as tmp:
      owned=Path(tmp)/'source.rgb565';shutil.copy2(raw,owned)
      started=time.monotonic();q=packed_infer(owner,owned,Path(tmp)/'job',10000+len(comparisons)*2+repeat)
      assert q['face_count']==count,(name,q['face_count']);stable.append(signatures(q))
      print(json.dumps(dict(fixture=name,repeat=repeat,face_count=count,elapsed_ms=1000*(time.monotonic()-started))),flush=True)
    assert stable[0]==stable[1],(name,'Model outputs changed between repetitions')
    comparisons.append(dict(fixture=name,repeat_equal=True));selected.append((raw,stable[0],name))
   result['preview_url']='http://192.168.1.113:8094/'
   print('Camera/model checks passed; preview remains available for 15 seconds.',flush=True)
   time.sleep(15)
   monitor_stop.set();monitor_thread.join();owner.close();assert owner.process.returncode==0
   result.update(owner_pid=owner.process.pid,preview_frames=observed,camera_cases=cases,fixtures=comparisons)
   shutil.copy2(work/'native-stdout.log',T/'native-stdout.log');shutil.copy2(work/'native-stderr.log',T/'native-stderr.log')
   owner=None
  finally:
   if owner is not None:owner.close()
 # Compare identical raw inputs against the existing isolated PL/NPU backend.
 old.guard()
 with (release/'npu.lock').open('a') as lock:
  import fcntl
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);baseline=ModelBackend(release,app/'wcis_face_cached')
  try:
   for i,(raw,expected,name) in enumerate(selected):
    with tempfile.TemporaryDirectory(prefix='wcis-baseline-',dir='/dev/shm') as tmp:
     q=packed_infer(baseline,raw,Path(tmp)/'job',20000+i)
     assert signatures(q)==expected,(name,'Baseline model output mismatch')
     print('Baseline exact output parity: '+name,flush=True)
  finally:baseline.close()
 gaps=[observed[i+1]['observed_at']-observed[i]['observed_at'] for i in range(len(observed)-1)]
 assert observed and all(x['preview_frames_during_request']>0 for x in cases), 'Preview did not advance during recognition'
 result.update(passed=True,exact_baseline_cases=len(selected),preview_max_gap_s=max(gaps),preview_observed_fps=(len(observed)-1)/(observed[-1]['observed_at']-observed[0]['observed_at']))
finally:
 monitor_stop.set()
 if monitor_thread is not None:monitor_thread.join(timeout=2)
 if owner is not None:
  try:owner.close()
  except BaseException as e:result['owner_close_error']=str(e)
 if server is not None:server.shutdown();server.server_close()
 # A hardware fault never triggers an automatic SDK restart.
 safe=not old.marker.exists() or json.loads(old.marker.read_text()).get('boot_id')!=boot
 if safe and 'owner_close_error' not in result:
  run('systemctl','start','wcis-sdi-camera-live.service',timeout=20);old.fresh_snapshot(boot)
  run('systemctl','start','wcis-face-photo.service',timeout=20)
  result['formal_services_restored']=True
 else:result['formal_services_restored']=False
 result['gallery_unchanged']=gallery_hashes()==before['gallery']
 result['formal_app_unchanged']=all(sha(app/n)==value for n,value in before['files'].items())
 save(T/'verification.json',result)
assert result['passed'] and result['formal_services_restored'] and result['gallery_unchanged'] and result['formal_app_unchanged']
print(json.dumps({k:v for k,v in result.items() if k not in ('preview_frames','camera_cases','fixtures')}),flush=True)
