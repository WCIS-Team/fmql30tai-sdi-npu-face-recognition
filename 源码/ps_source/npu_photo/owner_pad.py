"""Same-frame PAD evidence through the existing exclusive camera owner.

No second SDK process, gallery writes, or access-control decisions. Cropping
reuses the pinned MiniFASNet PS reference until the PL adapter is deployed.
"""
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
from model_backend.face_pad import MODELS, UPSTREAM_COMMIT, prepare_reference, combine_logits


def checked_bundle(bundle):
    bundle = Path(bundle).resolve()
    manifest_path = bundle / 'pad-models.json'
    manifest = json.loads(manifest_path.read_text())
    roles = {m[0] for m in MODELS}
    if (manifest.get('generated') is not True or manifest.get('upstream_commit') != UPSTREAM_COMMIT
            or set(manifest.get('models', {})) != roles):
        raise ValueError('Expected the pinned complete PAD model bundle')
    files = {manifest_path}
    for role in roles:
        for key in ('json', 'raw'):
            name = manifest['models'][role][key]
            path = (bundle / name).resolve()
            if (bundle not in path.parents or name not in manifest.get('files_sha256', {})
                    or hashlib.sha256(path.read_bytes()).hexdigest() != manifest['files_sha256'][name]):
                raise ValueError('PAD model checksum/path mismatch')
            files.add(path)
    return manifest_path, manifest, files


MAX_PAD_FACES = 4


def _rgb565_table():
    # OpenCV's 565 conversion zero-fills the low bits; restore the exact
    # original bit-replication rule using its native per-channel lookup.
    values = np.arange(256, dtype=np.uint8)
    table = np.empty((256, 1, 3), dtype=np.uint8)
    table[:, 0, 0] = values | (values >> 5)
    table[:, 0, 1] = values | (values >> 6)
    table[:, 0, 2] = values | (values >> 5)
    table.setflags(write=False)
    return table


_RGB565_EXPAND_LUT = _rgb565_table()


def expand_rgb565(packed):
    """Exact bit replication through native uint8 conversion and lookup."""
    import cv2
    image = cv2.cvtColor(packed.view(np.uint8).reshape(*packed.shape, 2), cv2.COLOR_BGR5652BGR)
    return cv2.LUT(image, _RGB565_EXPAND_LUT)


def face_box(face, width, height):
    box = face['box']
    if len(box) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in box):
        raise ValueError('Invalid same-frame face box')
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        raise ValueError('Empty or reversed face box')
    left, top = max(0, math.floor(x0)), max(0, math.floor(y0))
    right, bottom = min(width, math.ceil(x1)), min(height, math.ceil(y1))
    if right <= left or bottom <= top:
        raise ValueError('Face box outside source frame')
    return [left, top, right-left, bottom-top]


