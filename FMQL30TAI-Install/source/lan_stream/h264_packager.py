"""Package hardware-encoded GOPs with the installed FFmpeg; never encode pixels."""
from fractions import Fraction
import json
from pathlib import Path
import struct
import subprocess
import threading
import time
from h264_fragments import boxes,timing
from h264_media import directory

def atomic(path,data):
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_bytes(data);temp.replace(path)

def split_mp4(data,sequence,start):
    init=bytearray();fragment=bytearray()
    for kind,a,b in boxes(data):
        block=data[a-8:b]
        if kind in (b'ftyp',b'moov'):init.extend(block)
        elif kind in (b'moof',b'mdat'):fragment.extend(block)
    if not init or not fragment:raise ValueError('FFmpeg did not produce fragmented MP4')
    # Each short FFmpeg invocation starts a fragment sequence; place it on the
    # owner's monotonic capture timeline at the declared 90 kHz timescale.
    for kind,a,b in boxes(fragment):
        if kind!=b'moof':continue
        for child,x,y in boxes(fragment,a,b):
            if child==b'mfhd':struct.pack_into('>I',fragment,x+4,sequence+1)
            elif child==b'traf':
                for field,p,q in boxes(fragment,x,y):
                    if field==b'tfdt':
                        value=round(start*90000);size=8 if fragment[p]==1 else 4
                        if value<0 or value>=1<<(size*8):raise ValueError('Fragment timestamp exceeds bounds')
                        fragment[p+4:p+4+size]=value.to_bytes(size,'big')
    offset,count=timing(init,fragment)
    if abs(offset-start)>1/90000:raise ValueError('MP4 timescale mismatch')
    return bytes(init),bytes(fragment),count

class H264Packager:
    def __init__(self,frames):
        self.frames=frames;self.stop=threading.Event();self.thread=threading.Thread(target=self.run,name='h264-packager',daemon=True);self.error=None
    def start(self):self.thread.start()
    def close(self):self.stop.set();self.thread.join(timeout=8)
    def run(self):
        session=None;last=-1;window=[]
        while not self.stop.is_set():
            try:
                root,state=directory(self.frames);raw=root.parent/'h264';root.mkdir(exist_ok=True)
                if state['session']!=session:session=state['session'];last=-1;window=[]
                files=sorted(raw.glob('raw-?????????.json'))
                if last<0:files=files[-2:]
                for meta in files:
                    value=json.loads(meta.read_text());number=value['sequence']
                    if number<=last:continue
                    if last>=0 and number!=last+1:raise RuntimeError('Packager missed a hardware GOP')
                    duration=value['end']-value['start'];count=value['frames']
                    if not 0<duration<10 or not 0<count<=300:raise ValueError('Invalid hardware GOP timing')
                    source=meta.with_suffix('.h264')
                    if source.is_symlink() or not 0<source.stat().st_size<=8*1024**2:raise ValueError('Hardware GOP exceeds bounds')
                    output=root/'pack.pending.mp4';rate=Fraction(count/duration).limit_denominator(10000)
                    command=['ffmpeg','-v','error','-probesize','65536','-analyzeduration','0','-f','h264','-framerate',str(rate),'-i',str(source),'-map','0:v:0','-c:v','copy','-video_track_timescale','90000','-use_editlist','0','-movflags','frag_keyframe+empty_moov+default_base_moof','-f','mp4','-y',str(output)]
                    process=subprocess.run(command,capture_output=True,timeout=5)
                    if process.returncode:raise RuntimeError('H264 packaging failed: '+process.stderr.decode(errors='replace')[-400:])
                    init,fragment,actual=split_mp4(output.read_bytes(),number,value['start']-value['origin'])
                    if actual!=count:raise ValueError('Packaged sample count differs from hardware output')
                    _,current=directory(self.frames,session)
                    if current['pid']!=state['pid']:raise RuntimeError('Camera changed while packaging')
                    if not window:atomic(root/'init.mp4',init)
                    name=f'seg-{number:09d}.m4s';atomic(root/name,fragment);output.unlink()
                    window.append((number,duration,name));window=window[-12:]
                    lines=['#EXTM3U','#EXT-X-VERSION:7','#EXT-X-INDEPENDENT-SEGMENTS','#EXT-X-TARGETDURATION:10',f'#EXT-X-MEDIA-SEQUENCE:{window[0][0]}','#EXT-X-MAP:URI="init.mp4"']
                    for _,seconds,file in window:lines.extend([f'#EXTINF:{seconds:.6f},',file])
                    atomic(root/'index.m3u8',('\n'.join(lines)+'\n').encode())
                    for old in root.glob('seg-?????????.m4s'):
                        if int(old.stem[4:])<number-15:old.unlink()
                    last=number;self.error=None
                    atomic(root/'packager.json',json.dumps(dict(session=session,pid=state['pid'],updated_at=time.monotonic(),sequence=last,error=None)).encode())
            except FileNotFoundError:pass
            except Exception as error:
                self.error=str(error)
                try:
                    if 'root' in locals():atomic(root/'packager.json',json.dumps(dict(session=session,updated_at=time.monotonic(),error=self.error)).encode())
                except OSError:pass
            self.stop.wait(.05)
