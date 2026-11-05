"""Packed-frame ModelBackend adapter for FAC1. No camera, gallery or scheduling.

Caller owns the existing project hardware lock across preprocessing and NPU
requests. Run before opening an NPU Runner, or after its worker has exited.
"""
import json
import hashlib
from pathlib import Path
import subprocess
import time
import tempfile
import os
import select
import uuid
import numpy as np
import cv2


class _FrameProcess:
    """One CPU lease owner. SDK devices close before each synchronous reply."""
    def __init__(self,executable,work):
        self.buffer=b'';self.frame=None;self.broken=False
        self.stdout=(work/'frame-worker.stdout.log').open('wb')
        self.stderr=(work/'frame-worker.stderr.log').open('wb')
        self.process=subprocess.Popen([str(executable),'--serve'],stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE,stderr=self.stderr)
        try:
            ready=self._read()
            if ready.get('status')!='ready' or ready.get('frame_leases') is not True or ready.get('device_opened') is not False:
                raise RuntimeError('PL executable lacks the CPU-only frame lease protocol')
        except BaseException:
            self.broken=True;self.close();raise

    def _read(self):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if b'\n' in self.buffer:
                line,self.buffer=self.buffer.split(b'\n',1);marker=line.find(b'WCIS_PL_RESULT ')
                if marker>=0:
                    response=json.loads(line[marker+len(b'WCIS_PL_RESULT '):])
                    if response.get('status')=='error':raise RuntimeError(response.get('message','PL lease command failed'))
                    return response
                continue
            if select.select([self.process.stdout],[],[],max(0,deadline-time.monotonic()))[0]:
                data=os.read(self.process.stdout.fileno(),65536)
                if not data:raise RuntimeError('PL frame process exited; no automatic retry')
                self.stdout.write(data);self.stdout.flush();self.buffer+=data
        raise TimeoutError('PL frame process deadline; review hardware before retry')

    def command(self,value):
        if self.broken or self.process.poll() is not None:raise RuntimeError('PL frame lease process unavailable')
        try:
            self.process.stdin.write((json.dumps(value)+'\n').encode());self.process.stdin.flush()
            response=self._read()
            if (response.get('frame_id')!=value['frame_id'] or response.get('frame_token')!=value['frame_token']
                    or (value['op']!='release' and response.get('device_closed') is not True)):
                raise RuntimeError('PL lease response belongs to another frame or live device')
            if value['op']=='begin':self.frame=response['frame_lease']
            if value['op']=='release':self.frame=None
            return response
        except BaseException:
            self.broken=True;raise

    def release(self):
        if self.frame is not None and not self.broken:
            self.command(dict(op='release',frame_id=self.frame['frame_id'],frame_token=self.frame['frame_token']))

    def close(self):
        try:
            self.release()
        finally:
            if self.process.stdin and not self.process.stdin.closed:self.process.stdin.close()
            # EOF drains commands. Never kill an active SDK/DMA owner.
            self.process.wait(timeout=35);self.process.stdout.close()
            self.stdout.close();self.stderr.close()


