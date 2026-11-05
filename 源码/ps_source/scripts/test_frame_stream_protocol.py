"""Transport corruption/bounds tests; no SDK or board required."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'npu_photo'))
from frame_stream_protocol import PREFIX,MAGIC,encode_header,read_packet,MAX_PAYLOAD


class Fragmented(io.BytesIO):
    def read(self,size=-1):return super().read(min(size,3))


class StreamProtocolTests(unittest.TestCase):
    def frame(self,sequence=1):
        pixels=b'\x12\x34'*8
        meta=dict(version=1,kind='frame',stream_id='a'*32,sequence=sequence,pts_us=sequence*33333,
                  width=4,height=2,pitch_bytes=8,pixel_format='RGB565LE',sha256=hashlib.sha256(pixels).hexdigest())
        return meta,pixels
    def test_fragmented_frames_and_finish(self):
        one,payload=self.frame();two,_=self.frame(20)
        finish=dict(version=1,kind='finish',stream_id='a'*32)
        data=Fragmented(encode_header(one,len(payload))+payload+encode_header(two,len(payload))+payload+encode_header(finish,0))
        self.assertEqual(read_packet(data)[:2],(one,payload))
        self.assertEqual(read_packet(data)[:2],(two,payload))
        self.assertEqual(read_packet(data)[0],finish);self.assertIsNone(read_packet(data))
    def test_truncated_payload(self):
        meta,payload=self.frame()
        with self.assertRaises(EOFError):read_packet(Fragmented(encode_header(meta,len(payload))+payload[:-1]))
    def test_bad_checksum(self):
        meta,payload=self.frame()
        with self.assertRaises(ValueError):read_packet(Fragmented(encode_header(meta,len(payload))+b'x'*len(payload)))
    def test_oversized_prefix_rejected_before_body(self):
        with self.assertRaises(ValueError):read_packet(io.BytesIO(PREFIX.pack(MAGIC,100,MAX_PAYLOAD+1)))
    def test_bad_stride_and_boolean_geometry(self):
        meta,payload=self.frame()
        for fields in ({'pitch_bytes':7},{'width':True},{'sequence':0},{'pixel_format':'JPEG'}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):encode_header(dict(meta,**fields),len(payload))
    def test_truncated_prefix(self):
        with self.assertRaises(EOFError):read_packet(Fragmented(MAGIC[:3]))
    def test_known_colors_and_padded_stride(self):
        try:import numpy as np
        except ImportError:self.skipTest('Run with the local video Python environment')
        from stream_video_to_board import pack_frame
        image=np.asarray([[[0,0,255],[0,255,0],[255,0,0]]],np.uint8)
        pixels,w,h,pitch=pack_frame(image,'RGB565LE',np)
        self.assertEqual((w,h,pitch),(3,1,8))
        self.assertEqual(pixels,b'\x00\xf8\xe0\x07\x1f\x00\x00\x00')
        pixels,w,h,pitch=pack_frame(image,'BGRX8',np)
        self.assertEqual(pitch,16)
        self.assertEqual(pixels,b'\x00\x00\xff\x00\x00\xff\x00\x00\xff\x00\x00\x00'+b'\x00'*4)
    def test_latest_slot_drops_old_frames(self):
        import threading
        from stream_video_to_board import LatestFrames
        class Reader:
            def __init__(self):self.sequence=0;self.closed=False
            def read(self):
                self.sequence+=1
                return dict(sequence=self.sequence,pts_us=self.sequence*10000) if self.sequence<=3 else None
            def close(self):self.closed=True
        reader=Reader();source=LatestFrames(reader,threading.Event());source.start();source.thread.join(timeout=2)
        self.assertFalse(source.thread.is_alive());self.assertEqual(source.take()['sequence'],3)
        self.assertIsNone(source.take());self.assertTrue(reader.closed);source.close()


if __name__=='__main__':unittest.main()
