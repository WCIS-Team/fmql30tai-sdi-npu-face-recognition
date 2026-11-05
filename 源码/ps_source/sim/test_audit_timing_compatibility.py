"""Fail-closed tests: equal count/worst slack must not hide changed failures."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_timing_compatibility import compare_reports


def report():
    def row(fields):
        widths = (18, 8, 25, 16, 14, 12, 11, 20, 0)
        return ''.join(str(v).ljust(w) for v, w in zip(fields, widths))
    return '\n'.join([
        'WNS(ns) TNS(ns) TNS Failing Endpoints TPWS Total Endpoints',
        '-----', '0.005 0.000 0 100 0.004 0.000 0 100 -0.409 -0.479 2 100',
        '', 'Pulse Width Checks', 'Clock Name: clk_npu', 'Period(ns): 1.000',
        row(('Check Type', 'Corner', 'Lib Pin', 'Reference Pin', 'Required(ns)',
             'Actual(ns)', 'Slack(ns)', 'Location', 'Pin')),
        row(('Min Period', 'n/a', 'BUFG/I', 'n/a', '1.409', '1.000', '-0.409', 'BUFGCTRL_X0Y20', 'npu/buf/I')),
        row(('Min Period', 'n/a', 'PLLE2_ADV/CLKOUT0', 'n/a', '1.071', '1.000', '-0.071', 'PLLE2_ADV_X1Y3', 'npu/pll/CLKOUT0')),
        '', '',
    ])


class TimingCompatibilityTests(unittest.TestCase):
    def test_identical_legacy_failures_pass_compatibility(self):
        before, after = compare_reports(report(), report())
        self.assertEqual(before['failures'], after['failures'])
        self.assertEqual(len(after['failures']), 2)

    def assert_rejected(self, candidate):
        with self.assertRaises(ValueError):
            compare_reports(report(), candidate)

    def test_changed_endpoint_same_count_and_worst(self):
        self.assert_rejected(report().replace('npu/pll/CLKOUT0', 'other/pll/CLKOUT0'))

    def test_changed_check_type_same_count_and_worst(self):
        self.assert_rejected(report().replace('Min Period', 'Max Period', 1))

    def test_unknown_check_type(self):
        self.assert_rejected(report().replace('Min Period', 'Unknown', 1))

    def test_changed_clock(self):
        self.assert_rejected(report().replace('clk_npu', 'clk_other'))

    def test_changed_requirement(self):
        self.assert_rejected(report().replace('1.071', '1.072'))

    def test_changed_nonworst_slack(self):
        self.assert_rejected(report().replace('-0.071', '-0.072'))

    def test_missing_detail_row(self):
        self.assert_rejected('\n'.join(line for line in report().splitlines()
                                        if not line.endswith('npu/pll/CLKOUT0')) + '\n\n')

    def test_truncated_table(self):
        self.assert_rejected(report().rstrip())

    def test_negative_setup(self):
        self.assert_rejected(report().replace('0.005', '-0.001'))

    def test_nan_summary(self):
        self.assert_rejected(report().replace('0.005', 'nan'))

    def test_nan_check(self):
        self.assert_rejected(report().replace('1.071', 'nan  '))


if __name__ == '__main__':
    unittest.main()
