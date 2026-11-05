"""Read-only feature comparison for enrollment review.

This module supplies measurements, not admission policy: it never decides to
register, reject, merge, rename or update anyone. No filesystem mutation, model
execution, frontend or scheduling is performed by compare_features().
"""
import argparse
import json
from pathlib import Path

import numpy as np

from face_history.store import normalized


def compare_features(embedding, gallery, pipeline_id, target_name=None, top_k=5):
    """Return closest sample/center scores, keeping target and alternatives apart.

    Max sample similarity retains evidence from a person's different views;
    center similarity follows the existing gallery's mean-then-normalize rule.
    Neither score is a probability or a calibrated registration decision.
    """
    if not isinstance(pipeline_id, str) or not pipeline_id.strip() or gallery.get('pipeline_id') != pipeline_id:
        raise ValueError('Feature pipeline mismatch')
    if gallery.get('schema_version') not in (1, 2):
        raise ValueError('Unsupported enrollment gallery schema')
    if type(top_k) is not int or not 1 <= top_k <= 100:
        raise ValueError('top_k must be in 1..100')
    if target_name is not None:
        if not isinstance(target_name, str) or not target_name.strip():
            raise ValueError('Target name must be nonempty')
        target_name = target_name.strip()
    query = normalized(embedding).astype(np.float64)
    query /= np.linalg.norm(query)
    people = gallery.get('people')
    if not isinstance(people, list) or len(people) > 100:
        raise ValueError('Expected a gallery with at most 100 people')
    seen_names, seen_ids, scores = set(), set(), []
    sample_count = 0
    for person in people:
        name, person_id = person.get('name'), person.get('id')
        if (not isinstance(name, str) or not name.strip() or name != name.strip()
                or not isinstance(person_id, str) or not person_id):
            raise ValueError('Invalid gallery person')
        if name in seen_names or person_id in seen_ids:
            raise ValueError('Ambiguous duplicate gallery name or person id')
        seen_names.add(name)
        seen_ids.add(person_id)
        samples = person.get('photos')
        if not isinstance(samples, list) or not 1 <= len(samples) <= 30:
            raise ValueError('Expected 1..30 features per person')
        vectors, sample_ids = [], []
        for sample in samples:
            sample_id = sample.get('id')
            if not isinstance(sample_id, str) or not sample_id or sample_id in sample_ids:
                raise ValueError('Invalid or repeated sample id')
            sample_ids.append(sample_id)
            value = np.asarray(sample.get('embedding'), dtype=np.float64)
            if (value.shape != (512,) or not np.isfinite(value).all()
                    or abs(float(np.linalg.norm(value)) - 1.0) > 0.0002):
                raise ValueError('Invalid normalized gallery feature')
            vectors.append(value / np.linalg.norm(value))
        matrix = np.stack(vectors)
        center = matrix.mean(axis=0)
        norm = float(np.linalg.norm(center))
        if norm < 1e-10:
            raise ValueError('Person features cancel; center is undefined')
        similarities = np.clip(matrix @ query, -1.0, 1.0)
        best = int(np.argmax(similarities))
        scores.append(dict(person_id=person_id, name=name, sample_count=len(samples),
            best_sample_id=sample_ids[best], best_sample_similarity=float(similarities[best]),
            center_similarity=float(np.clip(np.dot(center / norm, query), -1.0, 1.0))))
        sample_count += len(samples)
    scores.sort(key=lambda row: (-row['best_sample_similarity'], row['person_id']))
    target = next((row for row in scores if row['name'] == target_name), None)
    alternatives = [row for row in scores if row['name'] != target_name]
    gap = (alternatives[0]['best_sample_similarity'] - target['best_sample_similarity']
           if target is not None and alternatives else None)
    return dict(pipeline_id=pipeline_id, metric='normalized_cosine',
        ranking='maximum_sample_similarity_then_person_id',
        gallery_revision=gallery.get('revision'), compared_people=len(people),
        compared_samples=sample_count, target_name=target_name,
        target_found=target is not None, target=target,
        alternatives=alternatives[:top_k], alternative_minus_target=gap,
        admission_decision=None, calibrated=False, gallery_modified=False)


def _read(path):
    path = Path(path)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Input JSON exceeds 64 MiB')
    return json.loads(path.read_text(encoding='utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gallery', required=True, type=Path, help='Explicit enrollment JSON snapshot; read only')
    parser.add_argument('--probe', required=True, type=Path, help='JSON with pipeline_id and one embedding')
    parser.add_argument('--target-name', help='Optional existing name whose additional sample is being compared')
    parser.add_argument('--top-k', type=int, default=5)
    args = parser.parse_args(argv)
    try:
        value = _read(args.probe)
        if 'entry' in value:
            value = value['entry']
        if 'result' in value:
            value = value['result']
        if value.get('face_count', 1) != 1:
            raise ValueError('Comparison probe requires exactly one face')
        embedding = value.get('embedding')
        if embedding is None:
            people = value.get('identities', [])
            if len(people) != 1:
                raise ValueError('Probe must contain exactly one extracted feature')
            embedding = people[0]['embedding']
        report = compare_features(embedding, _read(args.gallery), value['pipeline_id'],
                                  args.target_name, args.top_k)
        print(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        import sys
        print(json.dumps(dict(status='failed', error=str(error)), ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
