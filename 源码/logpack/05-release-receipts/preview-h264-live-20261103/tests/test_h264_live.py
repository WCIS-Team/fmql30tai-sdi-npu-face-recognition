import struct
import time
import unittest
from h264_live import LiveFragments

def box(kind,data):return struct.pack('>I4s',len(data)+8,kind)+data
INIT=box(b'ftyp',b'isom')+box(b'moov',box(b'mdia',box(b'mdhd',b'\0'*12+struct.pack('>I',30)))+box(b'avcC',bytes.fromhex('014d001eff')))
def fragment(n,key=False):
 return box(b'moof',box(b'traf',box(b'tfdt',b'\0'*4+struct.pack('>I',n))+box(b'trun',b'\0'*4+struct.pack('>I',1))))+box(b'mdat',b'\0\0\0\1'+(b'\x65' if key else b'\x41'))
def capture(_):return dict(start=time.monotonic()-.04,end=time.monotonic()-.01)

class LiveTests(unittest.TestCase):
 def test_arbitrary_pipe_boundaries_preserve_complete_keyframe_start(self):
  q=LiveFragments(capture);data=INIT+b''.join(fragment(n,n%30==0) for n in range(150))
  for n in range(0,len(data),7):q.feed(data[n:n+7])
  init,rows=q.read();self.assertEqual(init,INIT);self.assertEqual(rows[0]['sequence'],120);self.assertTrue(rows[0]['key']);self.assertEqual(rows[-1]['sequence'],149)
  self.assertLessEqual(len(q.rows),60)
 def test_slow_consumers_cannot_receive_a_discontinuous_stream(self):
  q=LiveFragments(capture);q.feed(INIT+b''.join(fragment(n,n%30==0) for n in range(150)))
  with self.assertRaisesRegex(RuntimeError,'missed'):q.read(0)
  self.assertEqual(q.read(149)[1],[])
 def test_partial_fragment_and_priming_are_not_published(self):
  q=LiveFragments(lambda i:None if i<2 else capture(i));q.feed(INIT+fragment(0,True)+fragment(1))
  with self.assertRaises(RuntimeError):q.read()
  data=fragment(2,True);q.feed(data[:-1])
  with self.assertRaises(RuntimeError):q.read()
  q.feed(data[-1:]);self.assertEqual(q.read()[1][0]['sequence'],2)
 def test_stale_failed_and_closed_outputs_fail_without_retaining_data(self):
  q=LiveFragments(lambda _:dict(end=time.monotonic()-3));q.feed(INIT+fragment(0,True))
  with self.assertRaises(RuntimeError):q.read()
  q.fail('bad');self.assertEqual(q.bytes,0);self.assertFalse(q.rows)
  with self.assertRaises(RuntimeError):q.read()
  q=LiveFragments(capture);q.feed(INIT+fragment(0,True));q.close()
  with self.assertRaises(RuntimeError):q.read()
 def test_malformed_boxes_nals_and_excessive_gops_are_rejected(self):
  q=LiveFragments(capture)
  with self.assertRaises(ValueError):q.feed(b'\0'*8)
  q=LiveFragments(capture,limit=1)
  with self.assertRaisesRegex(ValueError,'bounds'):q.feed(INIT+fragment(0,True))
  q=LiveFragments(capture);q.feed(INIT)
  with self.assertRaises(ValueError):q.feed(box(b'mdat',b'bad'))

if __name__=='__main__':unittest.main()
