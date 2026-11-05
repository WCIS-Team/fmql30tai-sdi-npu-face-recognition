import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'model_backend'))
from enrollment_compare import compare_features, main


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = np.eye(512)[:2]
        self.gallery = dict(schema_version=2, pipeline_id='test-pipeline', revision=7,
            people=[dict(id='a', name='A', photos=[dict(id='a1', embedding=self.a.tolist())]),
                    dict(id='b', name='B', photos=[dict(id='b1', embedding=self.b.tolist())])])

    def test_new_name_returns_similar_existing_person_without_decision_or_mutation(self):
        before = copy.deepcopy(self.gallery)
        result = compare_features(self.a * 3, self.gallery, 'test-pipeline', target_name='new-name')
        self.assertEqual(result['alternatives'][0]['name'], 'A')
        self.assertAlmostEqual(result['alternatives'][0]['best_sample_similarity'], 1)
        self.assertFalse(result['target_found'])
        self.assertIsNone(result['admission_decision'])
        self.assertEqual(self.gallery, before)

    def test_append_wrong_person_preserves_target_and_separates_alternative(self):
        result = compare_features(self.b, self.gallery, 'test-pipeline', target_name='A', top_k=1)
        self.assertEqual(result['target']['name'], 'A')
        self.assertEqual(result['alternatives'][0]['name'], 'B')
        self.assertAlmostEqual(result['alternative_minus_target'], 1)
        correct = compare_features(self.a, self.gallery, 'test-pipeline', target_name='A')
        self.assertAlmostEqual(correct['alternative_minus_target'], -1)

    def test_center_and_best_sample_are_distinct_measurements(self):
        self.gallery['people'][0]['photos'].append(dict(id='a2', embedding=self.b.tolist()))
        result = compare_features(self.a, self.gallery, 'test-pipeline', target_name='A')
        self.assertAlmostEqual(result['target']['best_sample_similarity'], 1)
        self.assertAlmostEqual(result['target']['center_similarity'], 2 ** -.5)

    def test_empty_library_and_single_person_have_no_invented_gap(self):
        empty = dict(self.gallery, people=[])
        self.assertEqual(compare_features(self.a, empty, 'test-pipeline')['alternatives'], [])
        one = dict(self.gallery, people=self.gallery['people'][:1])
        self.assertIsNone(compare_features(self.a, one, 'test-pipeline', target_name='A')['alternative_minus_target'])

    def test_pipeline_invalid_vectors_and_ambiguous_names_fail(self):
        with self.assertRaises(ValueError):
            compare_features(self.a, self.gallery, 'wrong-pipeline')
        for vector in ([0] * 512, [1] * 511, [float('nan')] * 512):
            with self.assertRaises(ValueError):
                compare_features(vector, self.gallery, 'test-pipeline')
        self.gallery['people'][1]['name'] = 'A'
        with self.assertRaises(ValueError):
            compare_features(self.a, self.gallery, 'test-pipeline')

    def test_invalid_library_and_cancelling_samples_fail(self):
        for value in ([0] * 512, [float('nan')] * 512, (self.a * 2).tolist()):
            broken = copy.deepcopy(self.gallery)
            broken['people'][0]['photos'][0]['embedding'] = value
            with self.assertRaises(ValueError):
                compare_features(self.a, broken, 'test-pipeline')
        self.gallery['people'][0]['photos'].append(dict(id='opposite', embedding=(-self.a).tolist()))
        with self.assertRaises(ValueError):
            compare_features(self.a, self.gallery, 'test-pipeline')

    def test_equal_scores_have_deterministic_order(self):
        self.gallery['people'][1]['photos'][0]['embedding'] = self.a.tolist()
        result = compare_features(self.a, self.gallery, 'test-pipeline')
        self.assertEqual([p['person_id'] for p in result['alternatives']], ['a', 'b'])

    def test_cli_reads_snapshots_without_modifying_them(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            gallery = path / 'gallery.json'
            probe = path / 'probe.json'
            gallery.write_text(json.dumps(self.gallery), encoding='utf8')
            probe.write_text(json.dumps(dict(pipeline_id='test-pipeline', embedding=self.a.tolist())), encoding='utf8')
            before = gallery.read_bytes()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['--gallery', str(gallery), '--probe', str(probe), '--target-name', 'B']), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result['alternatives'][0]['name'], 'A')
            self.assertEqual(before, gallery.read_bytes())


if __name__ == '__main__':
    unittest.main()