class PLPreprocessor:
    def __init__(self, executable, work, fault_marker, memory_transport=False, worker_factory=None):
        self.executable=Path(executable)
        self.work=Path(work)
        self.work.mkdir(parents=True,exist_ok=True)
        self.fault_marker=Path(fault_marker)
        self.frame=0
        self.serial=0
        self.original_image_hash=None
        self.timings=[]
        self.buffers=tempfile.TemporaryDirectory(prefix='wcis-face-pl-',dir=self.work if worker_factory else '/dev/shm') if memory_transport else None
        self.source=None
        self.source_builds=0
        self.retained_frame=None
        self.worker=None
        if memory_transport:
            try:self.worker=worker_factory(self.work) if worker_factory else _FrameProcess(self.executable,self.work)
            except BaseException:
                self.buffers.cleanup();raise

    def close(self):
        try:
            if self.worker is not None:self.worker.close()
        finally:
            if self.buffers is not None:self.buffers.cleanup()

    def _retain_source(self,image):
        started=time.monotonic()
        if image.dtype!=np.uint8 or image.ndim!=3 or image.shape[2]!=3:
            raise ValueError('Expected original-frame uint8 BGR image')
        h,w=image.shape[:2];pitch=((w*4+7)//8)*8
        if not (1<=w<=8192 and 1<=h<=8192):raise ValueError('Image outside PL geometry contract')
        if ((pitch*h+63)//64)*64+640*640*4+(128 if self.worker else 0)>64*1024*1024:
            raise ValueError('Frame exceeds the bounded PL allocation')
        if self.source is not None and self.buffers is not None:
            if self.worker:self.worker.release();self.retained_frame=None
            if self.source.get('owned',True):self.source['path'].unlink()
        self.frame+=1
        self.original_image_hash=hashlib.sha256(np.ascontiguousarray(image)).hexdigest()
        directory=Path(self.buffers.name) if self.buffers else self.work
        source=directory/('frame-'+str(self.frame)+'.rgbx')
        storage=np.zeros((h,pitch//4,4),dtype=np.uint8)
        storage[:,:w,:3]=image;storage.tofile(source);del storage
        source.chmod(0o444)
        # This owned snapshot survives both synchronous PL commands. Later
        # caller changes to the decoded image cannot change alignment pixels.
        self.source=dict(path=source,w=w,h=h,pitch=pitch,frame_id=self.frame,
                         prepare_ms=(time.monotonic()-started)*1000,uses=0,token=uuid.uuid4().hex)
        self.source_builds+=1

    def _run(self,matrix,content,canvas,replicate,role=None):
        started=time.monotonic()
        if self.source is None:raise ValueError('No retained source frame')
        source_record=self.source
        h,w,pitch=source_record['h'],source_record['w'],source_record['pitch']
        cw,ch=content;dw,dh=canvas
        q=np.rint(np.asarray(matrix,dtype=np.float64)*65536)
        if q.shape!=(2,3) or not np.all(np.isfinite(q)) or np.any(q<-(2**31)) or np.any(q>=2**31):
            raise ValueError('Invalid inverse Q16.16 matrix')
        self.serial+=1;directory=self.work/('job-'+str(self.serial));directory.mkdir()
        buffers=directory if self.buffers is None else Path(self.buffers.name)/directory.name
        buffers.mkdir(exist_ok=True)
        source=source_record['path'];output=buffers/'output.rgbx'
        descriptor=dict(frame_id=self.frame,src_w=w,src_h=h,pitch_bytes=pitch,
            content_w=cw,content_h=ch,canvas_w=dw,canvas_h=dh,inverse_q16=q.astype(np.int64).reshape(-1).tolist(),
            rgb565=source_record.get('rgb565',False),replicate=bool(replicate),border=0,input_rgbx=str(source),output_rgbx=str(output),fault_marker=str(self.fault_marker))
        job=directory/'job.json';job.write_text(json.dumps(descriptor,indent=2))
        packed=time.monotonic()
        # The executable owns its 10-second hardware deadline. Do not SIGKILL
        # it and recycle DMA storage while the accelerator may still be active.
        if self.worker:
            command=dict(descriptor,op='begin' if source_record['uses']==0 else 'transform',frame_token=source_record['token'])
            native=bool(role and getattr(self.worker,'native_inputs',False))
            parity=native and self.worker.verify_native_inputs
            if native:
                command.update(forward_role=role,forward_token=uuid.uuid4().hex,
                               forward_output_directory=str(buffers/'npu'),write_output=role=='mobilefacenet' or parity)
                if parity:command['verify_input_f32']=str(buffers/'verify-input.f32')
            response=self.worker.command(command)
            if response.get('status')!='preprocessed':raise RuntimeError('PL did not complete the retained frame transform')
            if self.retained_frame is None:self.retained_frame=dict(response['frame_lease'])
            elif response.get('frame_lease')!=self.retained_frame:raise RuntimeError('PL changed the active frame lease')
            process_stdout=json.dumps(response);process_stderr=''
        else:
            native=parity=False
            result=subprocess.run([str(self.executable),'--run',str(job)],capture_output=True,text=True)
            process_stdout,process_stderr=result.stdout,result.stderr
            if result.returncode:raise RuntimeError('PL preprocessing failed; review per-frame logs and hardware quarantine')
            marker='WCIS_PL_RESULT '
            lines=[line[line.index(marker)+len(marker):] for line in result.stdout.splitlines() if marker in line]
            if not lines:raise RuntimeError('PL runner returned no completion record')
            response=json.loads(lines[-1])
        process_returned=time.monotonic()
        (directory/'stdout.log').write_text(process_stdout)
        (directory/'stderr.log').write_text(process_stderr)
        if response.get('status')!='preprocessed' or response.get('frame_id')!=self.frame:
            raise RuntimeError('Invalid PL completion record')
        image_result=None
        if not native or command['write_output']:
            values=np.fromfile(output,np.uint8)
            if values.size!=dw*dh*4:raise RuntimeError('Incomplete PL output frame')
            response['output_sha256']=hashlib.sha256(values.tobytes()).hexdigest()
            image_result=values.reshape(dh,dw,4)[:,:,:3].copy()
        else:response['output_sha256']=None
        if native:
            reply=response.pop('forward_result')
            if parity:
                actual=np.fromfile(buffers/'verify-input.f32',np.float32)
                expected=image_result.astype(np.float32) if role=='yunet' else (image_result[:,:,::-1].astype(np.float32)-np.float32(127.5))/np.float32(127.5)
                if actual.tobytes()!=expected.tobytes():raise RuntimeError('Native input differs from NumPy contract')
                (buffers/'verify-input.f32').unlink()
            response['native_input_parity_checked']=parity;response['fused_forward_in_prepare']=True
            image_result=self.worker.native_forward(role,command['forward_token'],reply,buffers/'npu',image_result)
        retained_ms=source_record['prepare_ms'] if source_record['uses']==0 else 0
        response['host_phases_ms']=dict(source_pack_and_write=retained_ms+(packed-started)*1000,
            process_wall=(process_returned-packed)*1000,
            output_read_and_validate=(time.monotonic()-process_returned)*1000,
            total=retained_ms+(time.monotonic()-started)*1000)
        response['pixel_transport']='bounded_tmpfs' if self.buffers else 'debug_files'
        response['source_reused']=source_record['uses']>0
        response['source_image_sha256']=self.original_image_hash
        response['source_builds']=self.source_builds
        source_record['uses']+=1
        if self.buffers is not None:
            if output.exists():output.unlink()
            if not native:buffers.rmdir()
        self.timings.append(response)
        return image_result

    def verify_retained_source(self):
        """Explicit validation path only: full DDR source readback, no upload."""
        if not self.worker or not self.retained_frame:raise RuntimeError('No DDR frame lease to verify')
        result=self.worker.command(dict(op='verify',frame_id=self.frame,frame_token=self.source['token']))
        if result.get('status')!='verified' or result.get('full_source_equal') is not True:
            raise RuntimeError('Retained DDR frame failed full verification')
        return result

    def prepare(self,image):
        self._retain_source(image)
        return self.resize_retained()

    def prepare_packed(self,path,width,height,pitch,pixel_format,frame_id=None):
        """One-time replay seed load, already packed off the board.

        Input file stays caller-owned. This does not adopt arbitrary physical
        memory or claim a capture producer; the SDK still allocates the frame.
        """
        if self.worker is None:raise ValueError('Packed input requires the retained-frame executable')
        if pixel_format not in ('BGRX8','RGB565LE'):raise ValueError('Unsupported packed pixel format')
        if any(type(v) is not int for v in (width,height,pitch)):
            raise ValueError('Packed geometry must use integers')
        bpp=2 if pixel_format=='RGB565LE' else 4
        if not (1<=width<=8192 and 1<=height<=8192) or pitch%8 or pitch<width*bpp or pitch>65536:
            raise ValueError('Packed frame outside PL geometry contract')
        if 128+((pitch*height+63)//64)*64+640*640*4>64*1024*1024:
            raise ValueError('Packed frame exceeds bounded PL allocation')
        path=Path(path).resolve(strict=True)
        if not path.is_file() or path.stat().st_size!=pitch*height:
            raise ValueError('Packed frame file length mismatch')
        next_frame=self.frame+1 if frame_id is None else frame_id
        if type(next_frame) is not int or not self.frame<next_frame<=0xffffffff:
            raise ValueError('Packed frame ID must increase within uint32')
        if self.source is not None:
            self.worker.release();self.retained_frame=None
            if self.source.get('owned',True):self.source['path'].unlink()
        self.frame=next_frame
        self.original_image_hash=hashlib.sha256(path.read_bytes()).hexdigest()
        self.source=dict(path=path,w=width,h=height,pitch=pitch,frame_id=self.frame,
                         prepare_ms=0,uses=0,token=uuid.uuid4().hex,
                         rgb565=pixel_format=='RGB565LE',owned=False)
        return self.resize_retained()

    def resize_retained(self):
        if self.source is None:raise ValueError('No retained source frame')
        h,w=self.source['h'],self.source['w'];ratio=min(640/w,640/h)
        cw,ch=max(1,int(w*ratio)),max(1,int(h*ratio))
        ax,ay=w/cw,h/ch
        inverse=[[ax,0,(ax-1)/2],[0,ay,(ay-1)/2]]
        return self._run(inverse,(cw,ch),(640,640),True,'yunet'),cw/w,ch/h

    def align(self,image,face):
        if self.frame==0 or hashlib.sha256(np.ascontiguousarray(image)).hexdigest()!=self.original_image_hash:
            raise ValueError('Alignment source does not match the retained detection frame')
        return self.align_retained(face)

    def align_retained(self,face):
        if self.source is None:raise ValueError('No retained detection frame')
        from run_photos import alignment_matrix
        inverse=cv2.invertAffineTransform(alignment_matrix(face))
        return self._run(inverse,(112,112),(112,112),False,'mobilefacenet')
