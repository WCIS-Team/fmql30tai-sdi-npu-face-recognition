"""Bounded client for a single capture/FAC1/NPU owner; no SDK in Python.

One device/allocator and VPU stay resident. SDK commands never overlap;
camera DMA can fill its other PS buffer while a command is running.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

import numpy as np
from model_backend_runtime import BackendRequest, file_version
from pl_preprocess import PLPreprocessor
from recognize_frame import infer_prepared
from run_photos import sha,save
from native_forward import NativeForward


class FrameWorker:
    def __init__(self, owner):
        self.owner=owner;self.frame=None;self.native_inputs=owner.native_inputs;self.verify_native_inputs=owner.verify_native_inputs

    def native_forward(self,role,token,reply,directory,image):
        return NativeForward(self.owner,role,token,reply,directory,image)

    def command(self,q):
        reply=self.owner.command(q)
        if (reply.get('frame_id')!=q['frame_id'] or reply.get('frame_token')!=q['frame_token']
                or reply.get('single_owner') is not True or (q['op']!='release' and reply.get('device_closed') is not False)):
            raise RuntimeError('Owner frame completion identity mismatch')
        if q['op']=='begin':self.frame=reply['frame_lease']
        if q['op']=='release':self.frame=None
        return reply

    def release(self):
        if self.frame is not None:
            self.command(dict(op='release',frame_id=self.frame['frame_id'],frame_token=self.frame['frame_token']))

    def close(self):
        if not self.owner.broken:self.release()


class CameraOwner:
    def __init__(self, root, executable, digest, work, *, seconds=180, camera_enabled=True, fps=30,native_inputs=False,verify_native_inputs=False,profile=False,preview_mode='vpu',pad_bundle=None):
        if preview_mode not in ('vpu','pl'):raise ValueError('Unknown camera preview mode')
        if preview_mode=='pl' and not camera_enabled:raise ValueError('PL preview mode requires camera input')
        self.preview_mode=preview_mode
        self.root=Path(root);self.work=Path(work);self.executable=Path(executable)
        self.native_inputs=bool(native_inputs);self.verify_native_inputs=bool(verify_native_inputs)
        self.profile=bool(profile)
        if self.verify_native_inputs and not self.native_inputs:raise ValueError('Input parity requires native input mode')
        self.broken=False;self.closed=False;self.process=None;self.buffer=b'';self.busy=threading.Lock();self.last_frame=0;self.photo_serial=0
        self.responses=queue.Queue(maxsize=2);self.reader_error=None;self.reader=None;self.stopping=False
        self.stop_receipt=None
        self.marker=self.root.parents[1]/'hardware-review-required.json'
        self.boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        from camera_interlock import CameraInterlock
        self.admission=CameraInterlock('/root/wcis-face/candidates/face-camera-ready-20261020/camera-control.json',self.root)
        if self.admission.guard()!=self.boot:raise RuntimeError('Owner boot has no verified deployment proof')
        active=json.loads(Path('/root/wcis-face/video-stream-current.json').read_text())
        if active['verified_boot_id']!=self.boot or Path(active['release'])!=self.root:raise RuntimeError('Owner release not admitted for this boot')
        self.config=json.loads((self.root/'models.json').read_text());self.evidence=json.loads((self.root/'run-01/verification.json').read_text())
        pipeline='yunet-mf-'+self.config['precision']+'-npu:'+sha(self.root/'models.json')
        if not self.evidence['all_passed'] or self.evidence['pipeline_id']!=pipeline:raise RuntimeError('Owner release is not validated')
        if self.work.parent!=Path('/dev/shm') or not self.work.name.startswith('wcis-owner-'):
            raise ValueError('Owner requires an isolated tmpfs workspace')
        self.versions={}
        for path in [self.root/'models.json']+[self.root/item[k] for item in self.config['models'].values() for k in ('json','raw')]:
            self.versions[path]=file_version(path)
        for record in self.config['models'].values():
            for key in ('json','raw'):
                if sha(self.root/record[key])!=record[key+'_sha256']:raise RuntimeError('Owner model checksum mismatch')
        self.pad_manifest=None
        if pad_bundle is not None:
            from owner_pad import checked_bundle
            self.pad_manifest,pad_config,pad_files=checked_bundle(pad_bundle)
            if any(pad_config.get(k)!=self.config[k] for k in ('rows','cols')):
                raise RuntimeError('PAD and identity model MPE geometries differ')
            self.versions.update({path:file_version(path) for path in pad_files})
        if sha(self.executable)!=digest:raise RuntimeError('Owner executable checksum mismatch')
        self.guard()
        self.lock=(self.root/'npu.lock').open('a');self.camera=Path('/root/wcis-camera-preview/camera.lock').open('a')
        self.log=(self.work/'native-stdout.log').open('wb');self.errors=(self.work/'native-stderr.log').open('wb');self.logged=0
        try:
            fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(self.camera,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if not isinstance(fps,int) or not 1<=fps<=30:raise ValueError('Camera FPS outside 1..30')
            env=os.environ.copy();env.update(WCIS_NPU_LOCK_FD=str(self.lock.fileno()),WCIS_CAMERA_LOCK_FD=str(self.camera.fileno()),WCIS_CAMERA_FPS=str(fps))
            env.pop('WCIS_OWNER_PAD_MANIFEST',None)
            if self.pad_manifest is not None:env['WCIS_OWNER_PAD_MANIFEST']=str(self.pad_manifest)
            command=[str(self.executable),str(self.root/'models.json'),self.boot,str(self.work),str(seconds)]
            if not camera_enabled:command.append('no-camera')
            elif preview_mode=='pl':command.append('pl-preview')
            self.process=subprocess.Popen(command,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,pass_fds=(self.lock.fileno(),self.camera.fileno()))
            self.reader=threading.Thread(target=self._pump,daemon=True);self.reader.start()
            self.ready=self._read()
            if self.ready.get('protocol')!=2 or self.ready.get('single_sdk_owner') is not True or self.ready.get('device_opened') is not False or self.ready.get('boot_id')!=self.boot:
                raise RuntimeError('Owner startup did not confirm the required contract')
            if self.native_inputs and self.ready.get('fused_prepared_inputs') is not True:raise RuntimeError('Owner does not support fused prepared inputs')
            if preview_mode=='pl' and self.ready.get('external_pl_preview') is not True:raise RuntimeError('Owner does not support external PL preview')
            if self.pad_manifest is not None and self.ready.get('pad_models_loaded') is not True:raise RuntimeError('Owner does not support the PAD bundle')
            self.validate_release()
            self.exclusive_owner=True
            if camera_enabled and preview_mode=='vpu':
                deadline=time.monotonic()+8
                while not (self.work/'latest.frame').is_file():
                    self.guard()
                    if self.process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Owner camera did not publish its first frame')
                    time.sleep(.02)
        except BaseException:
            self.close();raise

    def guard(self):
        if self.admission.guard()!=self.boot:raise RuntimeError('Owner boot proof changed')
        if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=self.boot:raise RuntimeError('Owner boot identity changed')
        if self.marker.exists() and json.loads(self.marker.read_text()).get('boot_id')==self.boot:raise RuntimeError('Hardware review required; no automatic owner retry')
        if self.process is not None and self.process.poll() is not None and not self.stopping:raise RuntimeError('Camera owner exited')

    def validate_release(self):
        self.guard()
        if any(file_version(p)!=v for p,v in self.versions.items()):raise RuntimeError('Owner model release changed')

    def _read(self):
        try:value=self.responses.get(timeout=30)
        except queue.Empty:raise TimeoutError('Owner command deadline; review hardware before reuse')
        if isinstance(value,BaseException):raise value
        if value.get('status')=='error':raise RuntimeError(value.get('message','Owner failed'))
        return value

    def _pump(self):
        try:
            while True:
                data=os.read(self.process.stdout.fileno(),65536)
                if not data:break
                if self.logged<4*1024*1024:
                    part=data[:4*1024*1024-self.logged];self.log.write(part);self.log.flush();self.logged+=len(part)
                self.buffer+=data
                if len(self.buffer)>1024*1024:raise RuntimeError('Owner log line exceeded the bounded transport buffer')
                while b'\n' in self.buffer:
                    line,self.buffer=self.buffer.split(b'\n',1);where=line.find(b'WCIS_OWNER_RESULT ')
                    if where>=0:
                        reply=json.loads(line[where+len(b'WCIS_OWNER_RESULT '):])
                        if reply.get('status')=='stopped':self.stop_receipt=reply
                        self.responses.put_nowait(reply)
            if not self.stopping:
                self.reader_error=RuntimeError('Owner exited without an active request completion')
                if self.responses.empty():self.responses.put_nowait(self.reader_error)
        except BaseException as error:
            self.reader_error=error;self.broken=True
            if self.responses.empty():self.responses.put_nowait(error)

    def command(self,q):
        if not self.busy.acquire(blocking=False):raise RuntimeError('Owner request already in flight; do not queue')
        try:
            self.validate_release()
            if self.broken or self.process.poll() is not None:raise RuntimeError('Owner unavailable')
            q=dict(q,profile=self.profile)
            self.process.stdin.write((json.dumps(q)+'\n').encode());self.process.stdin.flush()
            return self._read()
        except BaseException:
            self.broken=True;raise
        finally:self.busy.release()

    def preprocessor(self, work, *, photo=False):
        pre=PLPreprocessor(self.executable,work,self.marker,memory_transport=True,worker_factory=lambda _:FrameWorker(self))
        if photo:
            self.photo_serial+=1
            if self.photo_serial>=0x80000000:raise RuntimeError('Photo frame sequence exhausted; restart the owner')
            pre.frame=0x80000000+self.photo_serial-1
        return pre

    def request(self,out,retained_frame=None):
        if retained_frame is None:raise ValueError('Owner inference requires a retained frame')
        return BackendRequest(self,Path(out),retained_frame)

    def forward(self,role,data,out,stem,retained_frame=None):
        pad_roles=('MiniFASNetV2','MiniFASNetV1SE') if self.pad_manifest is not None else ()
        if role not in ('yunet','mobilefacenet')+pad_roles:raise ValueError('Unknown owner model')
        if isinstance(data,NativeForward):
            self.validate_release();start=time.monotonic();q=data.claim(self,role,retained_frame);output=Path(data.directory)
            if (q.get('status')!='forwarded' or q.get('role')!=role or q.get('device_closed') is not False
                    or q.get('single_owner') is not True or q.get('npu_bound_ops',0)<1 or q.get('frame_preserved') is not True
                    or q.get('worker_pid')!=self.process.pid or q.get('input_transport')!='native_host_memory'):
                raise RuntimeError('Fused NPU completion identity/transport mismatch')
            values=[]
            for record in q['outputs']:
                path=output/(str(record['index'])+'.f32')
                if str(path)!=record['file']:raise RuntimeError('Fused output path mismatch')
                a=np.fromfile(path,np.float32)
                if len(a)!=record['elements'] or not np.all(np.isfinite(a)):raise RuntimeError('Fused output tensor invalid')
                record['sha256']=sha(path);record.pop('file');values.append(a);path.unlink()
            output.rmdir()
            if not any(output.parent.iterdir()):output.parent.rmdir()
            q['output_validation_ms']=(time.monotonic()-start)*1000
            q['host_call_ms']=q['prepared_forward_ms']+q['output_validation_ms']
            q['fused_in_preprocessing_rpc']=True
            save(Path(out)/'timing'/(stem+'-'+role+'.json'),q);return values,q
        size=640 if role=='yunet' else 112 if role=='mobilefacenet' else 80;array=np.asarray(data,dtype=np.float32)
        if array.shape not in ((size,size,3),(1,size,size,3)):raise ValueError('Owner tensor geometry mismatch')
        directory=Path(out)/('exchange-'+uuid.uuid4().hex);directory.mkdir()
        try:
            source=directory/'input.f32';array.tofile(source);output=directory/'output'
            start=time.monotonic();lease=retained_frame
            q=self.command(dict(op='forward',role=role,input_f32=str(source),output_directory=str(output),frame_id=lease['frame_id'],frame_token=lease['frame_token']))
            if (q.get('status')!='forwarded' or q.get('role')!=role or q.get('device_closed') is not False or q.get('single_owner') is not True or q.get('npu_bound_ops',0)<1
                    or q.get('frame_preserved') is not True or q.get('frame_id')!=lease['frame_id']
                    or q.get('frame_token')!=lease['frame_token'] or q.get('worker_pid')!=self.process.pid):
                raise RuntimeError('Owner NPU completion identity mismatch')
            values=[]
            for record in q['outputs']:
                path=output/(str(record['index'])+'.f32')
                if str(path)!=record['file']:raise RuntimeError('Owner output path mismatch')
                a=np.fromfile(path,np.float32)
                if len(a)!=record['elements'] or not np.all(np.isfinite(a)):raise RuntimeError('Owner output tensor invalid')
                record['sha256']=sha(path);record.pop('file');values.append(a);path.unlink()
            output.rmdir();q['host_call_ms']=(time.monotonic()-start)*1000
            save(Path(out)/'timing'/(stem+'-'+role+'.json'),q);return values,q
        finally:
            if (directory/'input.f32').exists():(directory/'input.f32').unlink()
            if directory.exists() and not any(directory.iterdir()):directory.rmdir()

    def snapshot(self,out):
        q=self.command(dict(op='latest',output_directory=str(out)))
        if q.get('status')!='snapshot':raise RuntimeError('Owner did not return a fresh frame')
        raw=Path(q['raw_file']);jpeg=Path(q['jpeg_file']);frame=q['frame']
        if raw!=Path(out)/'source.rgb565' or jpeg!=Path(out)/'preview.jpg':raise RuntimeError('Owner snapshot path mismatch')
        if (frame.get('boot_id')!=self.boot or frame.get('pid')!=self.process.pid or frame.get('source')!='camera'
                or frame['frame_id']<=self.last_frame or raw.stat().st_size!=960*540*2
                or (frame['width'],frame['height'])!=(960,540) or not 0<=time.monotonic()-frame['captured_at']<=1.5):
            raise RuntimeError('Owner snapshot metadata mismatch')
        frame.update(session=self.work.name[len('wcis-owner-'):],source_rgb565_sha256=sha(raw),jpeg_sha256=sha(jpeg),input_pixel_format='RGB565LE')
        self.last_frame=frame['frame_id'];return raw,jpeg,frame

    def infer_camera(self,out,gallery,verify=False):
        started=time.monotonic();out=Path(out);out.mkdir()
        raw,jpeg,frame=self.snapshot(out/'snapshot');preprocessor=self.preprocessor(out/'preprocessing')
        try:
            padded,sx,sy=preprocessor.prepare_packed(raw,960,540,1920,'RGB565LE',frame_id=frame['frame_id'])
            result=infer_prepared(padded,sx,sy,root=self.root,out=out,config=self.config,evidence=self.evidence,gallery=gallery,
                preprocessor=preprocessor,model_backend=self,identity=dict(boot_id=self.boot,camera_frame=frame,photo_sha256=sha(jpeg),source_rgb565_sha256=sha(raw)),
                start=started,request_started=started,save_aligned=False)
            if verify:result['full_source_verification']=preprocessor.verify_retained_source()
            result.update(input_source='camera_raw_rgb565',presentation_attack_detection=dict(status='not_evaluated',security_calibrated=False))
            if self.pad_manifest is not None:
                from owner_pad import evaluate
                identity_finished=time.monotonic()
                result['presentation_attack_detection']=evaluate(self,preprocessor,result,raw,frame,out)
                result['request_elapsed_ms']=(time.monotonic()-started)*1000
                result['elapsed_ms']=result['request_elapsed_ms']
                result['pipeline_timing_ms']=dict(identity=(identity_finished-started)*1000,
                    pad=result['request_elapsed_ms']-(identity_finished-started)*1000)
            result['model_lifecycle']=('single_owner_cached_sessions' if self.ready.get('session_cache_enabled')
                                       else 'single_owner_cpu_models');save(out/'result.json',result)
            return result,jpeg
        finally:preprocessor.close()

    def close(self):
        if self.closed:return
        self.stopping=True
        if self.process is not None:
            if self.process.stdin and not self.process.stdin.closed:self.process.stdin.close()
            # EOF drains VPU and in-flight hardware; never SIGKILL this owner.
            self.process.wait(timeout=35)
            if self.reader is not None:self.reader.join(timeout=2)
            if self.stop_receipt is not None:
                save(self.executable.parent/(str(self.process.pid)+'-owner-stop.json'),dict(self.stop_receipt,boot_id=self.boot,worker_pid=self.process.pid,exit_code=self.process.returncode))
            self.process.stdout.close()
        self.log.close();self.errors.close()
        if self.process is not None:
            for name in ('fault.json','native-stdout.log','native-stderr.log'):
                path=self.work/name
                if path.exists():shutil.copy2(path,self.executable.parent/(str(self.process.pid)+'-'+name))
        self.camera.close();self.lock.close();self.closed=True
