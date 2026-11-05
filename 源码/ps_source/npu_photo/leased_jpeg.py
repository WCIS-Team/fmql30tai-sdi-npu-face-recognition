"""Synchronous JPG1 ModelBackend adapter borrowing one immutable FAC1 frame.

The caller holds the existing hardware lock across all frame consumers. Idle
worker processes own no SDK device. No camera queue, recording policy or UI.
"""
import json
import os
from pathlib import Path
import select
import subprocess
import threading
import time


class LeasedJPEG:
    def __init__(self, executable, work, fault_marker):
        self.marker=Path(fault_marker)
        work=Path(work);work.mkdir(parents=True,exist_ok=False)
        self.buffer=b'';self.broken=False;self.busy=threading.Lock();self.ready={}
        self.stdout=(work/'stdout.log').open('wb');self.stderr=(work/'stderr.log').open('wb')
        self.process=subprocess.Popen([str(executable),'--serve'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=self.stderr,start_new_session=True)
        try:
            ready=self._read()
            if ready.get('status')!='ready' or ready.get('device_opened') is not False or ready.get('frame_leases') is not True:
                raise RuntimeError('JPEG worker must start without a hardware owner')
            self.ready=ready
        except BaseException:
            self.broken=True;self.close();raise

    def _read(self):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if b'\n' in self.buffer:
                line,self.buffer=self.buffer.split(b'\n',1)
                marker=b'WCIS_LEASED_JPEG_RESULT '
                if marker in line:
                    response=json.loads(line.split(marker,1)[1])
                    if response.get('status')=='error':raise RuntimeError(response.get('message','JPEG failed'))
                    return response
                continue
            if select.select([self.process.stdout],[],[],max(0,deadline-time.monotonic()))[0]:
                data=os.read(self.process.stdout.fileno(),65536)
                if not data:raise RuntimeError('JPEG worker exited without completion')
                self.stdout.write(data);self.stdout.flush();self.buffer+=data
        raise TimeoutError('JPEG deadline; retain lock and drain worker before retry')

    def _command(self,value):
        if self.broken or self.process.poll() is not None:raise RuntimeError('JPEG worker unavailable')
        try:
            self.process.stdin.write((json.dumps(value)+'\n').encode());self.process.stdin.flush()
            return self._read()
        except BaseException:
            self.broken=True;raise

    def compress(self,lease,pts_us,source_sha256,output):
        if not self.busy.acquire(blocking=False):raise RuntimeError('JPEG already in flight; stale frames are not queued')
        try:
            if type(pts_us) is not int or not 0<=pts_us<2**63:raise ValueError('Invalid frame timestamp')
            if len(source_sha256)!=64 or any(c not in '0123456789abcdef' for c in source_sha256):
                raise ValueError('Invalid source digest')
            response=self._command(dict(op='frame',retained_frame=lease,pts_us=pts_us,
                source_sha256=source_sha256,output_jpeg=str(Path(output).resolve()),fault_marker=str(self.marker)))
            if (response.get('status')!='compressed' or response.get('frame_id')!=lease['frame_id']
                    or response.get('frame_token')!=lease['frame_token'] or response.get('pts_us')!=pts_us
                    or response.get('source_sha256')!=source_sha256 or response.get('source_uploaded') is not False
                    or response.get('frame_preserved') is not True or response.get('device_closed') is not True):
                self.broken=True;raise RuntimeError('JPEG completion/frame/ownership mismatch')
            return response
        finally:self.busy.release()

    def close(self):
        try:
            if self.process.poll() is None and not self.broken:
                response=self._command(dict(op='finish'))
                if response.get('status')!='closed' or response.get('device_closed') is not True:
                    self.broken=True;raise RuntimeError('JPEG failed to release hardware')
        finally:
            if self.process.stdin and not self.process.stdin.closed:self.process.stdin.close()
            # Preserve the caller's lock even if the SDK does not return within
            # the normal deadline. No SIGKILL or early recycling of DMA storage.
            try:self.process.wait(timeout=35)
            except subprocess.TimeoutExpired:
                self.broken=True
                boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
                self.marker.write_text(json.dumps(dict(boot_id=boot,source='leased_jpeg_drain',automatic_retry=False)))
                self.process.wait()
            self.process.stdout.close();self.stdout.close();self.stderr.close()
