"""Bounded WJP1 JPEG reassembly; the host publishes complete frames only.

CRC detects corruption, not an authenticated sender. The caller pins sender
address and nonzero deployment session. A new packet never queues old frames.
"""
from dataclasses import dataclass
import struct
import time
import zlib

HEADER = struct.Struct('!4sBBHIIIIHHHHI4s')
CHUNK = 1400
START, END, ABORT = 1, 2, 4


def newer(value, previous):
    return 0 < ((value - previous) & 0xffffffff) < 0x80000000


def jpeg_size(data):
    """Read baseline JPEG geometry without decoding untrusted pixel data."""
    if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise ValueError('Incomplete JPEG')
    p = 2
    size = None
    while p + 4 <= len(data):
        if data[p] != 255:
            raise ValueError('Malformed JPEG marker')
        while p < len(data) and data[p] == 255:
            p += 1
        if p >= len(data):
            break
        marker = data[p]
        p += 1
        if marker in (0, 0xd8, 0xd9) or 0xd0 <= marker <= 0xd7:
            raise ValueError('Unexpected JPEG header marker')
        if p + 2 > len(data):
            raise ValueError('Truncated JPEG header')
        length = int.from_bytes(data[p:p+2], 'big')
        if length < 2 or p + length > len(data):
            raise ValueError('JPEG marker outside frame')
        if marker == 0xc0:
            if size is not None or length != 17 or data[p+2] != 8 or data[p+7] != 3:
                raise ValueError('Expected one 8-bit, three-component baseline SOF')
            size = (int.from_bytes(data[p+5:p+7], 'big'), int.from_bytes(data[p+3:p+5], 'big'))
        elif 0xc1 <= marker <= 0xcf and marker not in (0xc4, 0xc8, 0xcc):
            raise ValueError('Unsupported JPEG coding mode')
        if marker == 0xda:
            if size is None or length != 12:
                raise ValueError('Unexpected JPEG scan header')
            return size
        p += length
    raise ValueError('Missing JPEG scan')


@dataclass(frozen=True)
class Frame:
    session: int
    frame_id: int
    jpeg: bytes
    first_packet_at: float
    completed_at: float


class Reassembler:
    def __init__(self, session, *, width=1920, height=1080,
                 max_bytes=8*1024*1024, timeout=.25, clock=time.monotonic):
        if isinstance(session, bool) or not isinstance(session, int) or not 0 < session < 2**32:
            raise ValueError('Pin a nonzero uint32 deployment session')
        if not 1 <= width <= 8192 or not 1 <= height <= 8192 or not 0 < timeout <= 5:
            raise ValueError('Invalid geometry/deadline')
        self.session, self.width, self.height = session, width, height
        self.max_bytes, self.timeout, self.clock = max_bytes, timeout, clock
        self.current = self.watermark = None
        self.parts = {}
        self.total = None
        self.start_seen = False
        self.first_at = 0.
        self.stats = dict(packets=0, rejected=0, duplicate=0, expired=0, superseded=0,
                          aborted=0, completed=0, invalid_jpeg=0)

    def _clear(self):
        self.current = None
        self.parts = {}
        self.total = None
        self.start_seen = False

    def expire(self, now=None):
        now = self.clock() if now is None else now
        if self.current is not None and now-self.first_at >= self.timeout:
            self.stats['expired'] += 1
            self._clear()

    def feed(self, packet):
        now = self.clock()
        self.expire(now)
        self.stats['packets'] += 1
        joined = False
        try:
            if len(packet) < HEADER.size or len(packet) > HEADER.size+CHUNK:
                raise ValueError('Datagram size')
            magic,version,flags,hlen,session,fid,offset,total,length,w,h,reserved,crc,fmt = HEADER.unpack_from(packet)
            body = packet[HEADER.size:]
            if (magic,version,hlen,session,w,h,reserved,fmt) != (
                    b'WJP1',1,HEADER.size,self.session,self.width,self.height,0,b'JPEG'):
                raise ValueError('Header contract')
            if flags not in (0, START, END, START|END, ABORT) or length != len(body):
                raise ValueError('Flags/length')
            if flags == ABORT:
                if body or total or crc:
                    raise ValueError('Malformed abort')
            elif (not body or offset % CHUNK or offset+length > self.max_bytes or
                  bool(flags & START) != (offset == 0) or
                  (flags & END and total != offset+length) or
                  (not flags & END and (total != 0 or length != CHUNK)) or
                  zlib.crc32(body) != crc):
                raise ValueError('Fragment bounds/CRC')
            if self.current != fid:
                if self.watermark is not None and not newer(fid,self.watermark):
                    raise ValueError('Retired frame')
                if self.current is not None:
                    self.stats['superseded'] += 1
                self._clear()
                self.current = self.watermark = fid
                self.first_at = now
            joined = True
            if flags == ABORT:
                self.stats['aborted'] += 1
                self._clear()
                return None
            if self.total is not None and offset+length > self.total:
                raise ValueError('Fragment exceeds declared frame')
            if flags & END:
                if self.total is not None and self.total != total:
                    raise ValueError('Conflicting EOF')
                if any(k+len(v)>total for k,v in self.parts.items()):
                    raise ValueError('EOF truncates existing fragments')
                self.total = total
            if offset in self.parts:
                if self.parts[offset] != body:
                    raise ValueError('Conflicting duplicate')
                self.stats['duplicate'] += 1
            else:
                self.parts[offset] = bytes(body)
            if flags & START:
                self.start_seen = True
            if self.total is None or not self.start_seen:
                return None
            count = (self.total+CHUNK-1)//CHUNK
            if len(self.parts) != count or any(k*CHUNK not in self.parts for k in range(count)):
                return None
            data = b''.join(self.parts[k*CHUNK] for k in range(count))
            if len(data) != self.total or jpeg_size(data) != (self.width,self.height):
                self.stats['invalid_jpeg'] += 1
                raise ValueError('JPEG geometry/integrity')
            result = Frame(self.session,fid,data,self.first_at,now)
            self.stats['completed'] += 1
            self._clear()
            return result
        except (ValueError,struct.error):
            self.stats['rejected'] += 1
            # An invalid packet must not create, retire or poison an unrelated
            # frame. Conflicting valid fragments retire the active frame.
            if joined:
                self._clear()
            return None
