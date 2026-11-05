"""No hardware needed: event policy, bounds, timestamps, durability failures."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'npu_photo'))
from recording_service import Recorder, Segment, Storage, MIB

JPEG=b'\xff\xd8payload\xff\xd9'

class Store:
    def __init__(self,root):
        self.root=Path(root);self.used=0;self.quota=4096*MIB;self.reserve=0;self.error=None
    def admit(self,n):
        if self.error:raise OSError(self.error)
    def account(self,n):self.used=max(0,self.used+n)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.now=10.;self.store=Store(self.tmp.name)
        self.r=Recorder(self.store,clock=lambda:self.now)
    def frame(self,i,session='a'):
        return dict(ready=True,source='camera',vpu_enabled=True,width=960,height=540,boot_id='boot',
                    session=session,frame_id=i,captured_at=self.now,timestamp_basis='capture_request_lower_bound')
    def put(self,i,session='a'):
        f=self.frame(i,session);self.r.ingest(f,JPEG);return f
    def detect(self,f,count):
        return self.r.detection(dict(camera_frame=f,face_count=count))
    def test_auto_preroll_and_tail_unknown_face(self):
        self.r.command('auto');f=self.put(1);self.now+=.5;self.put(2)
        self.assertTrue(self.detect(f,1));self.now+=.5;self.put(3)
        self.assertEqual([x[0]['frame_id'] for x in self.r.pending],[1,2,3])
        self.assertTrue(self.r.active)
        self.now+=4;self.put(4);self.assertTrue(self.r.active)
        self.now+=2;self.put(5);self.assertFalse(self.r.active)
    def test_stale_cross_session_and_disarmed_results(self):
        self.r.command('auto');f=self.put(1);self.now+=4
        self.assertFalse(self.detect(f,1));self.assertEqual(self.r.deadline,0)
        f=self.put(2,'b');f['session']='a';self.assertFalse(self.detect(f,1))
        self.r.command('off');f=self.put(3,'b');self.assertTrue(self.detect(f,1));self.assertEqual(self.r.deadline,0)
    def test_no_face_and_multiface_policy(self):
        self.r.command('auto');f=self.put(1);self.detect(f,0);self.put(2);self.assertFalse(self.r.pending)
        self.detect(f,4);self.put(3);self.assertTrue(self.r.pending)
    def test_duplicate_frame_and_reconnect(self):
        self.r.command('manual');self.put(1);self.put(1);self.put(0)
        self.assertEqual(len(self.r.pending),1)
        first=self.r.pending[0][2]['id'];self.put(1,'new')
        self.assertEqual(len(self.r.pending),2);self.assertNotEqual(first,self.r.pending[-1][2]['id'])
    def test_memory_backpressure_does_not_grow(self):
        self.r.limit=len(JPEG)*2;self.r.command('manual')
        for i in range(100):self.put(i)
        self.assertEqual(self.r.dropped,98)
        self.assertLessEqual(self.r.pending_bytes,self.r.limit);self.assertLessEqual(self.r.ring_bytes,self.r.limit)
    def test_source_failure_closes_event_and_forgets_preroll(self):
        self.r.command('manual');self.put(1);self.r.ingest(dict(ready=False),None)
        self.assertFalse(self.r.active);self.assertFalse(self.r.ring)
    def test_wrong_source_rejected(self):
        f=self.frame(1);f['source']='vtc'
        with self.assertRaises(ValueError):self.r.ingest(f,JPEG)
    def test_segments_index_offsets_and_shutdown_drain(self):
        self.r.segment_seconds=1;self.r.command('manual')
        for i in range(6):self.put(i);self.now+=.6
        self.r.start();self.r.close()
        summaries=sorted(self.store.root.glob('rec-*.json'))
        self.assertEqual(len(summaries),3)
        ids=[]
        for p in summaries:
            q=json.loads(p.read_text());self.assertEqual(q['state'],'complete')
            data=p.with_suffix('.mjpeg').read_bytes()
            for line in p.with_suffix('.frames.jsonl').read_text().splitlines():
                row=json.loads(line);ids.append(row['frame_id'])
                self.assertEqual(data[row['offset']:row['offset']+row['length']],JPEG)
        self.assertEqual(sorted(ids),list(range(6)));self.assertFalse(list(self.store.root.glob('*.part')))
    def test_disk_error_latches_and_does_not_claim_success(self):
        self.r.command('manual');self.put(1);self.store.error='disk full';self.r.start();self.r.close()
        self.assertIn('disk full',self.r.error);self.assertFalse(list(self.store.root.glob('rec-*.json')))
        with self.assertRaises(RuntimeError):self.r.command('manual')
    def test_fsync_failure_keeps_partial(self):
        f=self.frame(1);f['received_unix']=1
        part=Segment(self.store,f,{'id':'e','trigger':'manual'},60);part.write(f,JPEG)
        with patch('recording_service.os.fsync',side_effect=OSError('sync failed')):
            with self.assertRaises(OSError):part.finish('test')
        part.abandon();self.assertTrue(list(self.store.root.glob('*.part')))
        self.assertFalse(list(self.store.root.glob('rec-*.json')))
    def test_h264_index_keeps_real_source_frame_ids_separate_from_fragment_id(self):
        frame=dict(self.frame(12),codec='h264',_h264_init=b'init',received_unix=100,
                   captured_end=self.now+1,samples=30,duration=1,frame_id_basis='hls_segment_sequence',
                   source_first_frame=301,source_last_frame=331,capture_time_basis='native_raw_input_journal')
        part=Segment(self.store,frame,{'id':'e','trigger':'manual'},60)
        part.write(frame,b'fragment');part.abandon()
        row=json.loads(part.base.with_suffix('.frames.jsonl.part').read_text())
        self.assertEqual(row['frame_id'],12);self.assertEqual(row['source_first_frame'],301)
        self.assertEqual(row['source_last_frame'],331)
        self.assertEqual(row['capture_time_basis'],'native_raw_input_journal')
    def test_old_result_after_rearming_cannot_trigger(self):
        f=self.put(1);self.now+=.2;self.r.command('auto');self.detect(f,1)
        self.assertEqual(self.r.deadline,0)
    def test_quota_and_free_space_stop_without_deleting(self):
        from types import SimpleNamespace
        store=Storage.__new__(Storage);store.root=self.store.root;store.guard=lambda:None
        store.used=10*MIB;store.quota=11*MIB;store.reserve=512*MIB
        with self.assertRaisesRegex(RuntimeError,'quota'):store.admit(1)
        store.quota=100*MIB
        with patch('recording_service.shutil.disk_usage',return_value=SimpleNamespace(free=512*MIB)):
            with self.assertRaisesRegex(RuntimeError,'reserve'):store.admit(1)
    def test_missing_mount_never_falls_back(self):
        store=Storage.__new__(Storage);store.mount=self.store.root;store.root=self.store.root;store.device=self.store.root.stat().st_dev
        with self.assertRaisesRegex(RuntimeError,'no SD fallback'):store.guard()

if __name__=='__main__':unittest.main()
