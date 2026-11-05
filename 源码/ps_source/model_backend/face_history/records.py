"""Adapt existing multi-face results; no second detector or feature extractor."""
import hashlib
from pathlib import Path

from .quality import face_quality
from .store import normalized


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def unwrap_result(value):
    if 'entry' in value:
        value = value['entry']
    if 'result' in value:
        value = value['result']
    return value


def make_record(image, result, source, sequence=0, pts_ms=0, policy=None):
    result = unwrap_result(result)
    pipeline = result.get('pipeline_id')
    if not isinstance(pipeline, str) or not pipeline.strip():
        raise ValueError('Inference result must declare pipeline_id')
    people = result.get('identities')
    if people is None:
        raise ValueError('Use the multi-face backend with return_embedding=True')
    if not isinstance(people, list) or len(people) > 4:
        raise ValueError('Expected at most four processed identities')
    faces = result.get('faces', [])
    output, seen = [], set()
    for person in people:
        index = person['face_index']
        if type(index) is not int or index < 0 or index >= len(faces) or index in seen:
            raise ValueError('Invalid face/result association')
        seen.add(index)
        face = person['face']
        if face != faces[index]:
            raise ValueError('Identity points to a different detection')
        # Recheck before any index write; missing, NaN and zero vectors fail.
        embedding = normalized(person['embedding']).tolist()
        output.append(dict(face_index=index, box=face['box'],
                           embedding=embedding, quality=face_quality(image, face, policy)))
    return dict(pipeline_id=pipeline, source=dict(source), sequence=sequence,
                pts_ms=pts_ms, faces=output,
                detected_face_count=result.get('face_count', len(faces)),
                skipped_face_count=result.get('skipped_face_count', 0))


def query_face(record, face_index=None):
    if face_index is None:
        if record['detected_face_count'] != 1 or len(record['faces']) != 1:
            raise ValueError('Query must contain one face, or explicitly select --face-index')
        face = record['faces'][0]
    else:
        selected = [p for p in record['faces'] if p['face_index'] == face_index]
        if len(selected) != 1:
            raise ValueError('Selected query face was not extracted')
        face = selected[0]
    if not face['quality']['accepted']:
        raise ValueError('Query quality rejected: ' + ','.join(face['quality']['reasons']))
    return face
