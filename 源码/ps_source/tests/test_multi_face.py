"""Check face/identity association and bounded NPU work without device access."""
import copy
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'npu_photo'))
if sys.platform == 'win32':
    # Unit fixtures never acquire Linux hardware locks.
    sys.modules.setdefault('fcntl', types.ModuleType('fcntl'))
import recognize_frame as target


class MultiFaceTests(unittest.TestCase):
    def setUp(self):
        task = Path('D:/yzd/tmp/face-multi4-20261018/unit-tests')
        task.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=task)
        self.addCleanup(self.temp.cleanup)
        self.calls = []
        self.closed = False
        self.invalid = False
        self.faces = [dict(box=[i * 20, 0, i * 20 + 10, 10], landmarks=[],
                           score=0.90 + i * .01, marker=i + 1) for i in range(5)]
        self.gallery = dict(pipeline_id='test', people={
            'person-' + str(i): np.eye(512)[i].tolist() for i in range(1, 6)})
        owner = self

        class FakeRunner:
            def forward(self, role, tensor, stem):
                owner.calls.append((role, stem))
                if role == 'yunet': return [], {'outputs': []}
                marker = round(float(tensor[0, 0, 0]) * 127.5 + 127.5)
                vector = np.eye(512)[marker] * (0 if owner.invalid else 2)
                return [vector], {'outputs': [{'sha256': str(marker)}]}

            def close(self): owner.closed = True

        self.runner = FakeRunner()
        self.addCleanup(patch.stopall)
        patch.object(target, 'Runner', return_value=self.runner).start()
        patch.object(target, 'align', side_effect=lambda image, face:
                     np.full((112, 112, 3), face['marker'], dtype=np.uint8)).start()

    def run_faces(self, count, **kwargs):
        with patch.object(target, 'decode', return_value=copy.deepcopy(self.faces[:count])):
            return target.infer_prepared(np.zeros((640, 640, 3)), 1, 1,
                root=self.temp.name, out=self.temp.name, config={},
                evidence={'threshold': .5}, gallery=self.gallery,
                image=np.zeros((120, 120, 3)), save_aligned=False, **kwargs)

    def test_four_people_keep_their_own_box_and_identity(self):
        result = self.run_faces(4)
        self.assertEqual(result['processed_face_count'], 4)
        self.assertEqual(result['status'], 'multi_face')
        self.assertEqual(result['faces'], self.faces[:4])
        for person in result['identities']:
            index = person['face_index']
            self.assertEqual(person['face'], self.faces[index])
            self.assertEqual(person['name'], 'person-' + str(index + 1))
            self.assertAlmostEqual(person['similarity'], 1)
            self.assertNotIn('embedding', person)
        self.assertEqual(len({stem for role, stem in self.calls if role == 'mobilefacenet'}), 4)
        self.assertTrue(self.closed)

    def test_five_detections_run_only_the_four_highest_scores(self):
        result = self.run_faces(5)
        self.assertEqual(result['face_count'], 5)
        self.assertEqual(result['skipped_face_count'], 1)
        self.assertEqual([p['face_index'] for p in result['identities']], [4, 3, 2, 1])
        self.assertEqual(sum(role == 'mobilefacenet' for role, stem in self.calls), 4)

    def test_single_face_retains_legacy_aliases_and_embedding(self):
        result = self.run_faces(1, return_embedding=True)
        self.assertEqual(result['name'], result['identities'][0]['name'])
        self.assertEqual(result['embedding'], result['identities'][0]['embedding'])
        self.assertEqual(self.calls, [('yunet', 'photo'), ('mobilefacenet', 'photo')])
        self.assertIn('recognizer', result['timing'])

    def test_enrollment_rejects_group_without_extracting_any_feature(self):
        result = self.run_faces(4, require_single_face=True, return_embedding=True)
        self.assertEqual(result['status'], 'multiple_faces')
        self.assertEqual(result['processed_face_count'], 0)
        self.assertNotIn('embedding', result)
        self.assertEqual(self.calls, [('yunet', 'photo')])

    def test_empty_frame_does_not_run_recognizer(self):
        result = self.run_faces(0)
        self.assertEqual(result['status'], 'no_face')
        self.assertEqual(result['identities'], [])
        self.assertEqual(self.calls, [('yunet', 'photo')])

    def test_missing_identity_does_not_inherit_another_person(self):
        self.gallery['people'].pop('person-2')
        result = self.run_faces(2)
        names = {p['face_index']: p['name'] for p in result['identities']}
        self.assertEqual(names, {1: '未知', 0: 'person-1'})

    def test_equal_templates_are_rejected_as_ambiguous(self):
        self.gallery['people']['duplicate'] = self.gallery['people']['person-1']
        self.assertEqual(self.run_faces(1)['status'], 'unknown')

    def test_invalid_vector_closes_runner(self):
        self.invalid = True
        with self.assertRaisesRegex(RuntimeError, 'Invalid feature'):
            self.run_faces(1)
        self.assertTrue(self.closed)


if __name__ == '__main__':
    unittest.main()
