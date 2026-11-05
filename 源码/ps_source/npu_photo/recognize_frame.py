"""Shared inference for an already prepared frame; no input decoding or capture.

The caller owns the hardware lock and the source frame through alignment.
File input and DDR replay use the same deployed detection/alignment/feature
logic. No camera queue, capture driver, or gallery mutation is implemented here.
"""
import time
from pathlib import Path
import cv2
import numpy as np
from run_photos import Runner, decode, align, save
from native_forward import NativeForward

MAX_RECOGNIZED_FACES = 4


def infer_prepared(padded, sx, sy, *, root, out, config, evidence, gallery,
                   preprocessor=None, model_backend=None, image=None,
                   return_embedding=False, identity=None, host=None, start=None,
                   request_started=None, job_start=0, save_aligned=True,
                   require_single_face=False):
    root, out = Path(root), Path(out)
    start = time.monotonic() if start is None else start
    request_started = start if request_started is None else request_started
    host = {} if host is None else host
    runner = None
    def elapsed(since):return (time.monotonic() - since) * 1000
    try:
        phase = time.monotonic()
        runner = (model_backend.request(out, preprocessor.retained_frame if preprocessor else None)
                  if model_backend is not None else Runner(root, out))
        host['runner_initialize_ms'] = elapsed(phase);phase = time.monotonic()
        values, detector = runner.forward('yunet', padded if isinstance(padded,NativeForward) else padded.astype(np.float32), 'photo')
        host['detector_call_ms'] = elapsed(phase);phase = time.monotonic()
        faces = decode(values, sx, sy, logits=config.get('detector_activation') == 'host_sigmoid')
        host['decode_ms'] = elapsed(phase)
        result = dict(status='no_face' if not faces else 'multiple_faces', faces=faces,
                      face_count=len(faces),
                      identities=[], processed_face_count=0, skipped_face_count=0,
                      face_limit=MAX_RECOGNIZED_FACES,
                      backend='zg330_npu_pl_and_host' if preprocessor else 'zg330_npu_and_host',
                      preprocessing_backend='FAC1_customop_PL' if preprocessor else 'PS_OpenCV',
                      pipeline_id=gallery['pipeline_id'], threshold=evidence['threshold'],
                      timing={'detector': detector})
        result.update(identity or {})
        # Keep detector ordering/geometry intact. An explicit index binds each
        # identity to its detection even when only the four best scores fit.
        indices = sorted(range(len(faces)), key=lambda i: (-faces[i]['score'], i))
        selected = [] if require_single_face and len(faces) != 1 else indices[:MAX_RECOGNIZED_FACES]
        for index in selected:
            face = faces[index]
            single = len(faces) == 1
            stem = 'photo' if single else 'photo-face-' + str(index)
            face_host = host if single else {}
            phase = time.monotonic()
            crop = preprocessor.align_retained(face) if preprocessor else align(image, face)
            face_host['align_ms'] = elapsed(phase);phase = time.monotonic()
            aligned = None
            if save_aligned:
                aligned = str(out / ('aligned.png' if single else 'aligned-' + str(index) + '.png'))
                pixels=crop.image_bgr if isinstance(crop,NativeForward) else crop
                if pixels is None or not cv2.imwrite(aligned, pixels):raise RuntimeError('Cannot save aligned frame')
            tensor = crop if isinstance(crop,NativeForward) else (crop[:, :, ::-1].astype(np.float32) - np.float32(127.5)) / np.float32(127.5)
            face_host['tensor_and_aligned_image_ms'] = elapsed(phase);phase = time.monotonic()
            raw, recognizer = runner.forward('mobilefacenet', tensor, stem)
            face_host['recognizer_call_ms'] = elapsed(phase);phase = time.monotonic()
            vector = raw[0].astype(np.float64)
            norm = float(np.linalg.norm(vector))
            if len(vector) != 512 or not np.isfinite(norm) or norm < 1e-10:
                raise RuntimeError('Invalid feature vector')
            vector /= norm
            scores = {name:float(np.dot(vector, np.asarray(template, np.float64)))
                      for name, template in gallery['people'].items()}
            ranking = sorted(scores.items(), key=lambda item:item[1], reverse=True)
            name, score = ranking[0] if ranking else ('未知', None)
            accepted = score is not None and score >= evidence['threshold'] and (
                len(ranking) < 2 or abs(score - ranking[1][1]) > 1e-6)
            person = dict(face_index=index, face=face,
                          status='recognized' if accepted else 'unknown',
                          name=name if accepted else '未知', similarity=score,
                          scores=scores, aligned=aligned,
                          timing={'recognizer': recognizer, 'host': face_host.copy()})
            if return_embedding:person['embedding'] = vector.tolist()
            face_host['comparison_ms'] = elapsed(phase)
            person['timing']['host']['comparison_ms'] = face_host['comparison_ms']
            result['identities'].append(person)
            if single:
                # Existing enrollment and single-photo clients retain their API.
                for key in ('status', 'name', 'similarity', 'scores', 'face', 'aligned'):
                    result[key] = person[key]
                result['timing']['recognizer'] = recognizer
                if return_embedding:result['embedding'] = person['embedding']
        result['processed_face_count'] = len(result['identities'])
        result['skipped_face_count'] = len(faces) - len(selected)
        result['selection_policy'] = 'highest_detection_score'
        if len(faces) > 1 and not require_single_face:
            result['status'] = 'multi_face'
        if preprocessor:result['timing']['preprocessing'] = preprocessor.timings[job_start:]
        result['timing']['host'] = host
        result['model_lifecycle'] = ('resident_process_per_model' if model_backend is not None
                                     else 'isolated_process_per_request')
        result['elapsed_ms'] = elapsed(start)
        result['request_elapsed_ms'] = elapsed(request_started)
        save(out / 'result.json', result)
        return result
    finally:
        if runner is not None:runner.close()
