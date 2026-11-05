"""Warm one model per process; close SDK hardware before returning a result.

Workers start by exec, never by forking a multithreaded SDK/Python process.
The existing npu.lock still belongs to each complete face request.
"""
import json
import os
from pathlib import Path
import select
import subprocess
import threading
import time
import tempfile
import uuid
import copy

import numpy as np
from run_photos import save,sha


def file_version(path):
    stat=path.stat()
    return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)


class _ModelProcess:
    def __init__(self,root,executable,role):
        self.root=Path(root)
        self.executable=Path(executable)
        if not self.executable.is_file():raise RuntimeError('Cached NPU executable is missing')
        # At most one tensor exchange exists; it is removed before releasing
        # the request lock. Camera callers must not build an unbounded queue.
        if not Path('/dev/shm').is_dir():raise RuntimeError('Model backend requires tmpfs tensor transport')
        self.versions={}
        manifest=self.root/'models.json'
        self.versions[manifest]=file_version(manifest)
        config=json.loads((self.root/'models.json').read_text())
        for record in config['models'].values():
            for key in ('json','raw'):
                path=self.root/record[key];version=file_version(path)
                if sha(path)!=record[key+'_sha256'] or file_version(path)!=version:
                    raise RuntimeError('Model checksum mismatch before cache startup')
                self.versions[path]=version
        self.manifest_sha256=sha(self.root/'models.json')
        self.directory=self.root.parents[1]/'runtime'/('model-cache-'+uuid.uuid4().hex)
        self.directory.mkdir(parents=True)
        self.stderr=(self.directory/'stderr.log').open('wb')
        self.stdout=(self.directory/'stdout.log').open('wb')
        self.buffer=b''
        self.busy=threading.Lock()
        self.broken=False
        self.process=None
        try:
            started=time.monotonic()
            self.process=subprocess.Popen([str(self.executable),'--serve',str(self.root/'models.json'),role],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr)
            self.ready=self._read()
            if (self.ready.get('status')!='ready' or self.ready.get('device_opened') is not False
                or self.ready.get('role')!=role):
                raise RuntimeError('Model process did not confirm CPU-only startup')
            if self.ready.get('retained_frame_supported') is not True:
                raise RuntimeError('Model executable cannot protect a retained DDR frame')
            self.ready['host_startup_ms']=(time.monotonic()-started)*1000
            self.validate_files()
            save(self.directory/'ready.json',self.ready)
        except BaseException:
            self.close()
            raise

    def validate_files(self):
        for path,version in self.versions.items():
            if file_version(path)!=version:
                raise RuntimeError('Model release changed after checksum verification; restart with a verified release')

    def _read(self):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if b'\n' in self.buffer:
                line,self.buffer=self.buffer.split(b'\n',1)
                marker=line.find(b'WCIS_RESULT ')
                if marker>=0:
                    value=json.loads(line[marker+len(b'WCIS_RESULT '):])
                    if value.get('status')=='error':raise RuntimeError(value.get('message','NPU worker failed'))
                    return value
                continue
            if select.select([self.process.stdout],[],[],max(0,deadline-time.monotonic()))[0]:
                data=os.read(self.process.stdout.fileno(),65536)
                if not data:raise RuntimeError('Model cache exited; no automatic retry')
                self.stdout.write(data);self.stdout.flush();self.buffer+=data
        raise TimeoutError('NPU worker deadline exceeded; review hardware before retry')

    def forward(self,role,data,out,stem,retained_frame=None):
        if not self.busy.acquire(blocking=False):raise RuntimeError('Model backend already processing a request')
        try:
            started=time.monotonic()
            if self.broken or self.process.poll() is not None:raise RuntimeError('Model cache unavailable')
            with tempfile.TemporaryDirectory(prefix='wcis-face-npu-',dir='/dev/shm') as exchange:
                directory=Path(exchange);path=directory/'input.f32';output=directory/'output'
                np.asarray(data,dtype=np.float32).tofile(str(path))
                command=dict(role=role,input_f32=str(path),output_directory=str(output))
                if retained_frame is not None:command['retained_frame']=retained_frame
                self.process.stdin.write((json.dumps(command)+'\n').encode());self.process.stdin.flush()
                result=self._read()
                if (result.get('status')!='forwarded' or result.get('npu_bound_ops',0)<1
                    or result.get('device_closed') is not True
                    or result.get('worker_pid')!=self.process.pid):
                    raise RuntimeError('Missing isolated NPU completion evidence')
                if retained_frame is not None and (result.get('frame_preserved') is not True
                        or result.get('frame_id')!=retained_frame['frame_id']
                        or result.get('frame_token')!=retained_frame['frame_token']):
                    raise RuntimeError('NPU did not preserve the active DDR frame lease')
                values=[]
                for record in result['outputs']:
                    actual=Path(record['file']);expected=output/(str(record['index'])+'.f32')
                    if actual!=expected:raise RuntimeError('Unexpected NPU output path')
                    array=np.fromfile(actual,dtype=np.float32)
                    if len(array)!=record['elements'] or not np.all(np.isfinite(array)):
                        raise RuntimeError('Corrupt NPU output')
                    record['sha256']=sha(actual);record.pop('file')
                    values.append(array)
                result['tensor_transport']='bounded_tmpfs'
                result['outputs_retained']=False
            result['host_call_ms']=(time.monotonic()-started)*1000
            save(out/'timing'/(stem+'-'+role+'.json'),result)
            return values,result
        except BaseException:
            self.broken=True
            raise
        finally:self.busy.release()

    def close(self):
        if self.process is not None:
            if self.process.stdin and not self.process.stdin.closed:self.process.stdin.close()
            # EOF drains the current worker. Never SIGKILL an SDK/DMA owner.
            self.process.wait(timeout=35)
            self.process.stdout.close()
        self.stderr.close();self.stdout.close()


