import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_admitted_memory_probe import PROBE_BYTES, WINDOW_BYTES, validate_probe


def sample():
    return dict(status='memory_probe', allocation_base=4096, customop_started=False,
                results=[dict(offset=offset, chunk=chunk, bytes=PROBE_BYTES,
                              mismatches=0, second_read_mismatches=0,
                              changed_between_reads=0, first_mismatch=PROBE_BYTES,
                              lane_errors=[0] * 64, bit_errors=[0] * 8)
                         for offset in (0, 64) for chunk in (PROBE_BYTES, 65536)])


def parse(q, code=0):
    return validate_probe(code, 'SDK initialization banner\nWCIS_JPEG_RESULT ' + json.dumps(q) + '\n')


class ProbeAdmission(unittest.TestCase):
    def test_complete_zero_error_receipt(self):
        self.assertEqual(parse(sample())['allocation_base'], 4096)

    def test_process_success_does_not_override_bad_data(self):
        for field in ('mismatches', 'second_read_mismatches', 'changed_between_reads'):
            q = sample()
            q['results'][2][field] = 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse(q)

    def test_repeated_case_does_not_count_as_coverage(self):
        q = sample()
        q['results'][3] = copy.deepcopy(q['results'][0])
        with self.assertRaises(ValueError):
            parse(q)

    def test_window_and_alignment(self):
        for base in (1, -64, WINDOW_BYTES - 64):
            q = sample()
            q['allocation_base'] = base
            with self.subTest(base=base), self.assertRaises(ValueError):
                parse(q)

    def test_contradictory_error_distribution(self):
        for field in ('lane_errors', 'bit_errors'):
            q = sample()
            q['results'][0][field][0] = 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse(q)

    def test_customop_or_failed_process_is_rejected(self):
        q = sample()
        q['customop_started'] = True
        with self.assertRaises(ValueError):
            parse(q)
        with self.assertRaises(ValueError):
            parse(sample(), 3)

    def test_incomplete_or_duplicate_json(self):
        for raw in ('WCIS_JPEG_RESULT {',
                    'WCIS_JPEG_RESULT {}\nWCIS_JPEG_RESULT {}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_probe(0, raw)


if __name__ == '__main__':
    unittest.main()
