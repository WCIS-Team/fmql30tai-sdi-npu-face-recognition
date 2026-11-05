"""Read timed fMP4 fragments emitted by libavformat, without decoding video."""
import struct
import time
from h264_media import directory,manifest

def boxes(data,start=0,end=None):
    end=len(data) if end is None else end
    while start<end:
        if start+8>end:raise ValueError('Truncated MP4 box')
        size,kind=struct.unpack_from('>I4s',data,start);header=8
        if size==1:
            if start+16>end:raise ValueError('Truncated extended MP4 box')
            size=struct.unpack_from('>Q',data,start+8)[0];header=16
        if size<header or start+size>end:raise ValueError('Invalid MP4 box bounds')
        yield kind,start+header,start+size
        start+=size

def timing(init,fragment):
    timescale=None
    def descend(data,start=0,end=None):
        for kind,a,b in boxes(data,start,end):
            yield kind,a,b
            if kind in (b'moov',b'trak',b'mdia',b'moof',b'traf'):yield from descend(data,a,b)
    for kind,a,b in descend(init):
        if kind==b'mdhd':
            offset=20 if init[a]==1 else 12
            if a+offset+4>b:raise ValueError('Truncated media header')
            timescale=struct.unpack_from('>I',init,a+offset)[0]
    timestamp=None;samples=0
    for kind,a,b in descend(fragment):
        if kind==b'tfdt':
            size=8 if fragment[a]==1 else 4
            if a+4+size>b:raise ValueError('Truncated decode timestamp')
            timestamp=int.from_bytes(fragment[a+4:a+4+size],'big')
        elif kind==b'trun':
            if a+8>b:raise ValueError('Truncated sample count')
            samples+=struct.unpack_from('>I',fragment,a+4)[0]
    if not timescale or timestamp is None or not 0<samples<=300:raise ValueError('Missing fragment timing')
    return timestamp/timescale,samples

class H264Segments:
    def __init__(self,frames):self.frames=frames;self.session=None;self.last=-1
    def read_new(self):
        info=manifest(self.frames);root,state=directory(self.frames,info['session'])
        init=(root/info['init']).read_bytes()
        if self.session!=info['session']:self.session=info['session'];self.last=-1;entries=info['segments'][-2:]
        else:entries=info['segments']
        result=[]
        for item in entries:
            number=int(item['name'][4:-4])
            if number<=self.last:continue
            path=root/item['name']
            if path.is_symlink() or path.stat().st_size>8*1024**2:raise ValueError('Unexpected H264 fragment')
            data=path.read_bytes();offset,samples=timing(init,data)
            capture=None
            if state.get('external_h264'):
                try:capture=__import__('json').loads(path.with_suffix('.capture.json').read_text())
                except FileNotFoundError:break
                if (any(capture.get(key)!=state[key] for key in ('boot_id','pid','session'))
                        or capture['samples']!=samples or capture['first_frame']<=0
                        or capture['last_frame']<capture['first_frame'] or capture['end']<=capture['start']):
                    raise ValueError('H264 capture metadata belongs to another frame/session')
            if self.last>=0 and number!=self.last+1:raise RuntimeError('H264 recorder missed a fragment')
            frame=dict(state,frame_id=number,frame_id_basis='hls_segment_sequence',captured_at=state['h264_origin']+offset,
                       captured_end=state['h264_origin']+offset+item['duration'],samples=samples,duration=item['duration'],_h264_init=init)
            if capture is not None:
                frame.update(captured_at=capture['start'],captured_end=capture['end'],
                             source_first_frame=capture['first_frame'],source_last_frame=capture['last_frame'],
                             capture_time_basis='native_raw_input_journal')
            if not 0<=time.monotonic()-frame['captured_end']<=4:raise ValueError('H264 fragment is stale')
            result.append((frame,data));self.last=number
        return result
