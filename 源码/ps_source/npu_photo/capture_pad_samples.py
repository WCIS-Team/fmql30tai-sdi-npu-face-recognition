"""Finite, operator-labeled SDI collection. Run on the board, one owner at a time.

Each label requires an explicit human readiness response before invocation.
This tool records ground truth separately from PAD predictions. It never grants
access, invents a label from the camera image, or changes boot files.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


LABELS = ('bona_fide', 'print', 'phone_still', 'phone_replay')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def face_box(faces, width, height):
    """Explicit floor/ceil clipping from this frame's floating xyxy detection."""
    if len(faces) != 1:
        return None
    x0, y0, x1, y1 = faces[0]['box']
    if not all(math.isfinite(x) for x in (x0, y0, x1, y1)):
        return None
    left, top = max(0, math.floor(x0)), max(0, math.floor(y0))
    right, bottom = min(width, math.ceil(x1)), min(height, math.ceil(y1))
    if right <= left or bottom <= top:
        return None
    return [left, top, right-left, bottom-top]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--label', choices=LABELS, required=True)
    p.add_argument('--operator-confirmed', action='store_true', required=True)
    p.add_argument('--confirmed-at', required=True, help='Human readiness time with timezone, from the collecting client')
    p.add_argument('--control', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--count', type=int, default=6)
    p.add_argument('--pad-bundle', type=Path)
    a = p.parse_args()
    if not 1 <= a.count <= 30:
        p.error('count must be 1..30')
    from datetime import datetime
    confirmed = datetime.fromisoformat(a.confirmed_at)
    if confirmed.tzinfo is None:
        p.error('confirmed-at must include a timezone')
    out = a.out.resolve()
    allowed = Path('/mnt/wcis-emmc/wcis-face/acceptance')
    if allowed not in out.parents or out.exists():
        p.error('Use a new directory under the mounted eMMC acceptance store')
    cfg = json.loads(Path('/root/wcis-face/video-stream-current.json').read_text())
    app, release = Path(cfg['app']), Path(cfg['release'])
    for record in cfg['files']:
        if sha(app/record['file']) != record['sha256']:
            raise RuntimeError('Formal application checksum mismatch: '+record['file'])
    sys.path.insert(0, str(app))
    import cv2
    import numpy as np
    from camera_owner_runtime import CameraOwner
    from camera_interlock import CameraInterlock
    from persistent_gallery import PersistentGallery
    guard = CameraInterlock('/root/wcis-face/candidates/face-camera-ready-20261020/camera-control.json', release)
    boot = guard.guard()
    if not a.control.is_file():
        raise RuntimeError('Missing formal owner control')
    control = json.loads(a.control.read_text())
    if control['boot_id'] != boot:
        raise RuntimeError('Formal control belongs to another boot')
    binary = app/'wcis_camera_owner'
    digest = next(x['sha256'] for x in cfg['files'] if x['file'] == 'wcis_camera_owner')
    gallery = PersistentGallery(release, Path('/mnt/wcis-emmc/wcis-face/galleries'), Path('/mnt/wcis-emmc'),
                                '67104a06-74a6-4268-a124-269d1b232a28').templates()
    gallery_hashes = {str(x): sha(x) for x in Path('/mnt/wcis-emmc/wcis-face/galleries').rglob('*') if x.is_file()}
    if a.pad_bundle:
        # Validate the immutable bundle before interrupting the camera owner.
        from model_backend.face_pad import UPSTREAM_COMMIT
        manifest = json.loads((a.pad_bundle/'pad-models.json').read_text())
        if manifest.get('upstream_commit') != UPSTREAM_COMMIT or not manifest.get('generated'):
            raise RuntimeError('Unexpected PAD bundle')
        for name, expected in manifest['files_sha256'].items():
            path = (a.pad_bundle/name).resolve()
            if a.pad_bundle.resolve() not in path.parents or sha(path) != expected:
                raise RuntimeError('PAD bundle checksum/path mismatch')
    out.mkdir(parents=True)
    report = dict(schema_version=1, capture_group=uuid.uuid4().hex, ground_truth=a.label,
                  label_source='explicit_human_readiness_response', operator_confirmed_at=a.confirmed_at,
                  boot_id=boot, source_format='SDI_RGB565LE_expanded_by_bit_replication',
                  original_eight_bit_capture=False, security_calibrated=False,
                  samples=[], completed=False, formal_restored=False)
    def save():
        (out/'collection.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    def run(*cmd):
        return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=90).stdout
    def stopped(pid):
        if Path('/proc', str(pid)).exists():
            raise RuntimeError('Previous SDK owner is still running')
        lines = (app/(str(pid)+'-native-stdout.log')).read_text(errors='replace').splitlines()
        last = [json.loads(x.split('WCIS_OWNER_RESULT ', 1)[1]) for x in lines if 'WCIS_OWNER_RESULT ' in x][-1]
        if not (last['sdk_closed'] and not last['camera_pending'] and last['camera_drained'] == 1
                and last['captured'] == last['encoded'] and last['camera_requests'] == last['captured']+1):
            raise RuntimeError('Previous SDK owner did not drain cleanly')
        return last
    owner = None
    temp = None
    restart_safe = False
    try:
        run('systemctl', 'stop', 'wcis-face-photo.service')
        report['formal_stop'] = stopped(control['pid'])
        restart_safe = True
        temp = Path(tempfile.mkdtemp(prefix='wcis-owner-', dir='/dev/shm'))
        restart_safe = False
        owner = CameraOwner(release, binary, digest, temp, seconds=120, native_inputs=True)
        for index in range(a.count):
            with tempfile.TemporaryDirectory(prefix='request-', dir=temp) as request:
                result, _ = owner.infer_camera(Path(request)/'job', gallery, verify=True)
                frame = result['camera_frame']
                if not result['full_source_verification']['full_source_equal']:
                    raise RuntimeError('PL source no longer matches the captured frame')
                sample = out/('%03d' % index)
                sample.mkdir()
                raw = Path(request)/'job/snapshot/source.rgb565'
                if sha(raw) != frame['source_rgb565_sha256']:
                    raise RuntimeError('Captured raw source checksum mismatch')
                shutil.copy2(raw, sample/'source.rgb565')
                pixels = np.fromfile(raw, '<u2').reshape(540, 960)
                red, green, blue = pixels >> 11, (pixels >> 5) & 63, pixels & 31
                image = np.stack(((blue << 3) | (blue >> 2), (green << 2) | (green >> 4),
                                  (red << 3) | (red >> 2)), axis=-1).astype(np.uint8)
                if not cv2.imwrite(str(sample/'source.png'), image):
                    raise RuntimeError('Cannot save lossless frame')
                box = face_box(result['faces'], 960, 540)
                evidence = dict(index=index, ground_truth=a.label, camera_frame=frame,
                                source_png_sha256=sha(sample/'source.png'),
                                source_rgb565_sha256=sha(sample/'source.rgb565'),
                                faces=result['faces'], bbox_xywh=box,
                                pad_eligible=box is not None, bbox_conversion='floor_left_top_ceil_right_bottom_clip',
                                full_source_equal=True, inference_ms=result['elapsed_ms'],
                                sharpness_variance=float(cv2.Laplacian(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()))
                (sample/'sample.json').write_text(json.dumps(evidence, indent=2))
                report['samples'].append(evidence)
                save()
                print('CAPTURED '+json.dumps(dict(index=index, frame_id=frame['frame_id'], faces=len(result['faces']))), flush=True)
            time.sleep(.25)
        owner.close()
        if owner.process.returncode != 0:
            raise RuntimeError('Collection owner exited abnormally')
        report['collection_stop'] = stopped(owner.process.pid)
        restart_safe = True
        # The camera owner has closed its SDK before any separate PAD device opens.
        if a.pad_bundle:
            from model_backend.face_pad_inference import predict
            for sample in report['samples']:
                if not sample['pad_eligible']:
                    continue
                folder = out/('%03d' % sample['index'])
                restart_safe = False
                q = predict(a.pad_bundle, folder/'source.png', sample['bbox_xywh'],
                            sample['camera_frame']['frame_id'], folder/'pad')
                restart_safe = True
                if q['source_sha256'] != sample['source_png_sha256']:
                    raise RuntimeError('PAD frame source mismatch')
                sample['pad_model_result'] = q['model_result']
                sample['pad_preprocessing'] = q['preprocessing']
                save()
        report['completed'] = True
    finally:
        if owner:
            if owner.process.poll() is None:
                owner.close()
            if owner.process.returncode != 0:
                restart_safe = False
        if restart_safe and guard.guard() == boot:
            if {str(x): sha(x) for x in Path('/mnt/wcis-emmc/wcis-face/galleries').rglob('*') if x.is_file()} != gallery_hashes:
                raise RuntimeError('Gallery changed during collection')
            run('systemctl', 'start', 'wcis-face-photo.service')
            report['formal_restored'] = True
            if temp:
                shutil.rmtree(temp)
        save()
    print(json.dumps(dict(completed=report['completed'], formal_restored=report['formal_restored'], out=str(out))), flush=True)


if __name__ == '__main__':
    main()
