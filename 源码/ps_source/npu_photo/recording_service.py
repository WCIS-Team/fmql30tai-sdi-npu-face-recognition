"""PS event recorder; never opens SDK/PL/VPU devices.

Supports the legacy VPU JPEG source and packaged H264 GOPs saved as MP4.
The recorder shares encoded media and never creates a second hardware owner.
"""
import argparse
from collections import deque
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlsplit, parse_qs
from urllib.request import Request, build_opener, ProxyHandler

SOURCE = 'PS_VPU_JPEG'
MIB = 1024 * 1024


def durable_json(path, value):
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)
    if hasattr(os, 'O_DIRECTORY'):
        fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class Storage:
    def __init__(self, root, mount, expected_uuid, quota=4 * 1024 * MIB, reserve=512 * MIB):
        self.mount = Path(mount).resolve(strict=True)
        info = json.loads(subprocess.check_output(
            ['findmnt', '-J', '-T', str(self.mount), '-o', 'TARGET,UUID,FSTYPE'], text=True))['filesystems'][0]
        if not self.mount.is_mount() or info != dict(target=str(self.mount), uuid=expected_uuid, fstype='ext4'):
            raise RuntimeError('Recording mount identity mismatch')
        self.root = Path(root).resolve()
        self.root.relative_to(self.mount)
        if self.root == self.mount:
            raise ValueError('Recording needs its own directory')
        self.device = self.mount.stat().st_dev
        self.root.mkdir(parents=True, exist_ok=True)
        self.quota, self.reserve = quota, reserve
        self.lock = threading.RLock()
        self.used = sum(p.stat().st_size for p in self.root.glob('rec-*') if p.is_file())
        self.guard()

    def account(self, size):
        with self.lock:
            self.used = max(0, self.used + size)

    def guard(self):
        if (not self.mount.is_mount() or self.mount.stat().st_dev != self.device
                or self.root.stat().st_dev != self.device):
            raise RuntimeError('Recording storage unavailable; no SD fallback')

    def admit(self, size):
        self.guard()
        if self.used + size + MIB > self.quota:
            raise RuntimeError('Recording quota reached; recordings retained, no automatic deletion')
        if shutil.disk_usage(self.root).free < self.reserve + size + MIB:
            raise RuntimeError('Recording storage reserve reached')


