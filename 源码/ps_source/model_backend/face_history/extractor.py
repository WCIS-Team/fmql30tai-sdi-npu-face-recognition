"""Explicit board NPU adapter; no model compilation or CPU fallback."""
import json
from pathlib import Path
import sys
import tempfile
import subprocess
import os
import select
import time

import cv2

from .records import file_sha


class _BoardExtractor:
    def __init__(self, config_path, work):
        if sys.platform != 'linux':
            raise RuntimeError('NPU extraction must run on the board; use result import off-board')
        self.work = Path(work)
        self.work.mkdir(parents=True, exist_ok=True)
        self.config_path = Path(config_path)
        cfg = json.loads(self.config_path.read_text())
        self.app, self.root = Path(cfg['app']), Path(cfg['release'])
        self.config_digest = file_sha(self.config_path)
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if boot != cfg['verified_boot_id']:
            raise RuntimeError('Boot changed; revalidate the board input configuration')
        for record in cfg['files']:
            if file_sha(self.app / record['file']) != record['sha256']:
                raise RuntimeError('Configured backend artifact changed')
        unit = Path('/etc/systemd/system/wcis-face-photo.service')
        if file_sha(unit) != cfg['photo_service_sha256']:
            raise RuntimeError('Photo service changed; refresh the validated configuration')
        verification = json.loads(Path(cfg['verification']).read_text())
        if not verification['passed'] or verification['app'] != str(self.app):
            raise RuntimeError('No matching backend validation')
        marker = self.root.parents[1] / 'hardware-review-required.json'
        if marker.exists() and json.loads(marker.read_text()).get('boot_id') == boot:
            raise RuntimeError('Board hardware requires review')
        sys.path.insert(0, str(self.app))
        from recognize_photo import recognize
        from model_backend_runtime import ModelBackend
        # Never silently import stale modules from another application.
        for module in ('recognize_photo', 'model_backend_runtime'):
            if Path(sys.modules[module].__file__).resolve().parent != self.app.resolve():
                raise RuntimeError('A different backend application is already imported')
        manifest = json.loads((self.root / 'models.json').read_text())
        self.pipeline_id = 'yunet-mf-' + manifest['precision'] + '-npu:' + file_sha(self.root / 'models.json')
        self.recognize = recognize
        self.backend = ModelBackend(self.root, self.app / 'wcis_face_cached')

    def extract(self, image):
        if file_sha(self.config_path) != self.config_digest:
            raise RuntimeError('Backend configuration changed during this run')
        if not image.size or image.shape[0] * image.shape[1] > 16000000:
            raise ValueError('Invalid or oversized offline frame')
        with tempfile.TemporaryDirectory(prefix='history-frame-', dir=str(self.work)) as temp:
            work = Path(temp)
            photo = work / 'input.png'
            if not cv2.imwrite(str(photo), image):
                raise ValueError('Cannot prepare lossless offline input')
            result = self.recognize(self.root, photo, work / 'inference',
                gallery=dict(pipeline_id=self.pipeline_id, people={}),
                return_embedding=True, pl_executable=self.app / 'wcis_face_pl_retained',
                model_backend=self.backend)
            # The existing request owns npu.lock and retained DDR until complete.
            return result

    def close(self):
        self.backend.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class NPUExtractor:
    """A separate session prevents terminal group interrupts reaching SDK/DMA."""
    def __init__(self, config_path, work):
        if sys.platform != 'linux':
            raise RuntimeError('NPU extraction must run on the board; use result import off-board')
        self.work = Path(work)
        self.work.mkdir(parents=True, exist_ok=True)
        self.log = (self.work / 'extractor.stderr.log').open('ab')
        self.buffer = b''
        env = dict(os.environ)
        base = str(Path(__file__).resolve().parents[1])
        env['PYTHONPATH'] = base + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
        env['PYTHONPYCACHEPREFIX'] = str(self.work / 'pycache')
        for name in ('TMP', 'TEMP', 'TMPDIR'):
            env[name] = str(self.work)
        self.process = subprocess.Popen([sys.executable, '-u', '-c',
            'from face_history.extractor import worker_main; worker_main()',
            str(config_path), str(self.work)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.log, env=env, start_new_session=True)
        try:
            ready = self._read(90)
            if ready.get('status') != 'ready':
                raise RuntimeError('NPU history worker did not become ready')
            self.pipeline_id = ready['pipeline_id']
        except BaseException:
            self.close()
            raise

    def _read(self, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                value = json.loads(line)
                if value.get('status') == 'error':
                    raise RuntimeError(value.get('error', 'NPU history worker failed'))
                return value
            if select.select([self.process.stdout], [], [], max(0, deadline - time.monotonic()))[0]:
                data = os.read(self.process.stdout.fileno(), 65536)
                if not data:
                    raise RuntimeError('NPU history worker exited; inspect private stderr log')
                self.buffer += data
                if len(self.buffer) > 4 * 1024 * 1024:
                    raise RuntimeError('NPU result exceeds bounded protocol size')
        raise TimeoutError('NPU history worker deadline; drain before another hardware use')

    def extract(self, image):
        with tempfile.TemporaryDirectory(prefix='history-request-', dir=str(self.work)) as temp:
            path = Path(temp) / 'input.png'
            if not cv2.imwrite(str(path), image):
                raise ValueError('Cannot prepare offline frame')
            self.process.stdin.write((json.dumps(dict(image=str(path))) + '\n').encode())
            self.process.stdin.flush()
            return self._read(180)['result']

    def close(self):
        try:
            if not self.process.stdin.closed:
                self.process.stdin.close()
            # EOF drains the request; never kill an active SDK device owner.
            self.process.wait(timeout=240)
            self.process.stdout.close()
        finally:
            self.log.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def worker_main():
    extractor = None
    try:
        extractor = _BoardExtractor(sys.argv[1], sys.argv[2])
        print(json.dumps(dict(status='ready', pipeline_id=extractor.pipeline_id)), flush=True)
        for line in sys.stdin:
            value = json.loads(line)
            path = Path(value['image']).resolve(strict=True)
            path.relative_to(extractor.work.resolve())
            image = cv2.imread(str(path), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
            if image is None:
                raise ValueError('Cannot decode offline request')
            result = extractor.extract(image)
            print(json.dumps(dict(status='complete', result=result), allow_nan=False), flush=True)
    except Exception as error:
        print(json.dumps(dict(status='error', error_type=type(error).__name__, error=str(error))), flush=True)
    finally:
        if extractor is not None:
            extractor.close()
