import json
from pathlib import Path
import struct
import tempfile
import time
import unittest
from h264_fragments import timing,boxes
from h264_media import media,manifest

def box(kind,data):return struct.pack('>I4s',len(data)+8,kind)+data

class TimingTests(unittest.TestCase):
    def test_timescale_and_long_timestamp(self):
        mdhd=b'\0'*12+struct.pack('>I',90000)+b'\0'*8
        init=box(b'moov',box(b'trak',box(b'mdia',box(b'mdhd',mdhd))))
        fragment=box(b'moof',box(b'traf',box(b'tfdt',b'\x01\0\0\0'+struct.pack('>Q',90000*12345))+box(b'trun',b'\0'*4+struct.pack('>I',30))))
        self.assertEqual(timing(init,fragment),(12345.,30))
    def test_truncated_and_out_of_bounds_boxes(self):
        for value in (b'123',struct.pack('>I4s',100,b'moof'),struct.pack('>I4s',4,b'moof')):
            with self.subTest(value=value),self.assertRaises(ValueError):list(boxes(value))
    def test_missing_timing_rejected(self):
        with self.assertRaises(ValueError):timing(box(b'moov',b''),box(b'moof',b''))

class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);base=Path(self.tmp.name);root=base/'wcis-owner-example';(root/'hls').mkdir(parents=True)
        self.frames=type('Frames',(),{})();self.frames.frame_root=base;self.frames.control=base/'control.json'
        self.frames.control.write_text(json.dumps(dict(session='example',pid=123,directory=str(root))))
        self.state=dict(ready=True,codec='h264',session='example',pid=123,width=1920,height=1080)
        self.frames.read=lambda:(self.state,None);self.root=root/'hls'
        (self.root/'init.mp4').write_bytes(box(b'avcC',b'\x01\x4d\x40\x29\xff'))
        (self.root/'packager.json').write_text(json.dumps(dict(session='example',pid=123,updated_at=time.monotonic(),error=None)))
    def test_avc_codec_and_complete_manifest(self):
        (self.root/'index.m3u8').write_text('#EXTM3U\n#EXTINF:1.000,\nseg-000000001.m4s\n')
        self.assertEqual(manifest(self.frames)['codec'],'avc1.4d4029')
    def test_traversal_and_foreign_session_rejected(self):
        for name,session in [('../status.json','example'),('init.mp4','other')]:
            with self.subTest(name=name),self.assertRaises(ValueError):media(self.frames,name,session)
    def test_external_fragment_uri_rejected(self):
        (self.root/'index.m3u8').write_text('#EXTM3U\n#EXTINF:1,\nhttp://example.com/file.m4s\n')
        with self.assertRaises(ValueError):manifest(self.frames)
    def test_stale_stream_rejected(self):
        self.state['ready']=False
        with self.assertRaises(RuntimeError):media(self.frames,'init.mp4')

if __name__=='__main__':unittest.main()