class Segment:
    def __init__(self, store, frame, event, segment_seconds):
        self.store = store
        store.admit(0)
        self.name = 'rec-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:12]
        self.base = store.root / self.name
        self.h264 = frame.get('codec') == 'h264'
        self.extension = '.mp4' if self.h264 else '.mjpeg'
        self.video = self.base.with_suffix(self.extension+'.part').open('xb')
        self.index = self.base.with_suffix('.frames.jsonl.part').open('xb')
        self.started = frame['captured_at']
        self.seconds = segment_seconds
        self.session = (frame['boot_id'], frame['session'])
        self.event = event
        self.count = self.bytes = 0
        self.first = self.last = None
        if self.h264:
            init=frame['_h264_init'];store.admit(len(init));self.video.write(init);store.account(len(init));self.bytes=len(init)

    def write(self, frame, jpeg):
        row = {k: frame[k] for k in ('boot_id', 'session', 'frame_id', 'captured_at', 'width', 'height')}
        row.update(offset=self.bytes, length=len(jpeg), timestamp_basis=frame.get('timestamp_basis'),
                   received_unix=frame['received_unix'], source=SOURCE)
        if self.h264:
            row.update(source='PS_VPU_H264',captured_end=frame['captured_end'],samples=frame['samples'],duration=frame['duration'],frame_id_basis=frame['frame_id_basis'])
            row.update({k:frame[k] for k in ('source_first_frame','source_last_frame','capture_time_basis') if k in frame})
        data = (json.dumps(row, separators=(',', ':')) + '\n').encode()
        self.store.admit(len(jpeg) + len(data))
        self.video.write(jpeg)
        self.index.write(data)
        self.store.account(len(jpeg) + len(data))
        self.bytes += len(jpeg)
        self.count += frame.get('samples',1) if self.h264 else 1
        self.first = self.first or row
        self.last = row

    def finish(self, reason):
        for f in (self.video, self.index):
            f.flush()
            os.fsync(f.fileno())
            f.close()
        if self.h264:
            # Stream-copy remux rebases the file timeline and builds a seekable MP4.
            # The original fMP4 remains identifiable until remux and fsync succeed.
            self.store.admit(self.bytes+MIB)
            source=self.base.with_suffix('.mp4.part');ready=self.base.with_suffix('.mp4.ready')
            process=subprocess.run(['ffmpeg','-v','error','-i',str(source),'-map','0:v:0','-c:v','copy','-movflags','+faststart','-f','mp4','-y',str(ready)],capture_output=True,timeout=60)
            if process.returncode:raise RuntimeError('H264 recording remux failed: '+process.stderr.decode(errors='replace')[-500:])
            final_bytes=ready.stat().st_size
            self.store.admit(final_bytes)
            with ready.open('rb') as f:os.fsync(f.fileno())
            ready.replace(self.base.with_suffix('.mp4'));source.unlink();self.store.account(final_bytes-self.bytes);self.bytes=final_bytes
            self.base.with_suffix('.frames.jsonl.part').replace(self.base.with_suffix('.frames.jsonl'))
        else:
            for suffix in ('.mjpeg', '.frames.jsonl'):
                self.base.with_suffix(suffix + '.part').replace(self.base.with_suffix(suffix))
        value = dict(id=self.name, state='complete', source='PS_VPU_H264' if self.h264 else SOURCE, format='h264_mp4' if self.h264 else 'raw_mjpeg_with_timestamp_index',
                     event=self.event, reason=reason, frames=self.count, bytes=self.bytes,
                     first=self.first, last=self.last,
                     capture_span_s=self.last.get('captured_end',self.last['captured_at']) - self.first['captured_at'])
        if self.h264:value['index_format']='source_fragment_capture_timestamps_not_mp4_byte_offsets'
        durable_json(self.base.with_suffix('.json'), value)
        self.store.account(self.base.with_suffix('.json').stat().st_size)
        return value

    def abandon(self):
        # Keep partial files identifiable. Never advertise failed fsync as complete.
        for f in (self.video, self.index):
            try:
                f.close()
            except OSError:
                pass


