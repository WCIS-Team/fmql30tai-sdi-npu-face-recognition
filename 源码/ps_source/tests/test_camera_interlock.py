"""Reject stale/mismatched frames and unsafe SDK handoffs without hardware."""
from pathlib import Path
import json,struct,sys,tempfile,time,types,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'npu_photo'))
if sys.platform=='win32':
    sys.modules.setdefault('fcntl',types.SimpleNamespace(LOCK_EX=1,LOCK_NB=2,flock=lambda *_:None))
from camera_interlock import CameraInterlock

class CameraInterlockTests(unittest.TestCase):
    def setUp(self):
        base=Path('D:/yzd/tmp/face-camera-ready-20261020/tests') if sys.platform=='win32' else Path(tempfile.gettempdir())
        base.mkdir(parents=True,exist_ok=True);self.temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.live=self.root/'live';self.live.mkdir()
        self.release=self.root/'project/releases/r';self.release.mkdir(parents=True)
        config=self.root/'control.json';config.write_text(json.dumps(dict(root=str(self.live),unit='wcis-sdi-camera-live.service',boot_sha256='test')))
        self.owner=CameraInterlock(config,self.release);self.owner.boot=lambda:'boot'
        (self.live/'boot-proof.json').write_text(json.dumps(dict(boot_id='boot',boot_files={'BOOT.bin':'test'})))
        self.control=dict(session='a'*32,boot_id='boot',source='camera',pid=123,directory=str(self.live))
        self.meta=dict(source='camera',state='ready',boot_id='boot',pid=123,frame_id=1,width=960,height=540,captured_at=time.monotonic())
        self.calls=[];self.active=True
        self.owner.state=lambda:'active' if self.active else 'inactive'
        self.owner.current=lambda boot:self.control
        self.owner.cleanup=lambda control:None

    def packet(self,meta=None):
        header=json.dumps(meta or self.meta).encode();(self.live/'latest.frame').write_bytes(struct.pack('<I',len(header))+header+b'\xff\xd8test\xff\xd9')

    def service(self,args,**_):
        self.calls.append(args[1])
        if args[1]=='stop':
            self.active=False
            (self.live/('a'*32+'-result.json')).write_text(json.dumps(dict(exit_code=0,boot_id='boot',session='a'*32)))
        elif args[1]=='start':self.active=True
        return types.SimpleNamespace(returncode=0)

    def test_fresh_frame_identity(self):
        self.packet();sample=self.owner.snapshot(self.control)
        self.assertEqual(sample['identity']['frame_id'],1);self.assertEqual(sample['data'],b'\xff\xd8test\xff\xd9')

    def test_stale_or_foreign_frames_rejected(self):
        for changes in [dict(captured_at=time.monotonic()-2),dict(boot_id='other'),dict(pid=999),dict(source='vtc'),dict(width=1920)]:
            self.packet(dict(self.meta,**changes))
            with self.assertRaises(ValueError):self.owner.snapshot(self.control)

    def test_truncated_metadata_rejected(self):
        (self.live/'latest.frame').write_bytes(struct.pack('<I',16385)+b'xxxx')
        with self.assertRaises(ValueError):self.owner.snapshot(self.control)

    def test_inference_runs_only_after_drain_then_restores(self):
        with patch('camera_interlock.subprocess.run',side_effect=self.service):
            with self.owner.request():self.assertFalse(self.active)
        self.assertEqual(self.calls,['stop','start']);self.assertTrue(self.active)

    def test_invalid_photo_restores_capture(self):
        with patch('camera_interlock.subprocess.run',side_effect=self.service):
            with self.assertRaises(ValueError):
                with self.owner.request():raise ValueError('invalid image')
        self.assertEqual(self.calls,['stop','start'])

    def test_sdk_failure_quarantines_without_restart(self):
        with patch('camera_interlock.subprocess.run',side_effect=self.service):
            with self.assertRaises(RuntimeError):
                with self.owner.request():raise RuntimeError('SDK failed')
        self.assertEqual(self.calls,['stop']);self.assertTrue(self.owner.marker.is_file())
        with self.assertRaises(RuntimeError):self.owner.guard()

    def test_missing_drain_receipt_prevents_inference(self):
        def stop_without_receipt(args,**kwargs):self.active=False;self.calls.append(args[1])
        with patch('camera_interlock.subprocess.run',side_effect=stop_without_receipt):
            with self.assertRaises(FileNotFoundError):
                with self.owner.request():self.fail('SDK must not run')
        self.assertEqual(self.calls,['stop']);self.assertTrue(self.owner.marker.is_file())

    def test_cleanup_rejects_an_unowned_directory(self):
        with self.assertRaises(RuntimeError):CameraInterlock.cleanup(self.owner,self.control)
        self.assertTrue((self.live/'boot-proof.json').is_file())

    def test_waits_for_first_frame_without_sdk_retry(self):
        sample=dict(data=b'jpeg',identity={})
        with patch.object(self.owner,'snapshot',side_effect=[FileNotFoundError(),sample]) as read,patch('camera_interlock.time.sleep'):
            control,actual=self.owner.fresh_snapshot('boot')
        self.assertEqual(actual,sample);self.assertEqual(control,self.control);self.assertEqual(read.call_count,2)

    def test_quarantine_interrupts_frame_wait(self):
        def missing(control):
            self.owner.quarantine('test SDK failure');raise FileNotFoundError()
        with patch.object(self.owner,'snapshot',side_effect=missing) as read,patch('camera_interlock.time.sleep'):
            with self.assertRaises(RuntimeError):self.owner.fresh_snapshot('boot')
        self.assertEqual(read.call_count,1)

    def warm_worker(self):
        self.owner.config['handoff']='warm_process'
        self.control['handoff']='warm_process'
        def command(control,name,token):
            self.calls.append(name)
            if name=='pause.request':
                (self.live/'paused.json').write_text(json.dumps(dict(token=token,pid=123,boot_id='boot',device_closed=True)))
        self.owner.warm_command=command

    def test_warm_handoff_requires_closed_device_receipt_and_keeps_service(self):
        self.warm_worker()
        with patch('camera_interlock.subprocess.run',side_effect=AssertionError('No service restart')):
            with self.owner.request():
                self.assertEqual(self.calls,['pause.request']);self.assertTrue(self.active)
        self.assertEqual(self.calls,['pause.request','resume.request'])

    def test_warm_sdk_failure_never_resumes(self):
        self.warm_worker()
        with self.assertRaises(RuntimeError):
            with self.owner.request():raise RuntimeError('SDK failed')
        self.assertEqual(self.calls,['pause.request']);self.assertTrue(self.owner.marker.is_file())

    def test_stale_or_open_device_warm_receipt_blocks_inference(self):
        self.warm_worker()
        for proof in [dict(token='stale',pid=123,boot_id='boot',device_closed=True),
                      dict(pid=123,boot_id='boot',device_closed=False)]:
            if self.owner.marker.exists():self.owner.marker.unlink()
            def command(control,name,token):
                self.calls.append(name)
                (self.live/'paused.json').write_text(json.dumps(dict(dict(token=token),**proof)))
            self.owner.warm_command=command
            with patch('camera_interlock.time.monotonic',side_effect=range(0,1000,21)):
                with self.assertRaises(RuntimeError):
                    with self.owner.request():self.fail('Must not enter inference')
            self.assertTrue(self.owner.marker.is_file())
        self.assertNotIn('resume.request',self.calls)

    def test_busy_hardware_after_warm_receipt_quarantines(self):
        self.warm_worker()
        with patch('camera_interlock.fcntl.flock',side_effect=[None,BlockingIOError()]):
            with self.assertRaises(BlockingIOError):
                with self.owner.request():self.fail('Must not enter inference')
        self.assertEqual(self.calls,['pause.request']);self.assertTrue(self.owner.marker.is_file())

if __name__=='__main__':unittest.main()
