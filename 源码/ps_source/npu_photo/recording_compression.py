"""Low priority, interruptible software compression of completed recordings.

Original media/index/summary are never rewritten. Only verified smaller copies
are published. No SDK, VPU or camera device is opened by this worker.
"""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time

from recording_library import ID, sync_dir

MIB = 1024 ** 2
PROFILE = 'x264-crf18-medium-v1'


class Interrupted(RuntimeError):
    pass


def fingerprint(path):
    s = path.stat()
    return dict(size=s.st_size, mtime_ns=s.st_mtime_ns)


def cpu_sample():
    values = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    return sum(values), values[3] + values[4]


class IdleCompression:
    def __init__(self, library, recorder, stop, *, idle_seconds=60, idle_check=None):
        self.library, self.recorder, self.stop = library, recorder, stop
        self.store = library.store
        self.lock = threading.RLock()
        self.policy_path = self.store.root / 'compression-policy.json'
        self.enabled = True
        if self.policy_path.exists():
            q = json.loads(self.policy_path.read_text())
            if set(q) != {'enabled'} or type(q['enabled']) is not bool:
                raise ValueError('Invalid compression policy')
            self.enabled = q['enabled']
        self.idle_seconds, self.idle_check = idle_seconds, idle_check
        self.idle_since = None
        self.phase, self.current, self.error = 'waiting', None, None
        self.cpu_previous = None
        self.cpu_checked_at, self.cpu_busy = 0., True
        self.reason = 'Waiting for idle window'
        # Exclusive recorder lock is already held before construction. Scratch
        # lives only here; crash remnants are never published as playable copies.
        self.work_root = self.store.root / '.compression-work'
        if self.work_root.is_symlink():
            raise ValueError('Unexpected compression scratch symlink')
        self.work_root.mkdir(exist_ok=True)
        self.work_bytes = sum(p.stat().st_size for p in self.work_root.rglob('*') if p.is_file())
        self.store.account(self.work_bytes)
        self._clear_work()

    def _clear_work(self):
        # Never follow symlinks or delete outside this fixed owned directory.
        for p in self.work_root.iterdir():
            if p.is_dir() or p.is_symlink():
                raise ValueError('Unexpected compression scratch entry')
            p.unlink()
        self.store.account(-self.work_bytes)
        self.work_bytes = 0

    def _account_work(self):
        size = sum(p.stat().st_size for p in self.work_root.iterdir() if p.is_file())
        self.store.account(size - self.work_bytes)
        self.work_bytes = size

    def set_policy(self, q):
        if not isinstance(q, dict) or set(q) != {'enabled'} or type(q['enabled']) is not bool:
            raise ValueError('Compression policy needs enabled (boolean)')
        with self.lock:
            self.store.guard()
            self.library.save(self.policy_path, q)
            self.enabled = q['enabled']
            self.idle_since = None
        return self.status()

    def status(self):
        with self.lock:
            return dict(enabled=self.enabled, phase=self.phase, current=self.current,
                        reason=self.reason, error=self.error, profile=PROFILE,
                        idle_seconds=self.idle_seconds, originals_retained=True,
                        cpu_duty_fraction=.15, scratch_bytes=self.work_bytes)

    def idle(self):
        if self.stop.is_set() or not self.enabled:
            self.reason = 'Disabled' if not self.enabled else 'Stopping'
            self.idle_since = None
            return False
        q = self.recorder.status()
        with self.library.lock:
            readers = any(n for key,n in self.library.readers.items() if key != self.current)
            # Our input pin is one reader; any additional reader is foreground work.
            readers = readers or bool(self.current and self.library.readers.get(self.current, 0) > 1)
            trashed = bool(self.current and self.library._marker(self.current))
        reason = None
        if q['state'] not in ('idle', 'armed') or q['queue_bytes'] or q['error']:
            reason = 'Recorder busy or unavailable'
        elif readers:
            reason = 'Playback or download in progress'
        elif trashed:
            raise Interrupted('Recording moved to trash')
        elif self.idle_check is not None:
            if not self.idle_check():
                reason = 'System busy'
        else:
            if time.monotonic()-self.cpu_checked_at >= 1:
                now = cpu_sample()
                previous, self.cpu_previous = self.cpu_previous, now
                self.cpu_checked_at = time.monotonic()
                self.cpu_busy = (previous is None or now[0] <= previous[0] or
                                 1-(now[1]-previous[1])/(now[0]-previous[0]) > .15)
            if self.cpu_busy:
                reason = 'System CPU busy'
            elif os.getloadavg()[0] > .8:
                reason = 'System load busy'
        if reason:
            self.reason, self.idle_since = reason, None
            return False
        if self.idle_since is None:
            self.idle_since = time.monotonic()
        self.reason = 'Waiting for idle window'
        if time.monotonic()-self.idle_since < self.idle_seconds:
            return False
        self.reason = 'Idle; software encoder limited to 15% of one CPU core'
        return True

    def checkpoint(self):
        while not self.stop.is_set():
            if not self.enabled:
                raise Interrupted('Compression disabled; original retained')
            if self.idle():
                return
            self.phase = 'paused'
            self.stop.wait(.5)
        raise Interrupted('Compression stopped; original retained')

    def command(self, args, *, output=None, max_bytes=None):
        """No shell. Stop child between short duty windows and while busy."""
        log = self.work_root / 'process.log'
        self.checkpoint()
        def suspend(process, sig):
            try:
                process.send_signal(sig)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 6*3600
        with log.open('wb') as f:
            cpu = max(os.sched_getaffinity(0))
            p = subprocess.Popen(['taskset','-c',str(cpu),'nice','-n','19'] + args, stdin=subprocess.DEVNULL,
                                 stdout=f, stderr=subprocess.STDOUT,
                                 env=dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1'))
            try:
                while p.poll() is None:
                    suspend(p, signal.SIGSTOP)
                    self._account_work()
                    self.store.guard()
                    self.store.admit(MIB)
                    if output and max_bytes and output.exists() and output.stat().st_size >= max_bytes:
                        raise ValueError('Compressed copy exceeds saving budget')
                    if time.monotonic() > deadline:
                        raise RuntimeError('Compression time budget exceeded')
                    self.checkpoint()
                    self.phase = 'working'
                    suspend(p, signal.SIGCONT)
                    self.stop.wait(.15)
                    if p.poll() is None:
                        suspend(p, signal.SIGSTOP)
                    self.stop.wait(.85)
                if p.returncode:
                    raise RuntimeError('FFmpeg failed: '+log.read_text(errors='replace')[-500:])
            finally:
                if p.poll() is None:
                    p.terminate()
                    suspend(p, signal.SIGCONT)
                    try:
                        p.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        p.kill()
                        p.wait()
                self._account_work()
        return log.read_text(errors='replace')

    def ffmpeg(self, args, **kwargs):
        return self.command(['ffmpeg','-nostdin','-hide_banner','-v','info','-xerror',
                             '-filter_threads','1','-filter_complex_threads','1'] + args, **kwargs)

    def probe(self, path):
        text = self.command(['ffprobe','-v','error','-threads','1','-select_streams','v:0',
                             '-show_streams','-show_frames','-show_entries',
                             'stream=width,height,codec_name:frame=best_effort_timestamp_time',
                             '-of','json',str(path)])
        return json.loads(text)

    def candidate(self):
        with self.library.lock:
            self.store.guard()
            for p in sorted(self.store.root.glob('rec-*.json')):
                if not ID.fullmatch(p.stem) or self.library._marker(p.stem) or self.library.readers.get(p.stem):
                    continue
                try:
                    q = self.library._summary(p.stem)
                    if q.get('format') != 'h264_mp4':
                        continue  # Legacy MJPEG is deliberately outside this feature.
                    media = self.library.path(p.stem, '.mp4')
                    sig = fingerprint(media)
                    result = self.library.compression(p.stem)
                    if result and result.get('source') == sig and result.get('profile') == PROFILE:
                        if result['state'] != 'error' or time.time()-result.get('completed_at',0) < 3600:
                            continue
                    return p.stem
                except (OSError, ValueError, KeyError, TypeError):
                    continue

    def compress(self, key):
        self.current, self.error = key, None
        source_sig = None
        result = None
        try:
            with self.library.lock:
                q = self.library._summary(key)
                if q.get('format') != 'h264_mp4':
                    raise ValueError('Idle compression supports only H.264 / MP4')
            with self.library.opened(key, '.mp4') as (_, q):
                media = self.library.path(key, '.mp4')
                source_sig = fingerprint(media)
                max_bytes = min(256*MIB, int(source_sig['size']*.9))
                if source_sig['size'] < 256*1024:
                    result = dict(state='skipped', reason='Original already small (under 256 KiB)')
                elif q['first']['width'] > 960 or q['first']['height'] > 540:
                    result = dict(state='skipped', reason='Dimensions exceed current 960x540 memory profile')
                else:
                    self.store.admit(max_bytes+4*MIB)
                    inputs = ['-i',str(media)]
                    out = self.work_root/'output.mp4'
                    self.ffmpeg(['-threads','1']+inputs+['-map','0:v:0','-an','-vsync','0',
                                '-c:v','libx264','-threads','1','-preset','medium','-crf','18',
                                '-movflags','+faststart',
                                '-fs',str(max_bytes+MIB),'-y',str(out)], output=out, max_bytes=max_bytes+MIB)
                    if out.stat().st_size > max_bytes:
                        result = dict(state='skipped',reason='Less than 10% smaller')
                    else:
                        probe = self.probe(out)
                        s = probe['streams'][0]
                        times = [float(f['best_effort_timestamp_time']) for f in probe['frames']]
                        original = self.probe(media)
                        if original['streams'][0]['codec_name'] != 'h264':
                            raise ValueError('Source is not H.264')
                        expected = [float(f['best_effort_timestamp_time']) for f in original['frames']]
                        expected = [t-expected[0] for t in expected]
                        if (len(times)!=q['frames'] or len(times)!=len(expected) or
                                any(abs(a-b)>.001 for a,b in zip(times,expected)) or
                                s['width']!=q['first']['width'] or s['height']!=q['first']['height']):
                            raise ValueError('Compressed frames, dimensions or timeline disagree: '
                                             +str(dict(frames=len(times),expected_frames=len(expected),summary_frames=q['frames'],
                                                       width=s['width'],height=s['height'],
                                                       max_time_error=max((abs(a-b) for a,b in zip(times,expected)),default=0))))
                        metric = self.ffmpeg(['-threads','1']+inputs+['-threads','1','-i',str(out),
                            '-lavfi','[0:v]settb=AVTB,setpts=N/(30*TB)[a];[1:v]settb=AVTB,setpts=N/(30*TB)[b];[a][b]ssim',
                            '-an','-f','null','-'])
                        matches = re.findall(r'SSIM .*?All:([0-9.]+)',metric)
                        if not matches or float(matches[-1]) < .98:
                            raise ValueError('SSIM below 0.98 or unavailable; original retained')
                        size = out.stat().st_size
                        result = dict(state='complete',bytes=size,original_bytes=source_sig['size'],
                                      potential_saving_bytes=source_sig['size']-size,
                                      ssim=float(matches[-1]),frames=len(times),width=s['width'],height=s['height'],
                                      duration_s=times[-1],codec='h264',original_retained=True)
                        with self.library.lock:
                            if self.library._marker(key) or fingerprint(media)!=source_sig:
                                raise RuntimeError('Original changed or moved to trash')
                            target = self.library.path(key,'.compressed.mp4')
                            # Publish only after full decode, quality, timing and size checks.
                            with out.open('rb') as f:
                                os.fsync(f.fileno())
                            old_size = target.stat().st_size if target.exists() else 0
                            out.replace(target)
                            self.work_bytes -= size
                            self.store.account(-old_size)
                            sync_dir(self.store.root)
        except Interrupted:
            result = None
        except Exception as e:
            self.error = str(e)
            result = dict(state='error',reason=str(e))
        finally:
            try:
                if result is not None and source_sig is not None:
                    result.update(source=source_sig, profile=PROFILE,completed_at=time.time())
                    with self.library.lock:
                        # A purge may have completed after the input pin closed.
                        if self.library.path(key,'.json').exists() and not self.library._marker(key):
                            path = self.library.path(key,'.compression.json')
                            old_size = path.stat().st_size if path.exists() else 0
                            self.library.save(path,result)
                            self.store.account(path.stat().st_size-old_size)
            finally:
                self._clear_work()
                self.current = None
                self.phase = 'waiting'
        return result

    def run(self):
        while not self.stop.is_set():
            try:
                if self.idle():
                    key = self.candidate()
                    if key:
                        self.compress(key)
                    else:
                        self.phase, self.reason = 'up_to_date','No eligible unprocessed recordings'
                else:
                    self.phase = 'waiting'
            except Exception as e:
                self.error, self.phase = str(e),'error'
            self.stop.wait(1)
