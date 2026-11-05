"""Read complete VPU H264 fragments belonging to one admitted owner session."""
import json
from pathlib import Path
import re
import time

FILE=re.compile(r'(?:init\.mp4|seg-[0-9]{9}\.m4s)')
class H264Unavailable(RuntimeError):pass

def directory(frames, session=None):
    state,_=frames.read()
    if not state.get('ready') or state.get('codec')!='h264':raise H264Unavailable('No fresh H264 stream')
    if session is not None and session!=state['session']:raise ValueError('Camera session changed')
    cfg=json.loads(frames.control.read_text())
    if cfg['session']!=state['session'] or cfg['pid']!=state['pid']:raise ValueError('Owner changed')
    root=Path(cfg['directory'])
    if root.parent!=frames.frame_root or not root.name.startswith('wcis-') or root.is_symlink():raise ValueError('Unexpected owner directory')
    return root/'hls',state

def manifest(frames,session=None):
    root,state=directory(frames,session)
    health=json.loads((root/'packager.json').read_text())
    if (health.get('session')!=state['session'] or health.get('pid')!=state['pid']
            or health.get('error') or not 0<=time.monotonic()-health['updated_at']<=4):raise H264Unavailable('H264 packager is not current')
    text=(root/'index.m3u8').read_text()
    if len(text)>32768:raise ValueError('HLS manifest exceeds bounds')
    segments=[];duration=None
    for line in text.splitlines():
        if line.startswith('#EXTINF:'):duration=float(line[8:].split(',')[0])
        elif line and not line.startswith('#'):
            if not FILE.fullmatch(line) or not line.endswith('.m4s') or duration is None or not 0<duration<10:raise ValueError('Unexpected HLS fragment')
            segments.append(dict(name=line,duration=duration))
            duration=None
    if not segments or len(segments)>16:raise ValueError('No complete H264 fragments')
    if state.get('external_h264'):
        admitted=[]
        for item in segments:
            metadata=(root/item['name']).with_suffix('.capture.json')
            try:
                if metadata.is_symlink():raise ValueError('Unexpected capture metadata symlink')
                capture=json.loads(metadata.read_text())
            except FileNotFoundError:continue
            if any(capture.get(key)!=state[key] for key in ('boot_id','pid','session')):
                raise ValueError('H264 capture metadata belongs to another session')
            if capture.get('first_frame',0)>0 and capture.get('samples',0)>0:admitted.append(item)
        segments=admitted
        if not segments:raise H264Unavailable('Waiting for a camera-backed video fragment')
    init=(root/'init.mp4').read_bytes()
    offset=init.find(b'avcC')
    if offset<0 or init[offset+4:offset+5]!=b'\x01':raise ValueError('Missing AVC configuration')
    return dict(session=state['session'],codec='avc1.'+init[offset+5:offset+8].hex(),width=state['width'],height=state['height'],init='init.mp4',segments=segments)

def media(frames,name,session=None):
    if name=='manifest.json':return 'application/json',json.dumps(manifest(frames,session)).encode()
    if not FILE.fullmatch(name):raise ValueError('Unexpected media file')
    root,_=directory(frames,session);path=root/name
    if path.is_symlink():raise ValueError('Unexpected media symlink')
    if path.stat().st_size>8*1024**2:raise ValueError('H264 fragment exceeds bounds')
    return ('video/mp4' if name.endswith('.mp4') else 'video/iso.segment'),path.read_bytes()
