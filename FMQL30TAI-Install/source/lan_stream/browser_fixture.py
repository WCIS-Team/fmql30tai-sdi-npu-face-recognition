"""Finite browser-test fixture. Synthetic pixels/results; never a model output."""
import argparse
import http.client
import json
import time
import uuid
from raw_protocol import pack

parser=argparse.ArgumentParser()
parser.add_argument('--port',type=int,required=True)
parser.add_argument('--seconds',type=float,default=20)
parser.add_argument('--overlays',action='store_true')
args=parser.parse_args()
sid='browser-test-'+uuid.uuid4().hex
width,height=1920,1080
row=b''.join(v.to_bytes(2,'little')*(width//6) for v in (0xf800,0x07e0,0x001f,0xffff,0xffe0,0x07ff))
pixels=row*height
end=time.monotonic()+args.seconds
sequence=0
connection=http.client.HTTPConnection('127.0.0.1',args.port,timeout=5)
def post(path,payload):
    connection.request('POST',path,payload);response=connection.getresponse();response.read()
    if response.status!=204:raise RuntimeError('HTTP '+str(response.status))
while time.monotonic()<end:
    sequence+=1;t=str(time.monotonic_ns()//1000)
    meta=dict(schema_version=1,stream_id=sid,frame_id=str(sequence),timestamp_us=t,
        timestamp_basis='ps_dma_done_monotonic',source='demo',pixel_format='RGB565LE',
        width=width,height=height,stride_bytes=width*2)
    if args.overlays:
        result=dict(schema_version=1,stream_id=sid,frame_id=str(sequence),models={'face':'ready','voice':'ready'},
            faces=[dict(box=[.32,.2,.3,.45],name='接口测试（非模型）',confidence=.9)],
            subtitles=[dict(start_us=t,end_us=t,text='字幕接口测试（非语音模型输出）')])
        meta.update(result)
    post('/api/frame',pack(meta,pixels))
    time.sleep(.5)
print('Finished synthetic 1080p browser fixture; no camera or model used.')
connection.close()