def evaluate(owner, preprocessor, result, raw_path, frame, out, *, max_age=3.0, clock=time.monotonic):
    """Evaluate up to four identity-selected faces under the same frame lease.

    Deadline is a result-freshness bound, not a DMA cancellation mechanism.
    Hardware errors propagate to existing owner quarantine; never reuse a prior
    result. RGB565 is expanded by bit replication, as in the saved board probe.
    """
    started = time.perf_counter()
    if isinstance(max_age, bool) or not math.isfinite(max_age) or max_age <= 0:
        raise ValueError('PAD freshness bound must be positive and finite')
    lease = preprocessor.retained_frame
    if (lease is None or lease['frame_id'] != frame['frame_id'] or lease['boot_id'] != owner.boot
            or frame['boot_id'] != owner.boot or frame['pid'] != owner.process.pid
            or frame['session'] != owner.work.name[len('wcis-owner-'):]
            or result.get('camera_frame') != frame or result.get('boot_id') != owner.boot
            or result.get('source_rgb565_sha256') != frame['source_rgb565_sha256']):
        raise RuntimeError('PAD identity/source frame binding mismatch')
    if (frame['width'], frame['height'], frame.get('input_pixel_format')) != (960, 540, 'RGB565LE'):
        raise ValueError('PAD expects the verified RGB565 camera contract')
    captured = frame['captured_at']
    if isinstance(captured, bool) or not isinstance(captured, (int, float)) or not math.isfinite(captured):
        raise ValueError('Invalid camera capture timestamp')
    evidence = dict(status='not_evaluated', security_calibrated=False, authorization='not_evaluated',
                    boot_id=owner.boot, session=frame['session'], frame_id=frame['frame_id'],
                    source_rgb565_sha256=frame['source_rgb565_sha256'], frame_token=lease['frame_token'],
                    owner_pid=owner.process.pid, max_age_ms=max_age*1000,
                    preprocessing='PS_OpenCV_RGB565_bit_replication', original_eight_bit_capture=False,
                    upstream_commit=UPSTREAM_COMMIT, face_limit=MAX_PAD_FACES,
                    faces=[], processed_face_count=0, evaluated_face_count=0,
                    skipped_face_count=0,
                    aggregate_timing_ms=dict(source_read_decode=0., crop_resize=0.,
                                             model_calls=0., source_verify=0.))
    def fresh():
        age = clock()-captured
        evidence['frame_age_ms'] = age*1000
        return 0 <= age <= max_age
    faces = result['faces']
    if result['face_count'] != len(faces):
        raise RuntimeError('PAD detection count mismatch')
    if not faces:
        return dict(evidence, status='not_applicable' if fresh() else 'stale', reason='no_face')
    people = result['identities']
    if len(people) != min(len(faces), MAX_PAD_FACES):
        raise RuntimeError('PAD identity selection count mismatch')
    selected = {}
    for person in people:
        index = person['face_index']
        if (type(index) is not int or not 0 <= index < len(faces) or index in selected
                or person['face'] != faces[index]):
            raise RuntimeError('PAD identity does not belong to the detected face')
        selected[index] = person
    for index, face in enumerate(faces):
        item = dict(face_index=index, bbox_xywh=face_box(face, 960, 540),
                    status='not_evaluated', reason='face_limit' if index not in selected else 'pending',
                    identity_status=selected[index]['status'] if index in selected else 'not_evaluated')
        evidence['faces'].append(item)

    def finish():
        current = fresh()
        for item in evidence['faces']:
            item['frame_age_ms'] = evidence['frame_age_ms']
            item['max_age_ms'] = max_age*1000
            if not current and item.get('reason') != 'face_limit':
                item.update(status='stale', reason='frame_expired')
        evidence['evaluated_face_count'] = sum(x['status'] in ('model_live', 'model_non_live', 'inconclusive')
                                              for x in evidence['faces'])
        evidence['skipped_face_count'] = sum(x['status'] == 'not_evaluated' for x in evidence['faces'])
        evidence['aggregate_timing_ms']['total'] = (time.perf_counter()-started)*1000
        if len(faces) == 1:
            # Preserve the old single-face fields; the list is authoritative for groups.
            evidence.update(evidence['faces'][0])
        else:
            evidence['status'] = ('stale' if not current else 'evaluated'
                                  if evidence['evaluated_face_count'] == len(faces) else 'partial')
        return evidence

    if not fresh():
        return finish()
    phase = time.perf_counter()
    raw = Path(raw_path).read_bytes()
    if len(raw) != 960*540*2 or hashlib.sha256(raw).hexdigest() != frame['source_rgb565_sha256']:
        raise RuntimeError('PAD original camera bytes changed')
    packed = np.frombuffer(raw, dtype='<u2').reshape(540, 960)
    image = expand_rgb565(packed)
    evidence['aggregate_timing_ms']['source_read_decode'] = (time.perf_counter()-phase)*1000
    for index in selected:
        item = evidence['faces'][index]
        if not fresh():
            break
        phase = time.perf_counter()
        tensors = prepare_reference(image, item['bbox_xywh'])
        item['preprocessing_ms'] = (time.perf_counter()-phase)*1000
        evidence['aggregate_timing_ms']['crop_resize'] += item['preprocessing_ms']
        logits, receipts = {}, {}
        item['model_call_ms'] = 0.
        for role, _, _ in MODELS:
            if not fresh():
                break
            phase = time.perf_counter()
            stem = 'pad' if len(faces) == 1 else 'pad-face-'+str(index)
            values, receipt = owner.forward(role, tensors[role], Path(out), stem, retained_frame=lease)
            call_ms = (time.perf_counter()-phase)*1000
            item['model_call_ms'] += call_ms
            evidence['aggregate_timing_ms']['model_calls'] += call_ms
            if (receipt.get('role') != role or receipt.get('single_owner') is not True
                    or receipt.get('frame_id') != lease['frame_id'] or receipt.get('frame_token') != lease['frame_token']
                    or receipt.get('worker_pid') != owner.process.pid or receipt.get('frame_preserved') is not True
                    or receipt.get('npu_bound_ops', 0) < 1 or receipt.get('device_closed') is not False):
                raise RuntimeError('PAD model completion binding mismatch')
            if len(values) != 1:
                raise RuntimeError('PAD model output count mismatch')
            logits[role] = np.asarray(values[0]).tolist()
            receipts[role] = receipt
        item.update(models=logits, timing=receipts)
        if len(logits) != len(MODELS):
            break
        combined = combine_logits(logits)
        scores = combined['scores']
        tied = scores.count(max(scores)) != 1
        item.update(status='inconclusive' if tied else 'model_live'
                    if combined['model_predicts_live'] else 'model_non_live', model_result=combined)
        item.pop('reason')
        evidence['processed_face_count'] += 1
    # Full comparison catches corruption beyond the allocation guard bytes.
    phase = time.perf_counter()
    verification = preprocessor.verify_retained_source()
    if verification.get('full_source_equal') is not True:
        raise RuntimeError('PAD retained source verification failed')
    evidence['aggregate_timing_ms']['source_verify'] = (time.perf_counter()-phase)*1000
    evidence['full_source_equal'] = True
    return finish()
