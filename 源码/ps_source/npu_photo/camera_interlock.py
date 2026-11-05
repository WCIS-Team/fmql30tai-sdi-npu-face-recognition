"""Bounded SDK admission between photo inference and an owned SDI service."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import time
import uuid


class CameraInterlock:
    def __init__(self, config, release):
        self.config = json.loads(Path(config).read_text())
        self.release = Path(release)
        self.root = Path(self.config['root']).resolve()
        self.unit = self.config['unit']
        if self.unit != 'wcis-sdi-camera-live.service':
            raise ValueError('Unexpected camera service')
        self.marker = self.release.parents[1] / 'hardware-review-required.json'

    def boot(self):
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    def guard(self):
        boot = self.boot()
        proof = json.loads((self.root / 'boot-proof.json').read_text())
        if proof['boot_id'] != boot or proof['boot_files']['BOOT.bin'] != self.config['boot_sha256']:
            raise RuntimeError('Camera BOOT has not been verified for this boot')
        if self.marker.exists() and json.loads(self.marker.read_text()).get('boot_id') == boot:
            raise RuntimeError('Hardware review required; no automatic SDK reuse')
        return boot

    def state(self):
        p = subprocess.run(['systemctl', 'show', self.unit, '-p', 'ActiveState', '--value'],
                           capture_output=True, text=True, check=True, timeout=5)
        return p.stdout.strip()

    def quarantine(self, reason):
        if self.marker.exists() and json.loads(self.marker.read_text()).get('boot_id') == self.boot():
            return
        pending = self.marker.with_suffix('.camera.tmp')
        pending.write_text(json.dumps(dict(boot_id=self.boot(), reason=reason, automatic_retry=False)))
        pending.replace(self.marker)

    def current(self, boot):
        control = json.loads((self.root / 'current.json').read_text())
        session = control['session']
        if (not isinstance(session, str) or not re.fullmatch('[0-9a-f]{32}', session)
                or control['source'] != 'camera' or control['boot_id'] != boot
                or control['directory'] != '/dev/shm/wcis-vpu-camera-' + session):
            raise RuntimeError('Camera session identity mismatch')
        return control

    def snapshot(self, control):
        path = Path(control['directory']) / 'latest.frame'
        with path.open('rb') as f:
            packet = f.read(5 * 1024 * 1024 + 16389)
        if not 8 <= len(packet) <= 5 * 1024 * 1024 + 16388:
            raise ValueError('Invalid camera frame size')
        length = struct.unpack('<I', packet[:4])[0]
        if not 0 < length <= 16384 or len(packet) < 4 + length + 4:
            raise ValueError('Invalid camera metadata length')
        meta = json.loads(packet[4:4 + length]); jpeg = packet[4 + length:]
        age = time.monotonic() - meta['captured_at']
        if (meta['source'] != 'camera' or meta['boot_id'] != control['boot_id']
                or meta['pid'] != control['pid'] or meta['state'] != 'ready'
                or not 0 <= age <= 1.5 or meta['frame_id'] < 1
                or (meta['width'], meta['height']) != (960, 540)
                or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9')):
            raise ValueError('Camera frame is stale or belongs to another session')
        return dict(data=jpeg, identity=dict(meta, session=control['session'],
                    jpeg_sha256=hashlib.sha256(jpeg).hexdigest(), age_at_admission_s=age,
                    transport='VPU_JPEG_then_PS_decode_and_PL_upload'))

    def cleanup(self, control):
        directory = Path(control['directory'])
        expected = Path('/dev/shm') / ('wcis-vpu-camera-' + control['session'])
        if directory != expected or directory.resolve() != directory:
            raise RuntimeError('Refusing cleanup outside the owned camera session')
        # The worker is closed and a snapshot, if requested, is already copied.
        # Remove only its fixed filenames; never recursively delete a path.
        for name in ('latest.frame', 'latest.tmp', 'status.json', 'status.tmp'):
            try:(directory / name).unlink()
            except FileNotFoundError:pass
        directory.rmdir()

    def fresh_snapshot(self, boot):
        # A systemd Type=simple start returns before the new SDK owner publishes
        # its first frame. Wait on files only; never retry a failed SDK command.
        deadline = time.monotonic() + 4
        while True:
            self.guard()
            if self.state() != 'active':
                raise RuntimeError('摄像头未运行，请检查输入后重试')
            try:
                control = self.current(boot)
                return control, self.snapshot(control)
            except (OSError, ValueError, KeyError, TypeError, RuntimeError):
                if time.monotonic() >= deadline:
                    raise RuntimeError('摄像头正在恢复或等待输入，请稍后重试')
                time.sleep(.08)

    def warm_command(self, control, name, token):
        directory = Path(control['directory'])
        expected = Path('/dev/shm') / ('wcis-vpu-camera-' + control['session'])
        if directory != expected or directory.resolve() != directory:
            raise RuntimeError('Camera handoff directory mismatch')
        value = dict(boot_id=control['boot_id'], pid=control['pid'], token=token)
        temporary = directory / (name + '.tmp')
        temporary.write_text(json.dumps(value))
        temporary.replace(directory / name)

    def warm_pause(self, control):
        if control.get('handoff') != 'warm_process':
            raise RuntimeError('Camera worker does not support warm handoff')
        token = uuid.uuid4().hex
        self.warm_command(control, 'pause.request', token)
        deadline = time.monotonic() + 20
        while True:
            self.guard()
            if self.state() != 'active' or self.current(control['boot_id']) != control:
                raise RuntimeError('Camera owner changed during handoff')
            try:
                proof = json.loads((Path(control['directory']) / 'paused.json').read_text())
            except FileNotFoundError:proof = {}
            if (proof.get('token') == token and proof.get('pid') == control['pid']
                    and proof.get('boot_id') == control['boot_id'] and proof.get('device_closed') is True):
                return token
            if time.monotonic() >= deadline:
                raise RuntimeError('Camera did not confirm a clean warm SDK handoff')
            time.sleep(.005)

    @contextmanager
    def request(self, snapshot=False):
        request_started = time.monotonic()
        timings = {}
        with (self.release / 'camera-admission.lock').open('a') as admission:
            fcntl.flock(admission, fcntl.LOCK_EX | fcntl.LOCK_NB)
            boot = self.guard(); state = self.state()
            if state not in ('active', 'inactive'):
                raise RuntimeError('Camera is transitioning or failed; retry only after review')
            active = state == 'active'
            if snapshot and not active:
                raise RuntimeError('Live camera is not running')
            if snapshot:
                control, sample = self.fresh_snapshot(boot)
            else:
                control = self.current(boot) if active else None
                sample = None
            warm = active and self.config.get('handoff') == 'warm_process'
            timings['admission_and_snapshot_ms'] = (time.monotonic()-request_started)*1000
            phase_started = time.monotonic()
            pause_token = None
            if active:
                try:
                    if warm:pause_token = self.warm_pause(control)
                    else:
                        subprocess.run(['systemctl', 'stop', self.unit], check=True, timeout=20,
                                       capture_output=True, text=True)
                        self.guard()
                        result = json.loads((self.root / (control['session'] + '-result.json')).read_text())
                        if (self.state() != 'inactive' or result.get('exit_code') != 0
                                or result.get('boot_id') != boot or result.get('session') != control['session']):
                            raise RuntimeError('Camera did not confirm a clean SDK drain')
                except BaseException:
                    self.quarantine('Camera stop did not confirm a clean DMA/SDK drain')
                    raise
            # Probe the exact existing hardware lock before the inference code
            # takes it. The admission lock excludes all other photo requests.
            try:
                with (self.release / 'npu.lock').open('a') as hardware:
                    fcntl.flock(hardware, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BaseException:
                self.quarantine('Camera completion receipt did not release the hardware lock')
                raise
            timings['pause_and_lock_ms'] = (time.monotonic()-phase_started)*1000
            if sample is not None:sample['handoff_timing_ms'] = timings
            try:
                if active and not warm:self.cleanup(control)
                phase_started = time.monotonic()
                yield sample
            except ValueError:
                # Image/metadata validation errors are not hardware failures.
                raise
            except BaseException:
                self.quarantine('Inference did not confirm a clean PL/NPU completion')
                raise
            finally:
                timings['inference_and_cleanup_ms'] = (time.monotonic()-phase_started)*1000
                # A failed SDK transaction must never trigger an automatic retry.
                self.guard()
                phase_started = time.monotonic()
                if active:
                    if warm:self.warm_command(control, 'resume.request', pause_token)
                    else:
                        subprocess.run(['systemctl', 'start', self.unit], check=True, timeout=20,
                                       capture_output=True, text=True)
                timings['resume_command_ms'] = (time.monotonic()-phase_started)*1000
                timings['request_ms'] = (time.monotonic()-request_started)*1000
