"""Bounded static-frame replay through the existing deployed ModelBackend.

Run on the board with the photo service paused. This is a DDR-resident input
test, not a camera, video timing generator, capture writer, or frame scheduler.
The existing PL executable and SDK allocator own the address. No physical
addresses, bitstreams, production configuration, or gallery entries are changed.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', required=True, type=Path)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--photo', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--gallery-store', required=True, type=Path)
    parser.add_argument('--gallery-mount', required=True, type=Path)
    parser.add_argument('--gallery-uuid', required=True)
    parser.add_argument('--replays', type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.replays <= 30:
        parser.error('Use a bounded replay count of 1..30')

    import fcntl
    import cv2
    import numpy as np
    sys.path.insert(0, str(args.app))
    from recognize_photo import recognize
    from model_backend_runtime import ModelBackend
    from persistent_gallery import PersistentGallery
    from pl_preprocess import PLPreprocessor
    from run_photos import decode, save

    args.out.mkdir(parents=True, exist_ok=False)
    marker = args.root.parents[1] / 'hardware-review-required.json'
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if marker.exists() and json.loads(marker.read_text()).get('boot_id') == boot:
        raise RuntimeError('Current boot requires hardware review')
    gallery = PersistentGallery(args.root, args.gallery_store,
                                args.gallery_mount, args.gallery_uuid).templates()
    config = json.loads((args.root / 'models.json').read_text())
    report = dict(passed=False, simulation='static_PL_DDR_replay', boot_id=boot,
                  camera_capture=False, baseline=[], replays=[])
    backend = None
    prep = None
    image_reader = cv2.imread
    source_path = snapshot = None
    lock = None
    try:
        backend = ModelBackend(args.root, args.app / 'wcis_face_cached')

        def baseline(label, measured=True):
            result = recognize(args.root, args.photo, args.out / label, gallery,
                               True, args.app / 'wcis_face_pl_retained', backend)
            if result['face_count'] != 1:
                raise RuntimeError('This bounded replay test requires one face')
            if measured:
                report['baseline'].append(dict(pipeline_ms=result['elapsed_ms'],
                                               host=result['timing']['host']))
            return result

        expected = baseline('baseline-warmup', measured=False)
        for index in range(3):
            baseline('baseline-before-' + str(index))

        lock = (args.root / 'npu.lock').open('a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backend.validate_release()
        image = image_reader(str(args.photo), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        if image is None:
            raise ValueError('Cannot decode the one-time replay seed')
        prep = PLPreprocessor(args.app / 'wcis_face_pl_retained',
                              args.out / 'retained-input', marker, memory_transport=True)
        started = time.monotonic()
        initial, sx, sy = prep.prepare(image)
        report['one_time_prepare_ms'] = (time.monotonic() - started) * 1000
        report['geometry'] = dict(width=image.shape[1], height=image.shape[0])
        del image, initial
        descriptor = json.loads((prep.work / 'job-1' / 'job.json').read_text())
        matrix = np.asarray(descriptor['inverse_q16'], np.float64).reshape(2, 3) / 65536
        content = (descriptor['content_w'], descriptor['content_h'])
        canvas = (descriptor['canvas_w'], descriptor['canvas_h'])
        lease = dict(prep.retained_frame)

        # Make accidental file input or packing fail instead of timing cached PS
        # preparation. Restore the snapshot only for the final full DDR check.
        source_path = prep.source['path']
        snapshot = source_path.with_name('validation-only.rgbx')
        source_path.rename(snapshot)

        def forbidden(*unused, **kwargs):
            raise AssertionError('Replay attempted PS source decode/packing')

        cv2.imread = forbidden
        prep._retain_source = forbidden
        for index in range(args.replays + 1):
            out = args.out / ('replay-' + str(index))
            out.mkdir()
            phases = {}
            started = phase = time.monotonic()
            padded = prep._run(matrix, content, canvas, descriptor['replicate'])
            phases['resize_and_readback_ms'] = (time.monotonic() - phase) * 1000
            request = backend.request(out, lease)
            phase = time.monotonic()
            values, detector = request.forward('yunet', padded.astype(np.float32), 'replay')
            phases['detector_call_ms'] = (time.monotonic() - phase) * 1000
            phase = time.monotonic()
            faces = decode(values, sx, sy, logits=config.get('detector_activation') == 'host_sigmoid')
            phases['decode_ms'] = (time.monotonic() - phase) * 1000
            if len(faces) != 1:
                raise RuntimeError('Replay did not return the baseline single face')
            phase = time.monotonic()
            crop = prep.align_retained(faces[0])
            phases['align_ms'] = (time.monotonic() - phase) * 1000
            phase = time.monotonic()
            if not cv2.imwrite(str(out / 'aligned.png'), crop):
                raise RuntimeError('Cannot save bounded replay evidence')
            tensor = (crop[:, :, ::-1].astype(np.float32) - np.float32(127.5)) / np.float32(127.5)
            phases['tensor_and_aligned_image_ms'] = (time.monotonic() - phase) * 1000
            phase = time.monotonic()
            raw, recognizer = request.forward('mobilefacenet', tensor, 'replay')
            phases['recognizer_call_ms'] = (time.monotonic() - phase) * 1000
            phase = time.monotonic()
            vector = raw[0].astype(np.float64)
            norm = float(np.linalg.norm(vector))
            if vector.shape != (512,) or not np.isfinite(norm) or norm < 1e-10:
                raise RuntimeError('Invalid replay feature')
            vector /= norm
            scores = {name: float(np.dot(vector, np.asarray(template, np.float64)))
                      for name, template in gallery['people'].items()}
            phases['comparison_ms'] = (time.monotonic() - phase) * 1000
            elapsed = (time.monotonic() - started) * 1000
            request.close()
            assert faces == expected['faces'] and vector.tolist() == expected['embedding']
            assert scores == expected['scores']
            for role, result in [('detector', detector), ('recognizer', recognizer)]:
                assert result['frame_preserved'] and result['device_closed']
                assert [v['sha256'] for v in result['outputs']] == [
                    v['sha256'] for v in expected['timing'][role]['outputs']]
            for job in prep.timings[-2:]:
                assert job['frame_lease'] == lease and job['source_uploads'] == 1
                assert not job['source_uploaded_this_command'] and job['ddr_frame_reused']
            assert not source_path.exists() and prep.source_builds == 1
            row = dict(sequence=index, pipeline_ms=elapsed, host=phases,
                       npu_bit_exact=True, features_and_scores_exact=True,
                       source_uploaded=False, source_file_absent=True)
            if index == 0:
                report['warmup_replay'] = row
            else:
                report['replays'].append(row)
            save(out / 'verification.json', row)
            print('DDR replay', index, round(elapsed, 1), 'ms PASS', flush=True)

        snapshot.rename(source_path)
        report['full_source_equal'] = prep.verify_retained_source()['full_source_equal']
        report['source_uploads_total'] = 1
        report['source_builds_total'] = prep.source_builds
        report['single_unchanged_frame_lease'] = True
        prep.close()
        prep = None
        lock.close()
        lock = None
        cv2.imread = image_reader
        for index in range(3):
            baseline('baseline-after-' + str(index))
        report['baseline_median_ms'] = statistics.median(v['pipeline_ms'] for v in report['baseline'])
        report['replay_median_ms'] = statistics.median(v['pipeline_ms'] for v in report['replays'])
        report['replay_range_ms'] = [min(v['pipeline_ms'] for v in report['replays']),
                                     max(v['pipeline_ms'] for v in report['replays'])]
        report['passed'] = True
    finally:
        cv2.imread = image_reader
        try:
            if prep is not None:
                prep.close()
        finally:
            try:
                if backend is not None:
                    backend.close()
            finally:
                if lock is not None:
                    lock.close()
                save(args.out / 'replay-report.json', report)

    print(json.dumps({key: report[key] for key in ('passed', 'baseline_median_ms',
          'replay_median_ms', 'replay_range_ms', 'source_uploads_total')}), flush=True)


if __name__ == '__main__':
    main()
