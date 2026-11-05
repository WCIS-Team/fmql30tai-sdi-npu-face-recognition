"""File/video CLI for quality review, explicit result import and face search."""
import argparse
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import signal
import sqlite3
import tempfile

os.environ.setdefault('OPENCV_IO_MAX_IMAGE_PIXELS', '16000000')
import cv2

from .quality import QualityPolicy, face_quality, select_best
from .records import file_sha, make_record, query_face, unwrap_result
from .store import HistoryStore


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('JSON input exceeds 16 MiB')
    return json.loads(path.read_text(encoding='utf-8'))


def read_image(path):
    image = cv2.imread(str(path), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    if image is None or image.size == 0 or image.shape[0] * image.shape[1] > 16000000:
        raise ValueError('Unreadable image or image exceeds 16 megapixels')
    return image


def save_json(path, value):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n'
    if path is not None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=path.name + '.', dir=str(path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, str(path))
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    return raw


def source_for(path, kind, source_id=None):
    path = Path(path).resolve(strict=True)
    digest = file_sha(path)
    return dict(id=source_id or (kind + ':' + digest), kind=kind,
                uri=str(path), sha256=digest)


def policy_for(args):
    return QualityPolicy(**read_json(args.policy)) if args.policy else QualityPolicy()


def summary(record):
    # Feature vectors stay in the explicitly chosen DB, not stdout or summaries.
    return dict(source=record['source'], sequence=record['sequence'], pts_ms=record['pts_ms'],
        detected_face_count=record['detected_face_count'], skipped_face_count=record['skipped_face_count'],
        faces=[{k: v for k, v in p.items() if k != 'embedding'} for p in record['faces']])


def frame_inputs(args):
    if args.image:
        yield 0, 0.0, read_image(args.image), 'still_image'
        return
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise ValueError('Cannot open video')
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError('Video requires a valid nominal frame rate')
        next_pts, emitted, last_pts = 0.0, 0, -1.0
        for sequence in range(args.max_decoded):
            ok, image = cap.read()
            if not ok:
                break
            if image.shape[0] * image.shape[1] > 16000000:
                raise ValueError('Video frame exceeds 16 megapixels')
            pts = float(cap.get(cv2.CAP_PROP_POS_MSEC))
            clock = 'decoder_pts'
            if not math.isfinite(pts) or pts < 0 or (sequence > 0 and pts <= last_pts):
                pts = sequence * 1000.0 / fps
                clock = 'estimated_nominal_fps'
            if pts <= last_pts:
                raise ValueError('Video timestamps are not monotonic')
            last_pts = pts
            if pts + 1e-6 < next_pts:
                continue
            yield sequence, pts, image, clock
            emitted += 1
            if emitted >= args.max_frames:
                break
            next_pts = pts + args.sample_ms
    finally:
        cap.release()


def run(args, stopping=lambda: False):
    policy = policy_for(args)
    if args.command == 'review':
        image = read_image(args.image)
        result = unwrap_result(read_json(args.result))
        faces = result.get('faces', [])
        if not isinstance(faces, list) or len(faces) > 100:
            raise ValueError('Expected at most 100 detections')
        return dict(policy=asdict(policy), policy_id=policy.policy_id,
            faces=[dict(face_index=i, box=f['box'], quality=face_quality(image, f, policy))
                   for i, f in enumerate(faces)], calibrated=False)
    if args.command == 'best':
        values = read_json(args.candidates)
        if not isinstance(values, list) or not 1 <= len(values) <= 300:
            raise ValueError('Supply 1..300 explicitly same-person candidates')
        policies = {p['quality']['policy_id'] for p in values}
        if len(policies) != 1:
            raise ValueError('Candidate quality policies differ')
        return dict(best=select_best(values), same_person_group_supplied_by_caller=True)
    if args.command == 'import':
        manifest = Path(args.manifest).resolve(strict=True)
        entries = read_json(manifest)
        if not isinstance(entries, list) or not 1 <= len(entries) <= 300:
            raise ValueError('Import manifest requires 1..300 frames')
        reports = []
        store = None
        try:
            for entry in entries:
                image_path = (manifest.parent / entry['image']).resolve(strict=True)
                result_path = (manifest.parent / entry['result']).resolve(strict=True)
                result = unwrap_result(read_json(result_path))
                # Existing NPU photo evidence hashes the exact compressed input.
                # If absent, explicit trusted import cannot prove image linkage.
                digest = file_sha(image_path)
                if result.get('photo_sha256') != digest:
                    raise ValueError('Imported result is not bound to this image SHA256')
                source = entry.get('source') or source_for(image_path, 'image')
                record = make_record(read_image(image_path), result, source,
                    entry.get('sequence', 0), entry.get('pts_ms', 0), policy)
                if store is None:
                    store = HistoryStore(args.db, record['pipeline_id'], args.capacity)
                report = summary(record)
                report['index'] = store.add_frame(record)
                reports.append(report)
            return dict(frames=reports, indexed_faces=store.count(), pipeline_id=store.pipeline_id,
                        extraction='imported_existing_result', provenance='caller_trusted')
        finally:
            if store is not None:
                store.close()
    if args.command == 'search-result':
        result = unwrap_result(read_json(args.result))
        digest = file_sha(args.image)
        if result.get('photo_sha256') != digest:
            raise ValueError('Query result/image SHA256 mismatch')
        record = make_record(read_image(args.image), result,
                             source_for(args.image, 'image'), policy=policy)
        return search_record(args, record)
    # Explicit board extraction only. Nothing silently switches to CPU models.
    from .extractor import NPUExtractor
    source = source_for(args.image or args.video, 'image' if args.image else 'video',
                        getattr(args, 'source_id', None))
    with NPUExtractor(args.backend_config, args.work) as extractor:
        if args.command == 'search':
            if stopping():
                return dict(status='stopped', inference_started=False)
            image = read_image(args.image)
            record = make_record(image, extractor.extract(image), source, policy=policy)
            return search_record(args, record)
        reports = []
        with HistoryStore(args.db, extractor.pipeline_id, args.capacity) as store:
            for sequence, pts, image, clock in frame_inputs(args):
                if stopping():
                    break
                record = make_record(image, extractor.extract(image), source, sequence, pts, policy)
                report = summary(record)
                report.update(index=store.add_frame(record), timestamp_source=clock)
                reports.append(report)
                print(json.dumps(dict(event='indexed', sequence=sequence, **report['index'])), flush=True)
                if args.out:
                    save_json(args.out, dict(status='running', frames=reports, indexed_faces=store.count()))
            return dict(status='stopped' if stopping() else 'complete', pipeline_id=extractor.pipeline_id, frames=reports,
                        indexed_faces=store.count(), extraction='existing_PL_NPU',
                        bounded_offline_input=True, continuous_camera=False)


def search_record(args, record):
    face = query_face(record, args.face_index)
    with HistoryStore(args.db, record['pipeline_id'], readonly=True) as store:
        result = store.search(face['embedding'], record['pipeline_id'], args.threshold,
            args.top_k, args.source_id, args.start_ms, args.end_ms)
    result['query_face_index'] = face['face_index']
    result['query_quality'] = face['quality']
    return result


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest='command', required=True)
    for name in ('review', 'best', 'import', 'index', 'search', 'search-result'):
        p = commands.add_parser(name)
        p.add_argument('--policy', type=Path, help='Optional JSON quality thresholds; defaults are provisional')
        p.add_argument('--out', type=Path, help='Summary JSON, excludes feature vectors')
        if name == 'best':
            p.add_argument('--candidates', type=Path, required=True)
            continue
        if name in ('review', 'search-result'):
            p.add_argument('--result', type=Path, required=True)
        if name in ('review', 'search', 'search-result'):
            p.add_argument('--image', type=Path, required=True)
        if name != 'review':
            p.add_argument('--db', type=Path, required=True)
        if name == 'import':
            p.add_argument('--manifest', type=Path, required=True)
        if name in ('import', 'index'):
            p.add_argument('--capacity', type=int, default=10000)
        if name in ('search', 'search-result'):
            p.add_argument('--threshold', type=float, required=True, help='Cosine cutoff, not probability; calibrate independently')
            p.add_argument('--top-k', type=int, default=10)
            p.add_argument('--face-index', type=int)
            p.add_argument('--source-id')
            p.add_argument('--start-ms', type=float)
            p.add_argument('--end-ms', type=float)
        if name in ('index', 'search'):
            p.add_argument('--backend-config', type=Path, required=True)
            p.add_argument('--work', type=Path, required=True, help='Private temporary inference directory')
        if name == 'index':
            inputs = p.add_mutually_exclusive_group(required=True)
            inputs.add_argument('--image', type=Path)
            inputs.add_argument('--video', type=Path)
            p.add_argument('--source-id')
            p.add_argument('--sample-ms', type=float, default=1000)
            p.add_argument('--max-frames', type=int, default=30)
            p.add_argument('--max-decoded', type=int, default=10000)
    return cli


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    if args.command == 'index' and (not 1 <= args.max_frames <= 300 or
            not 1 <= args.max_decoded <= 100000 or not math.isfinite(args.sample_ms) or args.sample_ms < 0):
        cli.error('Use 1..300 samples, 1..100000 decoded frames, and nonnegative finite sample-ms')
    if args.command in ('search', 'search-result'):
        if not math.isfinite(args.threshold) or not -1 <= args.threshold <= 1 or not 1 <= args.top_k <= 100:
            cli.error('Use an explicit threshold in [-1,1] and top-k in 1..100')
        if any(v is not None and (not math.isfinite(v) or v < 0) for v in (args.start_ms, args.end_ms)):
            cli.error('Time filters must be finite and nonnegative')
        if args.start_ms is not None and args.end_ms is not None and args.start_ms > args.end_ms:
            cli.error('Invalid time interval')
        if not args.db.is_file():
            cli.error('Search database does not exist')
    if args.out:
        for name in ('db', 'image', 'video', 'result', 'manifest', 'candidates', 'policy', 'backend_config'):
            other = getattr(args, name, None)
            if other is not None and Path(other).resolve() == args.out.resolve():
                cli.error('Summary output must not overwrite an input or database')
    stopped = [False]
    old_signals = {}
    if args.command in ('index', 'search'):
        # Signal Python only: finish the in-flight synchronous SDK request and
        # close normally. Never forward terminal interrupts to DMA workers.
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_signals[sig] = signal.signal(sig, lambda *_: stopped.__setitem__(0, True))
    try:
        result = run(args, stopping=lambda: stopped[0])
        print(save_json(args.out, result), end='', flush=True)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        # Deliberately report failure; no recompile, CPU fallback, retry or kill.
        import sys
        print(json.dumps(dict(status='failed', error_type=type(error).__name__,
                              error=str(error)), ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        for sig, handler in old_signals.items():
            signal.signal(sig, handler)
    return 0