class BackendRequest:
    def __init__(self,backend,out,retained_frame=None):
        self.backend,self.out=backend,out
        self.retained_frame=copy.deepcopy(retained_frame)
    def forward(self,role,data,stem):return self.backend.forward(role,data,self.out,stem,self.retained_frame)
    def close(self):pass  # CPU models survive; hardware leases do not.


class ModelBackend:
    def __init__(self,root,executable):
        self.root=Path(root)
        self.busy=threading.Lock()
        self.workers={}
        try:
            for role in ('yunet','mobilefacenet'):
                self.workers[role]=_ModelProcess(self.root,executable,role)
        except BaseException:
            self.close()
            raise
        self.ready=dict(model_lifecycle='resident_process_per_model',
            workers={role:worker.ready for role,worker in self.workers.items()})

    @property
    def broken(self):
        return len(self.workers)!=2 or any(w.broken or w.process.poll() is not None for w in self.workers.values())

    def request(self,out,retained_frame=None):
        if self.broken:raise RuntimeError('Model backend unavailable; no automatic restart or fallback')
        self.validate_release()
        return BackendRequest(self,Path(out),retained_frame)

    def validate_release(self):
        for worker in self.workers.values():worker.validate_files()

    def forward(self,role,data,out,stem,retained_frame=None):
        if role not in self.workers:raise ValueError('Unknown model role')
        size=640 if role=='yunet' else 112
        if np.asarray(data).shape not in ((size,size,3),(1,size,size,3)):
            raise ValueError('Input tensor does not match the fixed model contract')
        if not self.busy.acquire(blocking=False):raise RuntimeError('Model backend is busy; do not queue stale frames')
        try:
            if self.broken:raise RuntimeError('Model backend unavailable')
            return self.workers[role].forward(role,data,out,stem,retained_frame)
        finally:self.busy.release()

    def close(self):
        errors=[]
        for worker in self.workers.values():
            try:worker.close()
            except Exception as e:errors.append(e)
        if errors:raise errors[0]
