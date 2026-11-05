"""Install a separate reference application; preserve startup firmware and reference files."""
from ssh_transport import board_connection, ROOT
import hashlib,json,shlex,time,posixpath
BINARY=ROOT/'outputs/ps_app/wcis_sdi_reference'
SHA=hashlib.sha256(BINARY.read_bytes()).hexdigest()
DEST='/root/wcis-vision/20261013-'+SHA[:12]
REF='/root/plin_demo/PLin+SingleNet+HDMI'
REPORT=ROOT/'outputs/ps_app/board_deployment.json'
result={'board':'192.168.1.113','directory':DEST,'binary_sha256':SHA,'firmware_replaced':False,'new_face_models_integrated':False,'test_input':'on-board VTC, not SDI camera'}
def run(c,cmd):
 _,o,e=c.exec_command(cmd,timeout=30)
 text=o.read().decode(errors='replace')+e.read().decode(errors='replace')
 code=o.channel.recv_exit_status()
 if code: raise RuntimeError(str(code)+': '+text[:1800])
 return text
# Read/write the one documented camera-source selector only, preserving its original value.
def selector(c,value=None):
 code="import mmap,os,struct; f=os.open('/dev/mem',os.O_RDWR|os.O_SYNC); m=mmap.mmap(f,4096,offset=0x40080000); "
 if value is None: code+="print(struct.unpack_from('<I',m,0xb4)[0]); "
 else: code+="struct.pack_into('<I',m,0xb4,"+str(int(value))+"); print(struct.unpack_from('<I',m,0xb4)[0]); "
 code+="m.close();os.close(f)"
 return int(run(c,'python3 -c '+shlex.quote(code)).strip())
raise SystemExit('Deployment execution disabled after board hang on 2026-10-13. Recover board and review hardware/runtime compatibility before retrying. No SSH connection was opened.')

with board_connection() as c:
 s=c.open_sftp()
 run(c,'mkdir -p '+shlex.quote(DEST+'/configs')+' '+shlex.quote(DEST+'/imodel/ZG')+' '+shlex.quote(DEST+'/names')+' '+shlex.quote(DEST+'/logs'))
 target=DEST+'/wcis_sdi_reference'
 try:
  existing=run(c,'sha256sum '+shlex.quote(target)).split()[0]
  if existing!=SHA: raise RuntimeError('Existing deployment binary differs; refusing overwrite')
 except IOError: raise
 except RuntimeError as e:
  if 'No such file' not in str(e): raise
  s.put(str(BINARY),target);s.chmod(target,0o700)
 assert run(c,'sha256sum '+shlex.quote(target)).split()[0]==SHA
 result['files']={}
 assets=['imodel/ZG/yolov5s_plin_352x640_ZG.json','imodel/ZG/yolov5s_plin_352x640_ZG.raw','names/coco.names']
 for rel in assets:
  old=REF+'/'+rel; new=DEST+'/'+rel
  run(c,'cp -n -- '+shlex.quote(old)+' '+shlex.quote(new))
  oldhash=run(c,'sha256sum '+shlex.quote(old)).split()[0]
  assert run(c,'sha256sum '+shlex.quote(new)).split()[0]==oldhash
  result['files'][rel]={'sha256':oldhash,'source':old}
 with s.open(REF+'/configs/ZG/vtc-test.yaml') as f:
  cfg=f.read().decode('utf-8-sig').replace('\r','')
 assert 'vision_mode' not in cfg and 'vtc: true' in cfg
 cfg=cfg.replace('log_path: ../io/output/ftmp','log_path: ./logs/ftmp')
 with s.open(DEST+'/configs/vtc.yaml','w') as f:f.write(cfg)
 with s.open(DEST+'/configs/sdi.yaml','w') as f:f.write(cfg.replace('vtc: true','vtc: false'))
 launcher='#!/bin/sh\nset -eu\ncd '+shlex.quote(DEST)+'\nexec ./wcis_sdi_reference "${1:-configs/sdi.yaml}"\n'
 with s.open(DEST+'/run.sh','w') as f:f.write(launcher)
 s.chmod(DEST+'/run.sh',0o700)
 result['dependencies']=run(c,'ldd '+shlex.quote(target))
 assert 'not found' not in result['dependencies']
 result['installed']=True
 REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 with s.open(DEST+'/deployment.json','w') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2))
 print('Installed:',DEST,flush=True)
 original=selector(c)
 result['source_selector_before']=original
 print('Original source selector:',original,flush=True)
 channel=c.get_transport().open_session()
 channel.exec_command('cd '+shlex.quote(DEST)+' && echo WCIS_TEST_PID=$$ && timeout --signal=TERM --kill-after=5s 75s ./wcis_sdi_reference configs/vtc.yaml 2>&1 | tee logs/vtc-test.log')
 chunks=[];start=time.monotonic();stop_at=None;sent=False
 try:
  while not channel.exit_status_ready():
   while channel.recv_ready():chunks.append(channel.recv(65536))
   while channel.recv_stderr_ready():chunks.append(channel.recv_stderr(65536))
   output=b''.join(chunks).decode(errors='replace')
   (ROOT/'outputs/ps_app/board_vtc_test.log').write_text(output,encoding='utf-8')
   if time.monotonic()-start > 90:
    result['test_local_deadline_exceeded']=True
    break
   if stop_at is None and 'All actors started' in output:
    stop_at=time.monotonic()+10
    print('Actors started; collecting 10 seconds of pipeline evidence.',flush=True)
   if not sent and ((stop_at is not None and time.monotonic()>=stop_at) or time.monotonic()-start>55):
    channel.send(b'\n');sent=True;print('Requested normal shutdown.',flush=True)
   time.sleep(.1)
  while channel.recv_ready():chunks.append(channel.recv(65536))
  while channel.recv_stderr_ready():chunks.append(channel.recv_stderr(65536))
  result['test_exit_code']=channel.recv_exit_status() if channel.exit_status_ready() else None
 finally:
  channel.close()
  try:
   result['source_selector_after_restore']=selector(c,original)
   result['source_selector_restored']=result['source_selector_after_restore']==original
  except Exception as e:
   result['source_selector_restored']=False
   result['restore_error']=type(e).__name__
  REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 log=b''.join(chunks).decode(errors='replace')
 (ROOT/'outputs/ps_app/board_vtc_test.log').write_text(log,encoding='utf-8')
 with s.open(DEST+'/logs/vtc-test.log','w') as f:f.write(log)
 result['elapsed_seconds']=round(time.monotonic()-start,2)
 result['normal_shutdown']='All actors stopped' in log
 result['test_log_local']=str(ROOT/'outputs/ps_app/board_vtc_test.log')
 with s.open(DEST+'/deployment.json','w') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2))
 REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 s.close()
 print('Exit:',result['test_exit_code'],'normal shutdown:',result['normal_shutdown'],'source selector restored:',original,flush=True)
 print(log[-10000:],flush=True)
