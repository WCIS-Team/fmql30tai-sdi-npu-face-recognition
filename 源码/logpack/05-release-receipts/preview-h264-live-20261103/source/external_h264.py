"""Hardware H264 worker and capture-time ledger; the SDK stays in CameraOwner."""
from collections import OrderedDict
import json
import errno
import os
from pathlib import Path
import subprocess
import threading
import time
from h264_fragments import timing


def atomic(path, value):
    pending = path.with_suffix(path.suffix + '.pending')
    pending.write_text(json.dumps(value), encoding='utf-8')
    pending.replace(path)


class Journal:
    def __init__(self, path, limit=3600):
        self.path = Path(path)
        self.limit = limit
        self.stream = None
        self.inode = None
        self.partial = ''
        self.rows = OrderedDict()

    def _read(self):
        text = self.partial + self.stream.read()
        lines = text.split('\n')
        self.partial = lines.pop()
        if len(self.partial) > 2048:
            raise ValueError('Capture journal row exceeds bounds')
        for line in lines:
            if not line:
                continue
            row = json.loads(line)
            index = row['input_index']
            if not isinstance(index, int) or index < 0:
                raise ValueError('Invalid capture index')
            if self.rows and index != next(reversed(self.rows)) + 1:
                raise ValueError('Capture journal is discontinuous')
            if not isinstance(row['frame_id'], int) or row['frame_id'] < 0:
                raise ValueError('Invalid source frame')
            self.rows[index] = row
            while len(self.rows) > self.limit:
                self.rows.popitem(last=False)

    def update(self):
        if self.stream is not None:
            self._read()
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return
        if self.inode != st.st_ino:
            if self.stream is not None:
                self._read()
                self.stream.close()
                if self.partial:
                    raise ValueError('Rotated capture journal contains a partial row')
            if self.path.is_symlink():
                raise ValueError('Unexpected capture journal symlink')
            self.stream = self.path.open(encoding='utf-8')
            self.inode = st.st_ino
            self._read()

    def capture(self, offset, samples, fps):
        index = round(offset * fps)
        if abs(index / fps - offset) > 1 / 90000:
            raise ValueError('Video timestamp does not match source frame cadence')
        return self.capture_index(index, samples, fps)

    def capture_index(self, index, samples, fps):
        rows = [self.rows.get(i) for i in range(index, index + samples)]
        if not rows or any(row is None for row in rows):
            return None
        if any(row['synthetic'] or row['frame_id'] == 0 for row in rows):
            return None
        if any(b['captured_at'] <= a['captured_at'] or b['frame_id'] <= a['frame_id']
               for a, b in zip(rows, rows[1:])):
            raise ValueError('Source frame timeline is not increasing')
        return dict(start=rows[0]['captured_at'], end=rows[-1]['captured_at'] + 1 / fps,
                    first_frame=rows[0]['frame_id'], last_frame=rows[-1]['frame_id'],
                    first_index=index, end_index=index + samples, samples=samples)

    def close(self):
        if self.stream is not None:
            self.stream.close()