class Recorder:
    def __init__(self, store, *, tail=5., pre=2., segment=60., byte_limit=16*MIB, clock=time.monotonic):
        self.store, self.tail, self.pre, self.segment_seconds = store, tail, pre, segment
        self.limit, self.clock = byte_limit, clock
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.quit = threading.Event()
        self.mode = 'off'
        self.arm_at = self.deadline = 0.
        self.event = None
        self.active = False
        self.pending = deque()
        self.pending_bytes = 0
        self.ring = deque()
        self.ring_bytes = 0
        self.latest = None
        self.last_key = None
        self.source_ready = False
        self.error = None
        self.detection_error = None
        self.last_detection = None
        self.dropped = self.received = self.written = self.high_water = 0
        self.source_gaps = 0
        self.current = None
        self.thread = threading.Thread(target=self._writer, name='record-writer')

    def start(self):
        self.thread.start()

    def command(self, mode):
        if mode not in ('off', 'auto', 'manual'):
            raise ValueError('Mode must be off, auto or manual')
        with self.lock:
            if self.error and mode != 'off':
                raise RuntimeError('Recorder failed; inspect storage and restart service: ' + self.error)
            if mode != self.mode:
                self.mode = mode
                self.arm_at = self.clock()
                self.deadline = 0
                self.event = None
                self.active = False
            self.wake.set()

    def detection(self, result):
        now = self.clock()
        frame = result.get('camera_frame', {})
        with self.lock:
            latest = self.latest
            captured = frame.get('captured_at', float('-inf'))
            if (latest is None or not self.source_ready or not isinstance(captured, (int, float))
                    or not math.isfinite(captured) or not 0 <= now-captured <= 3
                    or any(frame.get(k) != latest[k] for k in ('boot_id', 'session'))
                    or type(result.get('face_count')) is not int or result['face_count'] < 0):
                self.detection_error = 'Detection is stale or belongs to another camera session'
                return False
            self.last_detection = dict(at=now, captured_at=captured, frame_id=frame.get('frame_id'),
                                       faces=result['face_count'], session=frame['session'])
            self.detection_error = None
            if self.mode == 'auto' and captured >= self.arm_at and result['face_count'] > 0:
                self.deadline = now + self.tail
            return True

    def ingest(self, frame, jpeg):
        now = self.clock()
        with self.lock:
            self.source_ready = bool(frame.get('ready')) and jpeg is not None
            if not self.source_ready:
                self.active = False
                self.event = None
                self.deadline = 0
                self.ring.clear()
                self.ring_bytes = 0
                self.wake.set()
                return
            h264=frame.get('codec')=='h264'
            if h264:
                if (frame.get('source')!='camera' or (frame.get('width'),frame.get('height')) not in ((960,540),(1920,1080))
                        or frame.get('vpu_enabled') is not True or not frame.get('_h264_init')
                        or not 0<=now-frame['captured_end']<=4 or not 0<frame['samples']<=300 or len(jpeg)>8*MIB):
                    raise ValueError('Expected fresh full-view 1080p VPU H264 fragment')
            elif (frame.get('source') != 'camera' or (frame.get('width'), frame.get('height')) != (960,540)
                    or frame.get('vpu_enabled') is not True or not jpeg.startswith(b'\xff\xd8')
                    or not jpeg.endswith(b'\xff\xd9') or len(jpeg) > 5*MIB
                    or not 0 <= now-frame['captured_at'] <= 2):
                raise ValueError('Expected fresh camera 960x540 VPU JPEG')
            key = (frame['boot_id'], frame['session'], frame['frame_id'])
            if self.last_key and key[:2] != self.last_key[:2]:
                self.ring.clear()
                self.ring_bytes = 0
                self.active = False
                self.event = None
                self.deadline = 0
            if self.last_key and key[:2] == self.last_key[:2] and key[2] <= self.last_key[2]:
                return
            if self.last_key and key[:2] == self.last_key[:2]:
                self.source_gaps += max(0, key[2]-self.last_key[2]-1)
            self.last_key = key
            frame = dict(frame, received_unix=time.time())
            self.latest = frame
            self.received += frame.get('samples',1) if h264 else 1
            while self.ring and (now-self.ring[0][0]['captured_at'] > self.pre
                                 or self.ring_bytes+len(jpeg) > self.limit or len(self.ring) >= 300):
                self.ring_bytes -= len(self.ring.popleft()[1])
            wanted = not self.error and (self.mode == 'manual' or self.mode == 'auto' and now < self.deadline)
            if wanted:
                if not self.active:
                    self.event = dict(id=uuid.uuid4().hex, trigger=self.mode, detection=self.last_detection)
                    for old, data in self.ring:
                        self._enqueue(old, data)
                self._enqueue(frame, jpeg)
            self.active = bool(wanted)
            if not wanted:
                self.event = None
            self.ring.append((frame, jpeg))
            self.ring_bytes += len(jpeg)
            self.wake.set()

    def _enqueue(self, frame, data):
        if self.pending_bytes + len(data) > self.limit or len(self.pending) >= 600:
            self.dropped += 1
            return
        self.pending.append((frame, data, self.event))
        self.pending_bytes += len(data)
        self.high_water = max(self.high_water, self.pending_bytes)

    def status(self):
        with self.lock:
            age = None if not self.last_detection else self.clock()-self.last_detection['at']
            h264=bool(self.latest and self.latest.get('codec')=='h264')
            return dict(mode=self.mode, state='error' if self.error else (('recording' if self.active else 'finishing') if self.current else
                        ('starting' if self.active else ('armed' if self.mode=='auto' else 'idle'))),
                        source='PS_VPU_H264' if h264 else SOURCE, width=self.latest['width'] if h264 else 960, height=self.latest['height'] if h264 else 540, format='H.264 / MP4' if h264 else 'MJPEG + timestamp JSONL',
                        source_ready=self.source_ready, current=self.current, error=self.error,
                        detection_error=self.detection_error, detection_age_s=age,
                        trigger_healthy=self.mode!='auto' or age is not None and age < 5,
                        last_detection=self.last_detection, queue_bytes=self.pending_bytes,
                        queue_limit_bytes=self.limit, queue_high_water=self.high_water,
                        prebuffer_bytes=self.ring_bytes, pre_seconds=self.pre, tail_seconds=self.tail,
                        segment_seconds=self.segment_seconds, dropped_frames=self.dropped,
                        source_frame_id_gaps=self.source_gaps,
                        received_frames=self.received, written_frames=self.written,
                        used_bytes=self.store.used, quota_bytes=self.store.quota,
                        disk_free_bytes=shutil.disk_usage(self.store.root).free,
                        disk_reserve_bytes=self.store.reserve)

    def fail(self, error):
        with self.lock:
            self.error = str(error)
            self.mode = 'off'
            self.active = False
            self.pending.clear()
            self.pending_bytes = 0
            self.wake.set()

    def _writer(self):
        part = None
        try:
            while True:
                with self.lock:
                    item = self.pending.popleft() if self.pending else None
                    if item:
                        self.pending_bytes -= len(item[1])
                    active = self.active
                if item:
                    frame, data, event = item
                    if part and (part.event['id'] != event['id'] or part.session != (frame['boot_id'],frame['session'])
                                 or frame['captured_at']-part.started >= part.seconds or part.bytes+len(data) > 256*MIB):
                        part.finish('segment_or_event_boundary')
                        part = None
                    if part is None:
                        part = Segment(self.store, frame, event, self.segment_seconds)
                        with self.lock:
                            self.current = part.name
                    part.write(frame, data)
                    with self.lock:
                        self.written += frame.get('samples',1) if frame.get('codec')=='h264' else 1
                else:
                    if part and (not active or self.quit.is_set()):
                        part.finish('shutdown' if self.quit.is_set() else 'event_finished')
                        part = None
                        with self.lock:
                            self.current = None
                    if self.quit.is_set():
                        break
                    self.wake.wait(.1)
                    self.wake.clear()
        except Exception as error:
            if part:
                part.abandon()
            self.fail(error)
            with self.lock:
                self.current = None

    def close(self):
        self.command('off')
        self.quit.set()
        self.wake.set()
        self.thread.join()


