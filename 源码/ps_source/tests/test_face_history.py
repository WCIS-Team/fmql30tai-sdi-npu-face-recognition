"""Quality perturbations and durable, bounded exact history-search contracts."""
import copy
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'model_backend'))
from face_history.quality import QualityPolicy, face_quality, select_best
from face_history.records import make_record, query_face
from face_history.store import HistoryStore, normalized
from face_history.cli import main, source_for
from face_history.records import file_sha


class QualityTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(413)
        gray = rng.integers(65, 190, (112, 112), dtype=np.uint8)
        self.image = np.repeat(gray[:, :, None], 3, axis=2)
        self.face = dict(box=[0, 0, 112, 112], score=.99)

    def test_quality_responds_to_blur_dark_bright_and_size(self):
        original = face_quality(self.image, self.face)
        blurred = face_quality(cv2.GaussianBlur(self.image, (31, 31), 8), self.face)
        self.assertTrue(original['accepted'])
        self.assertIn('low_detail_or_blur', blurred['reasons'])
        self.assertGreater(original['heuristic_rank'], blurred['heuristic_rank'])
        self.assertIn('too_dark', face_quality(self.image // 8, self.face)['reasons'])
        self.assertIn('too_bright', face_quality(np.full_like(self.image, 250), self.face)['reasons'])
        self.assertIn('face_too_small', face_quality(self.image, dict(self.face, box=[0, 0, 20, 20]))['reasons'])

    def test_clipping_and_truncated_box_have_explicit_reasons(self):
        clipped = face_quality(np.zeros_like(self.image), self.face)
        self.assertIn('excessive_clipping', clipped['reasons'])
        partial = face_quality(self.image, dict(self.face, box=[-40, 0, 112, 112]))
        self.assertIn('truncated_face', partial['reasons'])

    def test_invalid_geometry_and_nonfinite_policy_fail(self):
        for box in ([0, 0, 0, 10], [200, 0, 300, 10], [0, 0, np.nan, 10]):
            with self.assertRaises(ValueError):
                face_quality(self.image, dict(self.face, box=box))
        for kwargs in (dict(min_brightness=float('nan')), dict(thumbnail_size=112.5),
                       dict(max_clipped_fraction=2), dict(min_laplacian_variance=0)):
            with self.assertRaises(ValueError):
                QualityPolicy(**kwargs)

    def test_best_shot_never_selects_rejected_face(self):
        accepted = dict(face_index=0, sequence=8, quality=face_quality(self.image, self.face))
        rejected = copy.deepcopy(accepted)
        rejected['quality'].update(accepted=False, heuristic_rank=100)
        self.assertIs(select_best([rejected, accepted]), accepted)
        self.assertIsNone(select_best([rejected]))


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'history.sqlite'
        self.vector = np.eye(512, dtype=np.float32)[0]
        self.record = dict(pipeline_id='test-model-contract', sequence=0, pts_ms=0,
            source=dict(id='video-A', kind='video', uri='sample.avi', sha256='a' * 64),
            faces=[dict(face_index=0, box=[0, 0, 112, 112], embedding=self.vector.tolist(),
                        quality=dict(accepted=True, policy_id='policy-test', reasons=[], heuristic_rank=.9))])

    def test_roundtrip_normalization_duplicate_and_readonly(self):
        with HistoryStore(self.path, self.record['pipeline_id']) as store:
            self.record['faces'][0]['embedding'] = (self.vector * 3).tolist()
            self.assertEqual(store.add_frame(self.record)['added'], 1)
            self.assertEqual(store.add_frame(self.record)['duplicates'], 1)
        before = self.path.read_bytes()
        with HistoryStore(self.path, 'test-model-contract', readonly=True) as store:
            hit = store.search(self.vector * 9, store.pipeline_id, .99)['hits'][0]
            self.assertAlmostEqual(hit['similarity'], 1)
            self.assertEqual(hit['source']['uri'], 'sample.avi')
            with self.assertRaises(ValueError):
                store.add_frame(self.record)
        self.assertEqual(self.path.read_bytes(), before)

    def test_capacity_failure_rolls_back_whole_frame(self):
        with HistoryStore(self.path, 'test-model-contract', capacity=1) as store:
            extra = copy.deepcopy(self.record['faces'][0])
            extra['face_index'] = 1
            self.record['faces'].append(extra)
            with self.assertRaisesRegex(ValueError, 'capacity'):
                store.add_frame(self.record)
            self.assertEqual(store.count(), 0)

    def test_pipeline_mismatch_rejected_on_write_query_and_reopen(self):
        with HistoryStore(self.path, 'test-model-contract') as store:
            with self.assertRaisesRegex(ValueError, 'pipeline'):
                store.add_frame(dict(self.record, pipeline_id='another'))
            with self.assertRaisesRegex(ValueError, 'pipeline'):
                store.search(self.vector, 'another', .5)
        with self.assertRaisesRegex(ValueError, 'pipeline'):
            HistoryStore(self.path, 'another')

    def test_source_conflict_and_changed_face_are_not_silently_overwritten(self):
        with HistoryStore(self.path, 'test-model-contract') as store:
            store.add_frame(self.record)
            changed = copy.deepcopy(self.record)
            changed['source']['sha256'] = 'b' * 64
            with self.assertRaises(ValueError):
                store.add_frame(changed)
            changed = copy.deepcopy(self.record)
            changed['faces'][0]['embedding'] = (-self.vector).tolist()
            with self.assertRaises(ValueError):
                store.add_frame(changed)
            self.assertEqual(store.count(), 1)

    def test_quality_rejected_faces_do_not_enter_index(self):
        self.record['faces'][0]['quality']['accepted'] = False
        with HistoryStore(self.path, 'test-model-contract') as store:
            self.assertEqual(store.add_frame(self.record)['quality_rejected'], 1)
            self.assertEqual(store.count(), 0)

    def test_invalid_features_and_duplicate_indices_do_not_write(self):
        with HistoryStore(self.path, 'test-model-contract') as store:
            for vector in ([0] * 512, [1] * 511, [float('nan')] * 512):
                record = copy.deepcopy(self.record)
                record['faces'][0]['embedding'] = vector
                with self.assertRaises(ValueError):
                    store.add_frame(record)
            record = copy.deepcopy(self.record)
            record['faces'] *= 2
            with self.assertRaises(ValueError):
                store.add_frame(record)
            self.assertEqual(store.count(), 0)

    def test_exact_chunked_search_matches_independent_cosine_and_filters(self):
        rng = np.random.default_rng(17)
        vectors = rng.normal(size=(31, 512))
        query = vectors[9] + rng.normal(size=512) * .05
        expected = (vectors @ query) / (np.linalg.norm(vectors, axis=1) * np.linalg.norm(query))
        with HistoryStore(self.path, 'test-model-contract') as store:
            for i, vector in enumerate(vectors):
                record = copy.deepcopy(self.record)
                record.update(sequence=i, pts_ms=i * 1000)
                record['faces'][0]['embedding'] = vector.tolist()
                store.add_frame(record)
            result = store.search(query, store.pipeline_id, -1, top_k=7, chunk_size=3)
            self.assertEqual([h['sequence'] for h in result['hits']], np.argsort(-expected)[:7].tolist())
            for hit in result['hits']:
                self.assertAlmostEqual(hit['similarity'], expected[hit['sequence']], places=6)
            subset = store.search(query, store.pipeline_id, -1, source_id='video-A', start_ms=8000, end_ms=10000)
            self.assertEqual(subset['scanned'], 3)
            self.assertEqual(store.search(query, store.pipeline_id, -1, source_id='absent')['hits'], [])

    def test_ties_have_stable_order_and_threshold_is_inclusive(self):
        with HistoryStore(self.path, 'test-model-contract') as store:
            for sequence in (4, 2, 7):
                store.add_frame(dict(self.record, sequence=sequence))
            hits = store.search(self.vector, store.pipeline_id, 1, top_k=2, chunk_size=1)['hits']
            self.assertEqual([h['sequence'] for h in hits], [4, 2])
            self.assertEqual(store.search(-self.vector, store.pipeline_id, .5)['hits'], [])

    def test_missing_readonly_db_is_not_created_and_bad_query_options_fail(self):
        missing = Path(self.temp.name) / 'missing.sqlite'
        with self.assertRaises(sqlite3.Error):
            HistoryStore(missing, readonly=True)
        self.assertFalse(missing.exists())
        with HistoryStore(self.path, 'test-model-contract') as store:
            for options in (dict(threshold=float('nan')), dict(threshold=0, top_k=0),
                            dict(threshold=0, start_ms=2, end_ms=1)):
                with self.assertRaises(ValueError):
                    store.search(self.vector, store.pipeline_id, **options)

    def test_query_requires_explicit_multiface_selection_and_quality(self):
        record = dict(self.record, detected_face_count=2)
        with self.assertRaises(ValueError):
            query_face(record)
        self.assertEqual(query_face(record, 0)['face_index'], 0)
        record['faces'][0]['quality']['accepted'] = False
        with self.assertRaisesRegex(ValueError, 'quality'):
            query_face(record, 0)

    def test_existing_result_adapter_checks_box_identity_link(self):
        image = np.random.default_rng(5).integers(60, 190, (112, 112, 3), dtype=np.uint8)
        face = dict(box=[0, 0, 112, 112], score=.99)
        result = dict(pipeline_id='test-model-contract', faces=[face], face_count=1,
                      identities=[dict(face_index=0, face=face, embedding=self.vector.tolist())])
        record = make_record(image, result, self.record['source'])
        self.assertTrue(record['faces'][0]['quality']['accepted'])
        result['identities'][0]['face'] = dict(face, box=[1, 1, 10, 10])
        with self.assertRaisesRegex(ValueError, 'different detection'):
            make_record(image, result, self.record['source'])

    def test_cli_import_review_and_search_without_hardware(self):
        work = Path(self.temp.name)
        image = np.random.default_rng(15).integers(60, 190, (112, 112, 3), dtype=np.uint8)
        photo = work / 'image.png'
        cv2.imwrite(str(photo), image)
        face = dict(box=[0, 0, 112, 112], score=.99)
        result = dict(pipeline_id='test-model-contract', photo_sha256=file_sha(photo),
            face_count=1, faces=[face], identities=[dict(face_index=0, face=face,
                                                       embedding=self.vector.tolist())])
        evidence = work / 'result.json'
        evidence.write_text(json.dumps(result), encoding='utf8')
        manifest = work / 'manifest.json'
        manifest.write_text(json.dumps([dict(image='image.png', result='result.json')]), encoding='utf8')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['review', '--image', str(photo), '--result', str(evidence)]), 0)
            self.assertEqual(main(['import', '--db', str(self.path), '--manifest', str(manifest)]), 0)
            report = work / 'hits.json'
            self.assertEqual(main(['search-result', '--db', str(self.path), '--image', str(photo),
                                   '--result', str(evidence), '--threshold', '.9', '--out', str(report)]), 0)
            self.assertEqual(json.loads(report.read_text())['hits'][0]['sequence'], 0)
            self.assertNotIn('embedding', report.read_text())
            result['photo_sha256'] = '0' * 64
            evidence.write_text(json.dumps(result), encoding='utf8')
            self.assertEqual(main(['import', '--db', str(self.path), '--manifest', str(manifest)]), 1)

    def test_cli_output_cannot_replace_inputs_or_database(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(['review', '--image', 'input.png', '--result', 'result.json', '--out', 'input.png'])


if __name__ == '__main__':
    unittest.main()
