"""A coarse clock must not break frame delivery or status responses."""
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lan_stream'))
from raw_protocol import RawHub, pack
from server import FrameHub


class ReceiveFpsTests(unittest.TestCase):
    def test_raw_equal_arrival_times_preserve_latest_frame(self):
        hub = RawHub()
        meta = dict(schema_version=1, stream_id='clock-test', frame_id='1',
                    timestamp_us='1', timestamp_basis='ps_dma_done_monotonic',
                    source='demo', pixel_format='RGB565LE', width=1, height=1,
                    stride_bytes=2)
        with patch('raw_protocol.time.monotonic', return_value=100):
            hub.publish(pack(meta, b'\x00\x00'))
            hub.publish(pack(dict(meta, frame_id='2', timestamp_us='2'), b'\xff\xff'))
            code, packet = hub.snapshot(None)
            self.assertEqual(code, 200)
            length = struct.unpack_from('!I', packet)[0]
            shown = json.loads(packet[4:4+length])
            self.assertEqual(shown['frame_id'], '2')
            self.assertEqual(packet[4+length:], b'\xff\xff')
            self.assertEqual(shown['receive_fps'], 0)
            self.assertEqual(hub.status()['receive_fps'], 0)
        with patch('raw_protocol.time.monotonic', return_value=100.5):
            hub.publish(pack(dict(meta, frame_id='3', timestamp_us='3'), b'\x01\x00'))
            self.assertEqual(hub.status()['receive_fps'], 4)
        with patch('raw_protocol.time.monotonic', return_value=104):
            self.assertEqual(hub.snapshot(None)[0], 503)
            self.assertEqual(hub.status()['receive_fps'], 0)

    def test_jpeg_equal_arrival_times_preserve_status(self):
        hub = FrameHub()
        with patch('server.jpeg_dimensions', return_value=(1, 1)):
            with patch('server.time.monotonic', return_value=100):
                hub.publish(b'jpeg-1', 'demo', 1)
                hub.publish(b'jpeg-2', 'demo', 2)
                status = hub.status()
                self.assertTrue(status['live'])
                self.assertEqual(status['frames_received'], 2)
                self.assertEqual(status['source_sequence'], 2)
                self.assertEqual(status['receive_fps'], 0)
            with patch('server.time.monotonic', return_value=100.5):
                hub.publish(b'jpeg-3', 'demo', 3)
                self.assertEqual(hub.status()['receive_fps'], 4)


if __name__ == '__main__':
    unittest.main()
