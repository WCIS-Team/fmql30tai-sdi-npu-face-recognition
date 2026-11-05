"""Replay saved board H264, stream-copy only; isolate packaging wait, no camera/NPU."""
import sys,time,threading,subprocess,struct,json,re,statistics,math,hashlib
from pathlib import Path
import argparse,shutil
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ffmpeg',required=True)
parser.add_argument('--snapshot',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
T=args.out.resolve();T.mkdir(parents=True,exist_ok=False)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lan_stream'))
from h264_fragments import timing
F=args.ffmpeg
S=args.snapshot.resolve()
joined=T/'saved-board.mp4';joined.write_bytes((S/'init.mp4').read_bytes()+b''.join(p.read_bytes() for p in sorted(S.glob('seg-*.m4s'))))
raw=T/'saved-board-aud.h264'
def run(args):
 r=subprocess.run([F,'-v','error']+args,capture_output=True,timeout=40);assert r.returncode==0,r.stderr.decode(errors='replace');return r
run(['-i',str(joined),'-map','0:v:0','-c:v','copy','-bsf:v','h264_mp4toannexb,h264_metadata=aud=insert','-f','h264','-y',str(raw)])
data=raw.read_bytes();positions=[]
for m in re.finditer(b'\x00\x00\x00\x01|\x00\x00\x01',data):
 if data[m.end()]&31==9:positions.append(m.start())
assert len(positions)>180
packets=[data[a:b] for a,b in zip(positions,positions[1:]+[len(data)])][:180]
reports=[]
for mode in ('hls','frame-fragments','combined'):
 root=T/(mode+'-rerun');root.mkdir(exist_ok=False);start=time.perf_counter();sent=[];observed=[];parts=[];buffer=bytearray();init=bytearray();current=bytearray()
 base=[F,'-v','warning','-nostdin','-fflags','+genpts','-f','h264','-framerate','30','-probesize','32','-analyzeduration','0','-i','pipe:0','-map','0:v:0','-c:v','copy']
 tail=['-f','hls','-hls_time','1','-hls_list_size','12','-hls_segment_type','fmp4','-hls_flags','independent_segments+temp_file','-hls_fmp4_init_filename','init.mp4','-hls_segment_filename',str(root/'seg-%09d.m4s'),str(root/'index.m3u8')] if mode=='hls' else ['-f','mp4','-movflags','empty_moov+default_base_moof+frag_every_frame','-flush_packets','1','pipe:1']
 if mode=='combined':
  tail=['-f','hls','-hls_time','1','-hls_list_size','12','-hls_segment_type','fmp4','-hls_flags','independent_segments+temp_file','-hls_fmp4_init_filename','init.mp4','-hls_segment_filename',str(root/'seg-%09d.m4s'),str(root/'index.m3u8'),'-map','0:v:0','-c:v','copy']+tail
 err=(root/'ffmpeg.log').open('wb');p=subprocess.Popen(base+tail,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,bufsize=0,cwd=root)
 done=threading.Event()
 def reader():
  while True:
   b=p.stdout.read(65536)
   if not b:break
   parts.append(b);buffer.extend(b)
   while len(buffer)>=8:
    size=int.from_bytes(buffer[:4],'big');kind=bytes(buffer[4:8]);assert size>=8
    if len(buffer)<size:break
    box=bytes(buffer[:size]);del buffer[:size]
    if kind in (b'ftyp',b'moov'):init.extend(box)
    if kind==b'moof':current.clear();current.extend(box)
    elif kind==b'mdat':
     current.extend(box);observed.append(dict(at=time.perf_counter()-start,samples=timing(bytes(init),bytes(current))[1]))
 def watch():
  seen=set()
  while not done.is_set():
   for f in sorted(root.glob('seg-*.m4s')):
    if f.name not in seen:
     count=timing((root/'init.mp4').read_bytes(),f.read_bytes())[1];observed.append(dict(at=time.perf_counter()-start,samples=count));seen.add(f.name)
   time.sleep(.005)
 thread=threading.Thread(target=watch if mode=='hls' else reader);thread.start()
 try:
  for i,packet in enumerate(packets):
   deadline=start+.2+i/30
   time.sleep(max(0,deadline-time.perf_counter()));sent.append(time.perf_counter()-start);p.stdin.write(packet)
  p.stdin.close();assert p.wait(timeout=15)==0
  time.sleep(.1)
 finally:
  done.set();thread.join(timeout=5);err.close()
 if mode!='hls':(root/'output.mp4').write_bytes(b''.join(parts));run(['-i',str(root/'output.mp4'),'-f','null','-'])
 else:
  run(['-i',str(root/'index.m3u8'),'-f','null','-'])
 if mode=='combined':
  decoded=run(['-i',str(root/'index.m3u8'),'-f','framemd5','-']).stdout.decode()
  assert len([line for line in decoded.splitlines() if line and not line.startswith('#')])==len(packets)
 latencies=[];index=0
 for item in observed:
  for j in range(item['samples']):
   if 30<=index<len(sent)-30:latencies.append(1000*(item['at']-sent[index]))
   index+=1
 assert index==len(packets),(mode,index,len(packets))
 report=dict(mode=mode,frames=index,fragments=len(observed),samples_per_fragment=sorted(set(q['samples'] for q in observed)),warm_packaging_ms_p50=statistics.median(latencies),warm_packaging_ms_p95=sorted(latencies)[math.ceil(.95*len(latencies))-1],raw_observed=observed,raw_submitted=sent,command=base+tail)
 reports.append(report);print(json.dumps({k:v for k,v in report.items() if not k.startswith('raw') and k!='command'}),flush=True)
 (T/'results.json').write_text(json.dumps(dict(tool_version=subprocess.check_output([F,'-version'],text=True).splitlines()[0],source_sha256=hashlib.sha256(data).hexdigest(),stream_copy_only=True,hardware_opened=False,results=reports),indent=2))
