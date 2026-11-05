"""Bounded live fMP4 cache. No encoder, SDK, file queue or recorder ownership."""
from collections import deque
import threading
import time
from h264_fragments import boxes, timing


class LiveFragments:
    def __init__(self, capture, limit=16*1024*1024):
        self.capture = capture
        self.limit = limit
        self.condition = threading.Condition()
        self.init = b''
        self.pending = bytearray()
        self.fragment = b''
        self.rows = deque()
        self.bytes = 0
        self.index = 0
        self.error = None
        self.closed = False

    def fail(self, error):
        with self.condition:
            self.error = str(error)
            self.rows.clear(); self.bytes = 0
            self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()

    def feed(self, data):
        self.pending.extend(data)
        if len(self.pending) > 8*1024*1024:
            raise ValueError('Live MP4 pending bytes exceed limit')
        while len(self.pending) >= 8:
            size = int.from_bytes(self.pending[:4], 'big')
            if not 8 <= size <= 8*1024*1024:
                raise ValueError('Unexpected live MP4 box size')
            if len(self.pending) < size:
                break
            box = bytes(self.pending[:size]); del self.pending[:size]
            kind = box[4:8]
            if kind in (b'ftyp', b'moov'):
                if self.rows or len(self.init)+len(box) > 256*1024:
                    raise ValueError('Unexpected live initialization')
                self.init += box
            elif kind == b'moof':
                if self.fragment:
                    raise ValueError('Incomplete live fragment')
                self.fragment = box
            elif kind == b'mdat':
                if not self.fragment:
                    raise ValueError('Live media lacks moof')
                fragment = self.fragment+box; self.fragment = b''
                offset, samples = timing(self.init, fragment)
                if samples != 1:
                    raise ValueError('Live output must contain one sample per fragment')
                index = self.index; self.index += 1
                capture = self.capture(index)
                if capture is None:  # verified synthetic priming frames only
                    continue
                # AVCC length-prefixed NALs, derived from this stream's avcC.
                avcc = self.init.find(b'avcC')
                if avcc < 0 or avcc+9 > len(self.init):
                    raise ValueError('Missing live AVC configuration')
                length_size = (self.init[avcc+8] & 3)+1
                payload = box[8:]; position = 0; key = False
                while position < len(payload):
                    if position+length_size >= len(payload):
                        raise ValueError('Truncated live NAL length')
                    size = int.from_bytes(payload[position:position+length_size], 'big'); position += length_size
                    if size <= 0 or position+size > len(payload):
                        raise ValueError('Invalid live NAL bounds')
                    key |= payload[position] & 31 == 5
                    position += size
                row = dict(sequence=index, pts=offset, end=offset+1/30, capture=capture,
                           key=key, data=fragment, published_at=time.monotonic())
                with self.condition:
                    if key:
                        # Retain the previous GOP and current GOP, bounded by bytes/frames.
                        keys = [i for i, q in enumerate(self.rows) if q['key']]
                        if len(keys) >= 2:
                            for _ in range(keys[-1]):
                                self.bytes -= len(self.rows.popleft()['data'])
                    if self.bytes+len(fragment) > self.limit or len(self.rows) >= 120:
                        raise ValueError('Live GOP cache exceeds bounds')
                    self.rows.append(row); self.bytes += len(fragment)
                    self.condition.notify_all()

    def read(self, after=None):
        with self.condition:
            if self.error or self.closed:
                raise RuntimeError(self.error or 'Live stream closed')
            if not self.rows or not 0 <= time.monotonic()-self.rows[-1]['capture']['end'] <= 2:
                raise RuntimeError('No fresh live H264 frame')
            rows = list(self.rows)
            if after is None:
                keys = [i for i, q in enumerate(rows) if q['key']]
                if not keys:
                    raise RuntimeError('Waiting for a camera keyframe')
                rows = rows[keys[-1]:]
            else:
                rows = [q for q in rows if q['sequence'] > after]
                if rows and rows[0]['sequence'] != after+1:
                    raise RuntimeError('Slow live consumer missed frames')
            return self.init, rows

    def wait(self, timeout=.2):
        with self.condition:
            self.condition.wait(timeout)
