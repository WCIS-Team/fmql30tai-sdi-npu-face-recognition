import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'npu_photo'))
from recording_service import durable_json
from recording_library import Library

JPEG=b'\xff\xd8abc\xff\xd9'
class Store:
    def __init__(self,root):self.root=Path(root);self.used=0
    def guard(self):pass
    def account(self,n):self.used=max(0,self.used+n)

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.now=1800000000
        self.library=Library(self.store,durable_json,clock=lambda:self.now)
    def make(self,i=1,stamp=None):
        key='rec-20261026T110000Z-'+f'{i:012x}'
        stamp=self.now if stamp is None else stamp
        first=dict(received_unix=stamp,captured_at=10)
        q=dict(id=key,state='complete',frames=3,bytes=3*len(JPEG),first=first,
               last=dict(received_unix=stamp+1,captured_at=11),capture_span_s=1,event=dict(trigger='manual'))
        (self.store.root/(key+'.mjpeg')).write_bytes(JPEG*3)
        (self.store.root/(key+'.frames.jsonl')).write_text(''.join(json.dumps(dict(captured_at=10+n*.5,offset=n*len(JPEG),length=len(JPEG)))+'\n' for n in range(3)))
        durable_json(self.store.root/(key+'.json'),q)
        self.store.used=sum(p.stat().st_size for p in self.store.root.glob('rec-*'))
        return key
    def test_paging_and_shanghai_date(self):
        start=self.library.date_bound('2026-10-26')
        for i in range(24):self.make(i,start+i)
        self.make(40,start-1);self.make(41,start+86400)
        a=self.library.listing(start='2026-10-26',end='2026-10-26',page=1)
        b=self.library.listing(start='2026-10-26',end='2026-10-26',page=2)
        self.assertEqual(a['total'],24);self.assertEqual(len(a['recordings']),20)
        self.assertEqual(len(b['recordings']),4)
        self.assertFalse({q['id'] for q in a['recordings']}&{q['id'] for q in b['recordings']})
        with self.assertRaises(ValueError):self.library.listing(start='2026-10-27',end='2026-10-26')
    def test_soft_delete_restore_does_not_release_bytes(self):
        key=self.make();size=self.store.used;self.library.delete(key)
        self.assertEqual(self.library.listing()['total'],0);self.assertEqual(self.library.listing(trash=True)['total'],1)
        self.assertEqual(self.store.used,size)
        with self.assertRaises(FileNotFoundError):self.library.frame(key,0)
        self.library.restore(key);self.assertEqual(self.library.frame(key,0),(JPEG,0))
        self.assertEqual(self.store.used,size)
    def test_purge_requires_trash_and_waits_for_reader(self):
        key=self.make()
        with self.assertRaises(ValueError):self.library.purge(key)
        with self.library.opened(key,'.mjpeg') as (f,_):
            self.library.delete(key)
            with self.assertRaises(RuntimeError):self.library.purge(key)
            self.assertEqual(f.read(),JPEG*3)
        self.library.purge(key);self.assertEqual(self.store.used,0)
        self.assertFalse(list(self.store.root.glob('rec-*')))
    def test_interrupted_purge_resumes_journal(self):
        key=self.make();self.library.delete(key)
        original=Path.unlink
        def fail(path,*a,**kw):
            if path.name==key+'.frames.jsonl':raise OSError('power interruption')
            return original(path,*a,**kw)
        with patch.object(Path,'unlink',fail):
            with self.assertRaises(OSError):self.library.purge(key)
        self.assertTrue(self.library._marker(key)['purging'])
        with self.assertRaises((RuntimeError,ValueError)):self.library.restore(key)
        Library(self.store,durable_json);self.assertFalse(list(self.store.root.glob('rec-*')))
    def test_retention_disabled_then_age_two_stages(self):
        key=self.make(stamp=self.now-10*86400)
        self.library.maintain();self.assertEqual(self.library.listing()['total'],1)
        self.library.set_policy(dict(enabled=True,days=7,trash_days=2));self.library.maintain()
        self.assertEqual(self.library.listing(trash=True)['total'],1)
        self.now+=86400;self.library.maintain();self.assertTrue(self.library.path(key,'.mjpeg').exists())
        self.now+=86400;self.library.maintain();self.assertFalse(self.library.path(key,'.mjpeg').exists())
    def test_policy_survives_restart_and_validates(self):
        policy=dict(enabled=False,days=3,trash_days=4);self.library.set_policy(policy)
        self.assertEqual(Library(self.store,durable_json).policy,policy)
        for invalid in (dict(enabled=1,days=7,trash_days=7),dict(enabled=True,days=0,trash_days=1),dict(enabled=True,days=7)):
            with self.assertRaises(ValueError):self.library.set_policy(invalid)
    def test_timestamp_seek_and_invalid_index(self):
        key=self.make();self.assertEqual(self.library.frame(key,.7),(JPEG,.5))
        self.assertEqual(self.library.frame(key,99),(JPEG,1))
        for at in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):self.library.frame(key,at)
        p=self.library.path(key,'.frames.jsonl');p.write_text('{"captured_at":10,"offset":1,"length":7}\n')
        with self.assertRaises(ValueError):self.library.frame(key,0)
    def test_incomplete_files_not_listed_or_deleted(self):
        key='rec-20261026T110000Z-000000000001';p=self.store.root/(key+'.mjpeg.part');p.write_bytes(JPEG)
        self.assertEqual(self.library.listing()['total'],0)
        with self.assertRaises(FileNotFoundError):self.library.delete(key)
        self.library.set_policy(dict(enabled=True,days=1,trash_days=1));self.library.maintain();self.assertTrue(p.exists())
    def test_traversal_unknown_suffix_and_corrupt_manifest(self):
        for key in ('../retention','/tmp/record','rec-../../x'):
            with self.assertRaises(ValueError):self.library.delete(key)
        key=self.make()
        with self.assertRaises(ValueError):self.library.path(key,'.part')
        self.library.path(key,'.json').write_text('{broken')
        q=self.library.listing();self.assertEqual(q['invalid_records'],1);self.assertEqual(q['total'],0)
    def test_storage_counts_trash_until_permanent_delete(self):
        self.store.quota=4*1024**3;self.store.reserve=512*1024**2
        a=self.make(1);b=self.make(2);before=self.library.storage_usage()
        self.library.delete(a);trash=self.library.storage_usage()
        self.assertEqual(trash['active_count'],1);self.assertEqual(trash['trash_count'],1)
        self.assertEqual(before['recording_file_bytes'],trash['recording_file_bytes'])
        self.assertEqual(before['quota_used_bytes'],trash['quota_used_bytes'])
        self.library.purge(a);after=self.library.storage_usage()
        self.assertEqual(after['trash_bytes'],0);self.assertEqual(after['active_count'],1)
        self.assertEqual(before['quota_used_bytes']-after['quota_used_bytes'],trash['trash_bytes'])
        self.assertEqual(after['recording_file_bytes'],sum(self.library.path(b,s).stat().st_size for s in ('.json','.mjpeg','.frames.jsonl')))
    def test_storage_unfinished_and_disk_reserve(self):
        from types import SimpleNamespace
        self.store.quota=4*1024**3;self.store.reserve=512*1024**2
        key='rec-20261026T110000Z-000000000001'
        (self.store.root/(key+'.mjpeg.part')).write_bytes(JPEG)
        with patch('recording_library.shutil.disk_usage',return_value=SimpleNamespace(total=1000000000,used=900000000,free=100000000)):
            q=self.library.storage_usage()
        self.assertEqual(q['unfinished_count'],1);self.assertEqual(q['unfinished_bytes'],len(JPEG))
        self.assertEqual(q['available_recording_bytes'],0);self.assertEqual(q['active_count'],0)

if __name__=='__main__':unittest.main()
