"""SQLite is authoritative; bounded exhaustive FP32 normalized inner product."""
import heapq
import json
import math
from pathlib import Path
import sqlite3

import numpy as np

DIMENSION = 512
SCHEMA = 'face-history-v1'


def normalized(vector):
    value = np.asarray(vector, dtype=np.float64)
    if value.shape != (DIMENSION,) or not np.isfinite(value).all():
        raise ValueError('Expected one finite 512-dimensional feature')
    norm = float(np.linalg.norm(value))
    if not math.isfinite(norm) or norm < 1e-10:
        raise ValueError('Invalid feature norm')
    return np.asarray(value / norm, dtype='<f4')


class HistoryStore:
    def __init__(self, path, pipeline_id=None, capacity=10000, readonly=False):
        self.path = Path(path)
        if type(capacity) is not int or not 1 <= capacity <= 100000:
            raise ValueError('Capacity must be in 1..100000')
        self.readonly = readonly
        if readonly:
            self.connection = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(str(self.path), timeout=5)
        try:
            self.connection.execute('PRAGMA foreign_keys=ON')
            self.connection.execute('PRAGMA busy_timeout=5000')
            if not readonly:
                self.connection.execute('PRAGMA journal_mode=WAL')
                self.connection.execute('PRAGMA synchronous=FULL')
                with self.connection:
                    self.connection.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
                    if not self.connection.execute('SELECT 1 FROM metadata LIMIT 1').fetchone():
                        if not isinstance(pipeline_id, str) or not pipeline_id.strip():
                            raise ValueError('New history requires an explicit pipeline_id')
                        self.connection.executemany('INSERT INTO metadata VALUES (?,?)',
                            [('schema', SCHEMA), ('pipeline_id', pipeline_id),
                             ('dimension', str(DIMENSION)), ('capacity', str(capacity))])
                    self.connection.execute('''CREATE TABLE IF NOT EXISTS faces (
                        id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, source_kind TEXT NOT NULL,
                        source_uri TEXT NOT NULL, source_sha256 TEXT NOT NULL,
                        sequence INTEGER NOT NULL, pts_ms REAL NOT NULL, face_index INTEGER NOT NULL,
                        box TEXT NOT NULL, quality TEXT NOT NULL, vector BLOB NOT NULL,
                        UNIQUE(source_id, sequence, face_index), CHECK(length(vector)=2048))''')
                    self.connection.execute('CREATE INDEX IF NOT EXISTS source_time ON faces(source_id,pts_ms)')
            meta = dict(self.connection.execute('SELECT key,value FROM metadata'))
            if meta.get('schema') != SCHEMA or meta.get('dimension') != str(DIMENSION):
                raise ValueError('Unsupported history schema or dimension')
            self.pipeline_id = meta['pipeline_id']
            if pipeline_id is not None and pipeline_id != self.pipeline_id:
                raise ValueError('Feature pipeline mismatch; rebuild the history')
            self.capacity = int(meta['capacity'])
            if not 1 <= self.capacity <= 100000:
                raise ValueError('Invalid stored capacity')
        except BaseException:
            self.connection.close()
            raise

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def count(self):
        return self.connection.execute('SELECT count(*) FROM faces').fetchone()[0]

    def add_frame(self, record):
        """Atomically add accepted faces; duplicate frame ingestion is idempotent.

        A reused logical source/frame with different content is an error, not a
        silent overwrite. Failed quality faces are counted but never indexed.
        """
        if self.readonly:
            raise ValueError('History is read-only')
        if record.get('pipeline_id') != self.pipeline_id:
            raise ValueError('Feature pipeline mismatch')
        source = record['source']
        for key in ('id', 'uri'):
            if not isinstance(source.get(key), str) or not 1 <= len(source[key]) <= 2048:
                raise ValueError('Invalid source ' + key)
        if source.get('kind') not in ('image', 'video'):
            raise ValueError('Invalid source kind')
        digest = source.get('sha256', '')
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid source SHA256')
        sequence, pts = record['sequence'], record['pts_ms']
        if type(sequence) is not int or sequence < 0 or sequence > 2**53:
            raise ValueError('Invalid frame sequence')
        if isinstance(pts, bool) or not isinstance(pts, (int, float)) or not math.isfinite(pts) or pts < 0:
            raise ValueError('Invalid source timestamp')
        faces = record['faces']
        if not isinstance(faces, list) or len(faces) > 4:
            raise ValueError('At most four extracted faces per frame')
        rows, seen, rejected = [], set(), 0
        for face in faces:
            index = face['face_index']
            if type(index) is not int or index < 0 or index in seen:
                raise ValueError('Duplicate or invalid face index')
            seen.add(index)
            quality = face['quality']
            if type(quality.get('accepted')) is not bool or not quality.get('policy_id'):
                raise ValueError('Quality review is required')
            vector = normalized(face['embedding']).tobytes()
            box = np.asarray(face['box'], dtype=float)
            if box.shape != (4,) or not np.isfinite(box).all() or box[2] <= box[0] or box[3] <= box[1]:
                raise ValueError('Invalid face box')
            if not quality['accepted']:
                rejected += 1
                continue
            quality_json = json.dumps(quality, sort_keys=True, allow_nan=False)
            if len(quality_json.encode('utf-8')) > 8192:
                raise ValueError('Quality metadata exceeds 8 KiB')
            rows.append((source['id'], source['kind'], source['uri'], digest, sequence,
                         float(pts), index, json.dumps(box.tolist()),
                         quality_json, vector))
        added = duplicates = 0
        with self.connection:
            # Serialize capacity check and mutation across independent clients.
            self.connection.execute('BEGIN IMMEDIATE')
            prior = self.connection.execute('SELECT source_kind,source_uri,source_sha256 FROM faces WHERE source_id=? LIMIT 1',
                                             (source['id'],)).fetchone()
            if prior is not None and prior != (source['kind'], source['uri'], digest):
                raise ValueError('Source id already refers to different content')
            count = self.count()
            for row in rows:
                old = self.connection.execute('''SELECT source_id,source_kind,source_uri,source_sha256,
                    sequence,pts_ms,face_index,box,quality,vector FROM faces
                    WHERE source_id=? AND sequence=? AND face_index=?''', (row[0], row[4], row[6])).fetchone()
                if old is not None:
                    if old != row:
                        raise ValueError('Existing frame/face has different content or quality policy')
                    duplicates += 1
                    continue
                if count + added >= self.capacity:
                    raise ValueError('History capacity reached; no automatic deletion')
                self.connection.execute('''INSERT INTO faces(source_id,source_kind,source_uri,source_sha256,
                    sequence,pts_ms,face_index,box,quality,vector) VALUES (?,?,?,?,?,?,?,?,?,?)''', row)
                added += 1
        return dict(added=added, duplicates=duplicates, quality_rejected=rejected)

    def search(self, vector, pipeline_id, threshold, top_k=10, source_id=None,
               start_ms=None, end_ms=None, chunk_size=256):
        if pipeline_id != self.pipeline_id:
            raise ValueError('Feature pipeline mismatch')
        if isinstance(threshold, bool) or not isinstance(threshold, (float, int)) or not math.isfinite(threshold) or not -1 <= threshold <= 1:
            raise ValueError('Explicit cosine threshold must be in [-1,1]')
        if type(top_k) is not int or not 1 <= top_k <= 100:
            raise ValueError('top_k must be in 1..100')
        if type(chunk_size) is not int or not 1 <= chunk_size <= 1024:
            raise ValueError('Invalid search chunk size')
        for value in (start_ms, end_ms):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int)) or
                                      not math.isfinite(value) or value < 0):
                raise ValueError('Invalid timestamp filter')
        if start_ms is not None and end_ms is not None and start_ms > end_ms:
            raise ValueError('Invalid timestamp interval')
        query = normalized(vector)
        where, arguments = [], []
        for name, operation, value in [('source_id', '=', source_id), ('pts_ms', '>=', start_ms), ('pts_ms', '<=', end_ms)]:
            if value is not None:
                where.append(name + operation + '?')
                arguments.append(value)
        sql = 'SELECT id,source_id,source_kind,source_uri,source_sha256,sequence,pts_ms,face_index,box,quality,vector FROM faces'
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY id'
        cursor = self.connection.execute(sql, arguments)
        best, scanned = [], 0
        try:
            while True:
                rows = cursor.fetchmany(chunk_size)
                if not rows:
                    break
                vectors = np.stack([np.frombuffer(r[10], dtype='<f4') for r in rows])
                norms = np.linalg.norm(vectors, axis=1)
                if vectors.shape[1] != DIMENSION or not np.isfinite(vectors).all() or np.any(abs(norms - 1) > 0.0002):
                    raise ValueError('Corrupt stored feature')
                similarities = np.clip(vectors @ query, -1.0, 1.0)
                scanned += len(rows)
                for row, similarity in zip(rows, similarities):
                    score = float(similarity)
                    if score >= threshold:
                        candidate = (score, -row[0], row)
                        if len(best) < top_k:
                            heapq.heappush(best, candidate)
                        elif candidate[:2] > best[0][:2]:
                            heapq.heapreplace(best, candidate)
        finally:
            cursor.close()
        hits = []
        for score, _, row in sorted(best, reverse=True):
            hits.append(dict(record_id=row[0], similarity=score,
                source=dict(id=row[1], kind=row[2], uri=row[3], sha256=row[4]),
                sequence=row[5], pts_ms=row[6], face_index=row[7],
                box=json.loads(row[8]), quality=json.loads(row[9])))
        return dict(pipeline_id=self.pipeline_id, metric='normalized_inner_product',
                    threshold=float(threshold), scanned=scanned, hits=hits,
                    match_count_returned=len(hits), identity_confirmed=False)
