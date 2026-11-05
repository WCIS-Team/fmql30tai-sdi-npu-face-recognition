import unittest
from sdi_diagnostics import decode


class DecodeTest(unittest.TestCase):
    def snapshot(self, rate=5):
        return [0x53444932, 1, 27, 3, 1234, 50,
                (1 << 11) | (rate << 7) | 1, 12000, 4, 4320, 8294400,
                (1080 << 16) | 1920, 50000000]

    def test_shd30_transport(self):
        for rate, fps in ((5, "25/1"), (7, "30/1"), (6, "30000/1001")):
            result = decode(self.snapshot(rate))
            self.assertEqual(result["transport_frame_rate"], fps)
            self.assertEqual(result["transport_geometry"], [1920, 1080])
            self.assertEqual(result["measured_active_geometry"], [1920, 1080])
            self.assertEqual(result["transport_mode"], "HD-SDI")
            self.assertEqual(result["transport_scan"], "progressive")

    def test_stopped_rx_does_not_report_stale_lock(self):
        words = self.snapshot(); words[2] = 29
        result = decode(words)
        self.assertFalse(result["fresh"])
        self.assertIsNone(result["transport_locked"])
        self.assertIsNone(result["transport_frame_rate"])
        self.assertIsNone(result["measured_active_geometry"])

    def test_unlocked_format_is_unknown(self):
        words = self.snapshot(); words[6] &= ~1
        result = decode(words)
        self.assertFalse(result["transport_locked"])
        self.assertIsNone(result["transport_geometry"])

    def test_factory_or_invalid_snapshot_rejected(self):
        for change in ((0, 0), (1, 2), (2, 32), (6, 4096), (12, 0), (3, -1)):
            words = self.snapshot(); words[change[0]] = change[1]
            with self.assertRaises(ValueError): decode(words)


if __name__ == "__main__":
    unittest.main()
