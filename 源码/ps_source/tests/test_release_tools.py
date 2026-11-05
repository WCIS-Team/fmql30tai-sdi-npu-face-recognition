"""Maintenance-tool regression: no real board or network access."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verify_app_release import verify
from assemble_camera_site import assemble
from wait_visual_ready import wait_ready


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'app.py').write_bytes(b'original')
        self.row = dict(file='app.py', sha256=hashlib.sha256(b'original').hexdigest())

    def test_valid_and_runtime_extras(self):
        (self.root / 'runtime.json').write_text('{}')
        self.assertTrue(verify(self.root, dict(files=[self.row]))['passed'])

    def test_changed_and_missing(self):
        (self.root / 'app.py').write_bytes(b'changed')
        self.assertFalse(verify(self.root, dict(files=[self.row]))['passed'])
        (self.root / 'app.py').unlink()
        self.assertFalse(verify(self.root, dict(files=[self.row]))['passed'])

    def test_unsafe_manifest(self):
        for name in ['../app.py','/app.py','D:/app.py','a\\b','a/../app.py','a//b']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify(self.root, dict(files=[dict(self.row,file=name)]))
        with self.assertRaises(ValueError):
            verify(self.root, dict(files=[self.row,self.row]))
        with self.assertRaises(ValueError):
            verify(self.root, dict(files=[]))

    def test_ambiguous_template(self):
        with self.assertRaises(ValueError):
            assemble('no substitution markers','<section id="cameraPanel"></section>','v1')


class ReadinessTests(unittest.TestCase):
    def scenario(self, *, delayed=False, stalled=False, wrong_boot=False, failed_recorder=False, owner_changes=False):
        now = [0.0]
        camera_calls = [0]
        def fetch(service, path, deadline):
            if delayed and now[0] < .5:
                raise ConnectionRefusedError('listener has not started')
            if path == '/api/health':
                return dict(status='ready',model_cache_ready=True,hardware_admission_ready=True,boot_id='boot')
            if path == '/api/status':
                return dict(source_ready=True,mode='off',state='idle',current=None,error='disk' if failed_recorder else None)
            camera_calls[0] += 1
            n = camera_calls[0]
            return dict(ready=True,codec='h264',width=960,height=540,boot_id='other' if wrong_boot else 'boot',
                        session=str(n) if owner_changes else 'session',pid=n if owner_changes else 1,
                        encoded=1 if stalled else n,frame_id=1 if stalled else n)
        def sleep(dt): now[0] += dt
        return wait_ready(fetch,'boot',timeout=2,clock=lambda:now[0],sleep=sleep)

    def test_delayed_listener_is_retried(self):
        q = self.scenario(delayed=True)
        self.assertTrue(q['passed'])
        self.assertGreater(q['attempts'],2)

    def test_static_ready_is_not_enough(self):
        self.assertFalse(self.scenario(stalled=True)['passed'])

    def test_wrong_boot_rejected(self):
        self.assertFalse(self.scenario(wrong_boot=True)['passed'])

    def test_recorder_error_rejected(self):
        self.assertFalse(self.scenario(failed_recorder=True)['passed'])

    def test_changing_owners_cannot_supply_progress(self):
        self.assertFalse(self.scenario(owner_changes=True)['passed'])


if __name__ == '__main__':
    unittest.main()
