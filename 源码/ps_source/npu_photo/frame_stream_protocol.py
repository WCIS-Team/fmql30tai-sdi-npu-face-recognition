"""Bounded raw-frame transport over an SSH exec channel, without a PTY.

Only pixels and their identity cross this interface; no physical addresses or
commands from the data stream are executed. JSON replies use the return pipe.
"""
import hashlib
import json
import re
import struct
import time

MAGIC=b'WCISVID1'
PREFIX=struct.Struct('!8sII')
MAX_HEADER=4096
MAX_PAYLOAD=32*1024*1024
MAX_ALLOCATION=64*1024*1024
FORMATS=('BGRX8','RGB565LE')


def validate_header(value,payload_bytes):
    if not isinstance(value,dict) or value.get('version')!=1:
        raise ValueError('Unsupported stream header')
    token=value.get('stream_id')
    if not isinstance(token,str) or re.fullmatch('[0-9a-f]{32}',token) is None:
        raise ValueError('Invalid stream identity')
    if value.get('kind')=='finish':
        if payload_bytes:raise ValueError('Finish packet contains pixels')
        return value
    if value.get('kind')!='frame' or value.get('pixel_format') not in FORMATS:
        raise ValueError('Unsupported frame kind/format')
    keys=('sequence','pts_us','width','height','pitch_bytes')
    if any(type(value.get(k)) is not int for k in keys):
        raise ValueError('Frame geometry and timestamps must use integers')
    seq,pts,w,h,pitch=(value[k] for k in keys)
    bpp=2 if value['pixel_format']=='RGB565LE' else 4
    if not 1<=seq<=0xffffffff or pts<0:
        raise ValueError('Invalid frame sequence/timestamp')
    if not (1<=w<=8192 and 1<=h<=8192) or pitch%8 or not w*bpp<=pitch<=65536:
        raise ValueError('Frame outside geometry contract')
    if payload_bytes!=pitch*h or not 0<payload_bytes<=MAX_PAYLOAD:
        raise ValueError('Frame byte count mismatch or limit exceeded')
    if 128+((payload_bytes+63)//64)*64+640*640*4>MAX_ALLOCATION:
        raise ValueError('Frame outside bounded SDK allocation')
    digest=value.get('sha256')
    if not isinstance(digest,str) or re.fullmatch('[0-9a-f]{64}',digest) is None:
        raise ValueError('Invalid frame digest')
    return value


def encode_header(metadata,payload_bytes):
    validate_header(metadata,payload_bytes)
    data=json.dumps(metadata,separators=(',',':'),ensure_ascii=True).encode('ascii')
    if len(data)>MAX_HEADER:raise ValueError('Frame metadata too large')
    return PREFIX.pack(MAGIC,len(data),payload_bytes)+data


def read_exact(stream,size,allow_eof=False):
    data=bytearray()
    while len(data)<size:
        part=stream.read(size-len(data))
        if not part:
            if allow_eof and not data:return None
            raise EOFError('Truncated video packet')
        data.extend(part)
    return bytes(data)


def read_packet(stream):
    # Exclude waiting for the next packet from payload assembly timing.
    first=read_exact(stream,1,allow_eof=True)
    if first is None:return None
    start=time.monotonic()
    magic,header_bytes,payload_bytes=PREFIX.unpack(first+read_exact(stream,PREFIX.size-1))
    if magic!=MAGIC or not 1<=header_bytes<=MAX_HEADER or payload_bytes>MAX_PAYLOAD:
        raise ValueError('Bad video packet prefix or size')
    header=json.loads(read_exact(stream,header_bytes).decode('utf-8'))
    validate_header(header,payload_bytes)
    payload=read_exact(stream,payload_bytes)
    if header['kind']=='frame' and hashlib.sha256(payload).hexdigest()!=header['sha256']:
        raise ValueError('Video frame checksum mismatch')
    return header,payload,(time.monotonic()-start)*1000