class ExternalH264:
    def __init__(self, work, fps=30, ffmpeg='/usr/bin/ffmpeg'):
        if fps != 30:
            raise ValueError('External H264 currently requires the verified 30 fps cadence')
        self.work = Path(work)
        self.fps = fps
        self.root = self.work / 'hls'
        self.root.mkdir()
        self.fifo = self.work / 'video-input.fifo'
        os.mkfifo(self.fifo, 0o600)
        self.primed = self.work / 'video-primed.bin'
        self.stop = threading.Event()
        self.owner = None
        self.identity = None
        self.error = None
        self.threads = []
        self.journal = Journal(self.work / 'raw-inputs.jsonl')
        from h264_live import LiveFragments
        self.live_journal = Journal(self.work / 'raw-inputs.jsonl')
        self.live = LiveFragments(self._live_capture)
        self.encoder = self.muxer = None
        self.fifo_keeper = None
        self.keeper_lock = threading.Lock()
        self.done_segments = set()
        self.next_segment = 0
        self.next_input = 0
        self.playlist_token = None
        self.playlist_changed = 0
        self.read_cache = {}
        self.published_media = None
        self.published_at = 0
        encode = [ffmpeg, '-v', 'warning', '-nostdin', '-threads', '2', '-f', 'rawvideo',
                  '-pixel_format', 'uyvy422', '-video_size', '960x540', '-framerate', str(fps),
                  '-i', str(self.fifo), '-an', '-c:v', 'h264_v4l2m2m', '-pix_fmt', 'uyvy422',
                  '-num_output_buffers', '6', '-num_capture_buffers', '4', '-b:v', '2M',
                  '-g', '30', '-bf', '0', '-flush_packets', '1', '-f', 'h264', 'pipe:1']
        mux = [ffmpeg, '-v', 'warning', '-nostdin', '-fflags', '+genpts', '-f', 'h264',
               '-framerate', str(fps), '-probesize', '32', '-analyzeduration', '0', '-i', 'pipe:0',
               '-map', '0:v:0', '-c:v', 'copy', '-f', 'hls', '-hls_time', '1',
               '-hls_list_size', '12', '-hls_segment_type', 'fmp4', '-hls_flags',
               'delete_segments+independent_segments+temp_file', '-hls_fmp4_init_filename', 'init.mp4',
               '-hls_segment_filename', str(self.root / 'seg-%09d.m4s'), '-y', str(self.root / 'index.m3u8')]
        mux += ['-map','0:v:0','-c:v','copy','-f','mp4','-movflags',
                'empty_moov+default_base_moof+frag_every_frame','-flush_packets','1','pipe:1']
        try:
            worker_env = dict(os.environ, OPENBLAS_NUM_THREADS='1')
            self.encoder = subprocess.Popen(encode, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0, env=worker_env)
            self.muxer = subprocess.Popen(mux, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, bufsize=0, env=worker_env)
            self._thread(self._log, self.encoder.stderr, self.work / 'h264-encoder.log')
            self._thread(self._log, self.muxer.stderr, self.work / 'h264-muxer.log')
            self._thread(self._live_output)
            self._thread(self._relay)
            self._wait_reader()
        except BaseException:
            self.close(abort=True)
            raise

    def _wait_reader(self):
        deadline = time.monotonic() + 10
        while True:
            if self.encoder.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('H264 input reader did not become ready')
            try:
                # Keep this writer open until native has submitted frames. An
                # open/close probe would deliver premature EOF to FFmpeg.
                self.fifo_keeper = os.open(self.fifo, os.O_WRONLY | os.O_NONBLOCK)
                return
            except OSError as error:
                if error.errno != errno.ENXIO:
                    raise
                time.sleep(.02)

    def _release_keeper(self):
        with self.keeper_lock:
            if self.fifo_keeper is not None:
                descriptor, self.fifo_keeper = self.fifo_keeper, None
                os.close(descriptor)

    def environment(self):
        return dict(WCIS_PREVIEW_CODEC='h264', WCIS_PREVIEW_SIZE='540', WCIS_H264_INPUT='nv12',
                    WCIS_H264_VPU_FIRST='1', WCIS_H264_SDK_PAUSE='0', WCIS_H264_COMMAND_PAUSE='0',
                    WCIS_RAW_PRIME_FRAMES='60', WCIS_RAW_PACKED_UYVY='1',
                    WCIS_RAW_SINK=str(self.fifo), WCIS_RAW_FIRST_OUTPUT=str(self.primed))

    def _thread(self, target, *args):
        thread = threading.Thread(target=target, args=args, daemon=True)
        self.threads.append(thread)
        thread.start()

    def _log(self, stream, path):
        kept = 0
        with path.open('wb') as output:
            while True:
                data = stream.read(8192)
                if not data:
                    break
                if kept < 1024 * 1024:
                    part = data[:1024 * 1024 - kept]
                    output.write(part)
                    output.flush()
                    kept += len(part)

    def _relay(self):
        try:
            first = True
            while True:
                data = self.encoder.stdout.read(65536)
                if not data:
                    break
                if first:
                    self.primed.write_bytes(data[:65536])
                    first = False
                    self._release_keeper()
                view = memoryview(data)
                while view:
                    written = self.muxer.stdin.write(view)
                    if not written:
                        raise RuntimeError('H264 parser input closed')
                    view = view[written:]
        except BaseException as error:
            self.error = str(error)
        finally:
            if self.muxer and self.muxer.stdin:
                self.muxer.stdin.close()

    def attach(self, owner, control):
        self.owner = owner
        self.identity = dict(boot_id=control['boot_id'], pid=control['pid'], session=control['session'])
        self._thread(self._monitor)

    def _live_capture(self, index):
        self.live_journal.update()
        if index < 60:
            row = self.live_journal.rows.get(index)
            if row is None or not row['synthetic']:
                raise ValueError('Unverified live priming frame')
            return None
        value = self.live_journal.capture_index(index, 1, self.fps)
        if value is None:
            raise ValueError('Live frame lacks camera capture identity')
        return value

    def _live_output(self):
        failed = False
        try:
            while True:
                data = self.muxer.stdout.read(65536)
                if not data:
                    break
                if not failed:
                    try:
                        self.live.feed(data)
                    except Exception as error:
                        # Always drain stdout: a broken preview must not stall recording.
                        self.live.fail(error); failed = True
        finally:
            self.live.close()

    def _cached_read(self, path, kind):
        # Keep checking existence/replacement on every poll. Only immutable
        # contents are reused; this cache never bypasses the freshness checks.
        if path.is_symlink():
            raise ValueError('Unexpected H264 metadata symlink')
        st = path.stat()
        token = (st.st_dev, st.st_ino, st.st_mtime_ns, st.st_ctime_ns, st.st_size)
        cached = self.read_cache.get(path)
        if cached is not None and cached[0] == token:
            return cached[1]
        value = path.read_bytes() if kind == 'bytes' else path.read_text()
        if kind == 'json':
            value = json.loads(value)
        self.read_cache[path] = (token, value)
        return value

    def _observe(self):
        self.owner.guard()
        if self.encoder.poll() is not None or self.muxer.poll() is not None:
            raise RuntimeError('H264 worker exited')
        self.journal.update()
        init_path = self.root / 'init.mp4'
        init = self._cached_read(init_path, 'bytes')
        playlist = self.root / 'index.m3u8'
        st = playlist.stat()
        token = (st.st_ino, st.st_mtime_ns, st.st_size)
        if token != self.playlist_token:
            self.playlist_token, self.playlist_changed = token, time.monotonic()
        if time.monotonic() - self.playlist_changed > 4:
            raise RuntimeError('H264 playlist is stale')
        names = [line for line in self._cached_read(playlist, 'text').splitlines() if line and not line.startswith('#')]
        retained = {init_path, playlist} | {self.root / name.replace('.m4s', '.capture.json') for name in names}
        self.read_cache = {path: value for path, value in self.read_cache.items() if path in retained}
        latest = None
        for name in names:
            if not __import__('re').fullmatch(r'seg-[0-9]{9}\.m4s', name):
                raise ValueError('Unexpected H264 segment name')
            path = self.root / name
            if path.is_symlink() or path.stat().st_size > 8 * 1024**2:
                raise ValueError('Unexpected H264 segment')
            metadata = path.with_suffix('.capture.json')
            if name not in self.done_segments:
                offset, samples = timing(init, path.read_bytes())
                number = int(name[4:-4])
                # The parser's integer time base accumulates rounding error.
                # Count actual samples, rejecting missing fragments, rather than
                # rounding its nominal PTS into a source frame number.
                if number != self.next_segment:
                    raise ValueError('H264 fragment sequence is discontinuous')
                if any(i not in self.journal.rows for i in range(self.next_input, self.next_input + samples)):
                    break
                capture = self.journal.capture_index(self.next_input, samples, self.fps)
                if capture is not None:
                    atomic(metadata, dict(self.identity, **capture))
                self.done_segments.add(name)
                self.next_segment += 1
                self.next_input += samples
            if not metadata.exists():
                continue
            capture = self._cached_read(metadata, 'json')
            if any(capture.get(key) != self.identity[key] for key in ('boot_id', 'pid', 'session')):
                raise ValueError('H264 capture metadata belongs to another session')
            latest = capture
        if latest is None or not 0 <= time.monotonic() - latest['end'] <= 4:
            raise RuntimeError('No fresh camera-backed H264 segment')
        for old in self.root.glob('seg-?????????.capture.json'):
            if not old.with_name(old.name.replace('.capture.json', '.m4s')).exists():
                old.unlink()
        self.done_segments.intersection_update(names)
        media = dict(self.identity, ready=True, codec='h264', external_h264=True, width=960, height=540,
                     encoder_pid=self.encoder.pid, muxer_pid=self.muxer.pid,
                     h264_encoded_at=latest['end'], h264_origin=latest['start'] - latest['first_index'] / self.fps,
                     encoded=max(0, latest['end_index'] - 60), frame_id=latest['last_frame'])
        now = time.monotonic()
        # Readers expire these heartbeats after 2.5/4 seconds. Publish new
        # frames immediately, and refresh unchanged healthy state each second.
        if media != self.published_media or now - self.published_at >= 1:
            atomic(self.work / 'external-video.json', dict(media, updated_at=now))
            atomic(self.root / 'packager.json', dict(self.identity, updated_at=now, error=None))
            self.published_media, self.published_at = media, now

    def _monitor(self):
        while not self.stop.is_set():
            previous = self.error
            try:
                self._observe()
                self.error = None
            except (OSError, ValueError, KeyError, RuntimeError) as error:
                self.error = str(error)
                self.published_media = None  # Recovery must overwrite unavailable immediately.
                atomic(self.work / 'external-video.json', dict(self.identity, ready=False,
                       updated_at=time.monotonic(), error=self.error))
            if self.error != previous:
                print('H264 media:', self.error or 'ready', flush=True)
            self.stop.wait(.2)

    def close(self, abort=False):
        self._release_keeper()
        if abort:
            for process in (self.encoder, self.muxer):
                if process is not None and process.poll() is None:
                    process.terminate()
        try:
            if self.encoder is not None:
                self.encoder.wait(timeout=20)
            if self.muxer is not None:
                self.muxer.wait(timeout=20)
            if not abort and any(p is not None and p.returncode != 0 for p in (self.encoder, self.muxer)):
                raise RuntimeError('H264 workers did not close normally')
        finally:
            self.stop.set()
            for thread in self.threads:
                thread.join(timeout=3)
            self.journal.close()
            self.live_journal.close()
            if abort:
                # Startup workspaces are temporary. Preserve bounded diagnostics
                # before their owner removes them, without reopening any device.
                report = dict(work=str(self.work),live_error=self.live.error,
                              encoder_exit=None if self.encoder is None else self.encoder.poll(),
                              muxer_exit=None if self.muxer is None else self.muxer.poll(),logs={})
                for name in ('h264-encoder.log','h264-muxer.log','native-stdout.log','native-stderr.log','fault.json'):
                    path=self.work/name
                    if path.is_file():
                        with path.open('rb') as stream:
                            stream.seek(max(0,path.stat().st_size-65536))
                            report['logs'][name]=stream.read(65536).decode('utf-8',errors='replace')
                atomic(Path(__file__).with_name('h264-abort-'+self.work.name+'.json'),report)