def run(args):
    from vpu_live_server import Frames
    import fcntl
    store = Storage(args.storage, args.mount, args.uuid, quota=args.quota_mib*MIB)
    instance = (store.root / '.recorder.lock').open('a')
    fcntl.flock(instance, fcntl.LOCK_EX | fcntl.LOCK_NB)
    from recording_library import Library
    library = Library(store, durable_json)
    media_slots = threading.BoundedSemaphore(2)
    recorder = Recorder(store, segment=args.segment_seconds)
    frames = Frames(args.control)
    h264_segments=None
    stop = threading.Event()
    from recording_compression import IdleCompression
    compression = IdleCompression(library, recorder, stop)
    opener = build_opener(ProxyHandler({}))
    backend = args.backend.rstrip('/')
    def detector():
        while not stop.is_set():
            if recorder.mode == 'auto' and recorder.source_ready and not recorder.error:
                try:
                    request = Request(backend+'/api/recognize-camera', data=b'', method='POST')
                    with opener.open(request, timeout=15) as r:
                        raw = r.read(12*MIB+1)
                    if len(raw) > 12*MIB:
                        raise ValueError('Detection response too large')
                    recorder.detection(json.loads(raw)['entry']['result'])
                except HTTPError as error:
                    with recorder.lock:
                        recorder.detection_error = 'Recognition busy' if error.code == 409 else 'Recognition HTTP '+str(error.code)
                except Exception as error:
                    with recorder.lock:
                        recorder.detection_error = str(error)
            stop.wait(.5)

    def capture():
        nonlocal h264_segments
        while not stop.is_set():
            try:
                state, jpeg = frames.read_if_changed()
                if state is not None and state.get('codec')=='h264' and state.get('ready'):
                    from h264_fragments import H264Segments
                    from h264_media import H264Unavailable
                    if h264_segments is None:h264_segments=H264Segments(frames)
                    try:
                        for meta,data in h264_segments.read_new():recorder.ingest(meta,data)
                    except FileNotFoundError:pass  # Encoder has not closed its first GOP yet.
                    except H264Unavailable:recorder.ingest(dict(state,ready=False),None)
                elif state is not None:
                    recorder.ingest(state, jpeg)
            except Exception as error:
                recorder.fail(error)
            stop.wait(.01)

    def maintenance():
        while not stop.is_set():
            try:
                library.maintain()
                library.cleanup_error = None
            except Exception as error:
                library.cleanup_error = str(error)
            stop.wait(60)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, code, data, kind='application/json; charset=utf-8', headers=None):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for key, value in (headers or {}).items():
                self.send_header(key, str(value))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            try:
                self.get()
            except FileNotFoundError as error:
                self.send(404, dict(error=str(error)))
            except (ValueError, KeyError, TypeError) as error:
                self.send(400, dict(error=str(error)))
            except (RuntimeError, OSError) as error:
                try:
                    self.send(503, dict(error=str(error)))
                except OSError:
                    pass

        def get(self):
            self.connection.settimeout(5)
            url = urlsplit(self.path)
            path = url.path
            query = {k:v[0] for k,v in parse_qs(url.query).items()}
            if path == '/':
                return self.send(200, Path(__file__).with_name('recording_panel.html').read_bytes(), 'text/html; charset=utf-8')
            if path == '/recording_panel.js':
                return self.send(200, Path(__file__).with_name('recording_panel.js').read_bytes(), 'text/javascript; charset=utf-8')
            if path == '/api/status':
                return self.send(200, recorder.status())
            if path == '/api/storage':
                return self.send(200, library.storage_usage())
            if path == '/api/compression':
                return self.send(200, compression.status())
            if path == '/api/retention':
                return self.send(200, dict(policy=library.policy, error=library.cleanup_error))
            if path == '/api/recordings':
                listing = library.listing(page=int(query.get('page',1)), limit=int(query.get('limit',20)),
                                          start=query.get('from',''), end=query.get('to',''), trash=query.get('trash')=='1')
                with recorder.lock:
                    current = recorder.current
                incomplete = [p for p in store.root.glob('rec-*.part')
                              if current is None or not p.name.startswith(current+'.')]
                return self.send(200, dict(listing, incomplete_files=len(incomplete)))
            match = re.fullmatch(r'/api/recordings/(rec-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12})/frame', path)
            if match:
                if not media_slots.acquire(blocking=False):
                    return self.send(429, dict(error='Playback/download connections full'))
                try:
                    jpeg, at = library.frame(match[1], float(query.get('at',0)))
                    return self.send(200, jpeg, 'image/jpeg', {'X-Frame-Time': at})
                finally:
                    media_slots.release()
            match = re.fullmatch(r'/api/recordings/(rec-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12})/(video|compressed)',path)
            if match:
                if not media_slots.acquire(blocking=False):return self.send(429,dict(error='Playback connections full'))
                try:
                    with library.opened(match[1],'.compressed.mp4' if match[2]=='compressed' else '.mp4') as (f,summary):
                        if match[2]=='video' and summary.get('format')!='h264_mp4':raise ValueError('Recording is not H264')
                        size=os.fstat(f.fileno()).st_size;start,end=0,size-1;requested=self.headers.get('Range')
                        if requested:
                            ranges=re.fullmatch(r'bytes=([0-9]+)-([0-9]*)',requested)
                            if not ranges:return self.send(416,b'',headers={'Content-Range':'bytes */'+str(size)})
                            start=int(ranges[1]);end=min(size-1,int(ranges[2])) if ranges[2] else size-1
                            if not 0<=start<=end<size:return self.send(416,b'',headers={'Content-Range':'bytes */'+str(size)})
                        self.send_response(206 if requested else 200);self.send_header('Content-Type','video/mp4');self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store')
                        self.send_header('Content-Length',str(end-start+1))
                        if requested:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                        self.end_headers();f.seek(start);remaining=end-start+1
                        while remaining:
                            chunk=f.read(min(65536,remaining))
                            if not chunk:raise OSError('Truncated recording')
                            self.wfile.write(chunk);remaining-=len(chunk)
                finally:media_slots.release()
                return
            match = re.fullmatch(r'/files/(rec-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12})\.(mjpeg|mp4|frames\.jsonl|json|compressed\.mp4)', path)
            if match:
                if not media_slots.acquire(blocking=False):
                    return self.send(429, dict(error='Playback/download connections full'))
                try:
                    with library.opened(match[1], '.'+match[2]) as (f, _):
                        self.send_response(200)
                        self.send_header('Content-Type','application/octet-stream')
                        self.send_header('Content-Disposition', 'attachment; filename="'+match[1]+'.'+match[2]+'"')
                        self.send_header('Content-Length',str(os.fstat(f.fileno()).st_size))
                        self.end_headers()
                        shutil.copyfileobj(f, self.wfile, 65536)
                finally:
                    media_slots.release()
                return
            return self.send(404, dict(error='Not found'))

        def do_POST(self):
            self.connection.settimeout(5)
            path = urlsplit(self.path).path
            if path not in ('/api/mode','/api/trash','/api/restore','/api/purge','/api/retention','/api/compression'):
                return self.send(404, dict(error='Not found'))
            if self.headers.get('Origin') not in (None, 'http://'+self.headers.get('Host','')):
                return self.send(403, dict(error='Cross-origin control rejected'))
            try:
                length = int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 1024:
                    raise ValueError('Invalid body size')
                data = json.loads(self.rfile.read(length))
                if path == '/api/mode':
                    recorder.command(data['mode'])
                    result = recorder.status()
                elif path == '/api/compression':
                    result = compression.set_policy(data['policy'])
                elif path == '/api/trash':
                    result = library.delete(data['id'])
                elif path == '/api/restore':
                    result = library.restore(data['id'])
                elif path == '/api/purge':
                    if data.get('confirm') != data['id']:
                        raise ValueError('Explicit recording confirmation required')
                    result = library.purge(data['id'])
                else:
                    if not isinstance(data['policy'], dict):
                        raise ValueError('Retention policy must be an object')
                    if data['policy'].get('enabled') and data.get('confirm') != 'delete_after_retention':
                        raise ValueError('Explicit retention deletion confirmation required')
                    result = library.set_policy(data['policy'])
                self.send(200, result)
            except (ValueError, KeyError, TypeError) as error:
                self.send(400, dict(error=str(error)))
            except FileNotFoundError as error:
                self.send(404, dict(error=str(error)))
            except (RuntimeError, OSError) as error:
                self.send(503, dict(error=str(error)))

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    def shutdown(*_):
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    recorder.start()
    workers = [threading.Thread(target=capture), threading.Thread(target=detector), threading.Thread(target=maintenance),
               threading.Thread(target=compression.run, name='idle-compression')]
    for worker in workers:
        worker.start()
    recorder.command(args.mode)
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        for worker in workers:
            worker.join()
        recorder.close()
        durable_json(store.root/'service-stop.json', recorder.status())
        instance.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--storage', type=Path, required=True)
    parser.add_argument('--mount', type=Path, required=True)
    parser.add_argument('--uuid', required=True)
    parser.add_argument('--backend', default='http://192.168.1.113:8091')
    parser.add_argument('--host', default='192.168.1.113')
    parser.add_argument('--port', type=int, default=8093)
    parser.add_argument('--mode', choices=['off','auto','manual'], default='auto')
    parser.add_argument('--segment-seconds', type=float, default=60.)
    parser.add_argument('--quota-mib', type=int, default=4096)
    args = parser.parse_args()
    if not 1 <= args.segment_seconds <= 300 or not 64 <= args.quota_mib <= 16384:
        parser.error('Segment/quota outside bounded limits')
    run(args)
