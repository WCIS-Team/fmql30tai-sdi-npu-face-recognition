import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'npu_photo'))
from recording_compression import IdleCompression, fingerprint, PROFILE
from recording_library import Library
from recording_service import durable_json


class Store:
    def __init__(self, root):
        self.root=Path(root);self.used=0;self.quota=1024**3;self.reserve=0
    def guard(self): pass
    def admit(self, n): pass
    def account(self, n): self.used += n


class Recorder:
    state='idle'
    def status(self):return dict(state=self.state,queue_bytes=0,error=None)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name)
        self.library=Library(self.store,durable_json)
        self.recorder=Recorder();self.stop=threading.Event();self.quiet=True
        self.worker=IdleCompression(self.library,self.recorder,self.stop,idle_seconds=0,idle_check=lambda:self.quiet)
        self.key='rec-20261031T110000Z-0123456789ab'
        self.make()
    def make(self):
        p=self.store.root/self.key
        p.with_suffix('.mp4').write_bytes(b'fake mp4 fixture')
        p.with_suffix('.frames.jsonl').write_text(''.join(json.dumps(dict(captured_at=10+i*.5,offset=i*7,length=7))+'\n' for i in range(3)))
        durable_json(p.with_suffix('.json'),dict(id=self.key,state='complete',format='h264_mp4',frames=3,bytes=15,
            first=dict(captured_at=10,received_unix=100,width=960,height=540),last=dict(captured_at=11,received_unix=101),capture_span_s=1))
        self.store.used=sum(p.stat().st_size for p in self.store.root.glob('rec-*'))
    def test_completed_only_and_persisted_skip_keeps_originals(self):
        original={p.name:p.read_bytes() for p in self.store.root.glob('rec-*')}
        self.assertEqual(self.worker.candidate(),self.key)
        q=self.worker.compress(self.key)
        self.assertEqual(q['state'],'skipped');self.assertIsNone(self.worker.candidate())
        for name,data in original.items():self.assertEqual((self.store.root/name).read_bytes(),data)
        self.assertEqual(self.store.used,sum(p.stat().st_size for p in self.store.root.glob('rec-*')))
    def test_busy_or_reader_resets_idle_and_current_input_pin_is_allowed(self):
        self.assertTrue(self.worker.idle());self.recorder.state='recording';self.assertFalse(self.worker.idle())
        self.recorder.state='idle';self.quiet=False;self.assertFalse(self.worker.idle());self.quiet=True
        with self.library.opened(self.key,'.mp4'):
            self.assertFalse(self.worker.idle());self.worker.current=self.key;self.assertTrue(self.worker.idle())
            with self.library.opened(self.key,'.mp4'):self.assertFalse(self.worker.idle())
        self.worker.current=None;self.assertTrue(self.worker.idle())
    def test_idle_window_and_policy_survive_restart(self):
        self.worker.idle_seconds=60
        with patch('recording_compression.time.monotonic',return_value=100):self.assertFalse(self.worker.idle())
        with patch('recording_compression.time.monotonic',return_value=160):self.assertTrue(self.worker.idle())
        self.worker.set_policy(dict(enabled=False));self.assertFalse(self.worker.idle())
        other=IdleCompression(self.library,self.recorder,self.stop,idle_check=lambda:True)
        self.assertFalse(other.enabled)
        for q in [dict(enabled=1),dict(enabled=True,crf=40),None]:
            with self.assertRaises(ValueError):self.worker.set_policy(q)
    def test_legacy_mjpeg_is_never_a_candidate_or_modified(self):
        p=self.library.path(self.key,'.json');q=json.loads(p.read_text())
        q['format']='raw_mjpeg_with_timestamp_index';durable_json(p,q)
        self.library.path(self.key,'.mjpeg').write_bytes(b'original jpeg')
        before={p.name:p.read_bytes() for p in self.store.root.glob('rec-*')}
        self.assertIsNone(self.worker.candidate());self.worker.compress(self.key)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.store.root.glob('rec-*')})
    def test_compressed_access_accounting_trash_and_purge(self):
        p=self.library.path(self.key,'.compressed.mp4');p.write_bytes(b'mp4')
        durable_json(self.library.path(self.key,'.compression.json'),dict(state='complete',bytes=3,original_bytes=21,
            potential_saving_bytes=18,source=fingerprint(self.library.path(self.key,'.mp4')),profile=PROFILE))
        self.store.used=sum(p.stat().st_size for p in self.store.root.glob('rec-*'))
        usage=self.library.storage_usage()
        self.assertEqual(usage['compressed_bytes'],3);self.assertEqual(usage['potential_saving_bytes'],18)
        self.assertEqual(usage['recording_file_bytes'],self.store.used)
        self.assertIsNone(self.worker.candidate())
        with self.library.opened(self.key,'.compressed.mp4') as (f,_):self.assertEqual(f.read(),b'mp4')
        self.library.delete(self.key)
        with self.assertRaises(FileNotFoundError):
            with self.library.opened(self.key,'.compressed.mp4'):pass
        self.library.restore(self.key);self.library.delete(self.key);self.library.purge(self.key)
        self.assertEqual(self.store.used,0);self.assertFalse(list(self.store.root.glob('rec-*')))
    def test_invalid_or_unpublished_copy_is_not_exposed(self):
        self.library.path(self.key,'.compressed.mp4').write_bytes(b'unverified')
        with self.assertRaises(FileNotFoundError):
            with self.library.opened(self.key,'.compressed.mp4'):pass
        self.library.path(self.key,'.compression.json').write_text('{"state":"complete","bytes":1}')
        self.assertIsNone(self.library.compression(self.key))
    def test_owned_scratch_recovery_does_not_touch_originals(self):
        scratch=self.worker.work_root/'output.mp4';scratch.write_bytes(b'partial')
        other=IdleCompression(self.library,self.recorder,self.stop,idle_check=lambda:True)
        self.assertFalse(scratch.exists());self.assertTrue(self.library.path(self.key,'.mp4').exists())
        self.assertEqual(other.work_bytes,0)


if __name__=='__main__':unittest.main()
