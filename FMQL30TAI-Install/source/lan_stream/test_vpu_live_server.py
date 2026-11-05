"""Verify fail-closed freshness/session handling; no camera or encoder emulation."""
import http.client
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from vpu_live_server import Frames, ThreadingHTTPServer, handler


class FreshFramesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "wcis-test"
        self.directory.mkdir()
        self.boot = self.root / "boot"
        self.boot.write_text("test-boot")
        self.control = self.root / "control.json"
        self.cfg = dict(source="camera", session="s1", boot_id="test-boot", pid=os.getpid(), directory=str(self.directory))
        self.info = dict(source="camera", state="ready", boot_id="test-boot", pid=os.getpid(), frame_id=1, captured_at=time.monotonic(), width=960, height=540, encoded=1)
        self.jpeg = b"\xff\xd8transport-test\xff\xd9"
        self.frames = Frames(self.control, self.boot, self.root, lambda pid: pid == os.getpid())
        self.write()

    def write(self):
        self.control.write_text(json.dumps(self.cfg))
        (self.directory / "status.json").write_text(json.dumps(self.info))
        meta = json.dumps(self.info).encode()
        (self.directory / "latest.frame").write_bytes(struct.pack("<I", len(meta)) + meta + self.jpeg)

    def test_fresh_frame(self):
        state, jpeg = self.frames.read()
        self.assertTrue(state["ready"])
        self.assertEqual(jpeg, self.jpeg)

    def web_frame(self, **changes):
        self.info.update(codec='raw_uyvy_external_test',web_preview_codec='mjpeg');self.write()
        media=dict(self.cfg,ready=True,codec='h264',external_h264=True,width=960,height=540,
                   encoder_pid=os.getpid(),muxer_pid=os.getpid(),updated_at=time.monotonic(),
                   h264_encoded_at=time.monotonic(),encoded=300)
        (self.directory/'external-video.json').write_text(json.dumps(media))
        info=dict(self.info,codec='mjpeg',encoded=15,**changes)
        body=json.dumps(info).encode()
        (self.directory/'preview-jpeg.frame').write_bytes(struct.pack('<I',len(body))+body+self.jpeg)

    def test_web_preview_does_not_change_mp4_recording_source(self):
        self.web_frame()
        state,jpeg=self.frames.read_preview()
        self.assertTrue(state['ready']);self.assertEqual(jpeg,self.jpeg)
        self.assertEqual((state['codec'],state['recording_codec'],state['encoded']),('mjpeg','h264',15))
        state,data=self.frames.read()
        self.assertEqual((state['codec'],state['encoded'],data),('h264',300,None))

    def test_web_preview_rejects_old_or_foreign_frames_without_breaking_recording(self):
        for change in [dict(captured_at=time.monotonic()-2),dict(boot_id='old'),dict(pid=0),dict(width=1),dict(frame_id=0)]:
            self.web_frame(**change)
            state,jpeg=self.frames.read_preview()
            self.assertFalse(state['ready']);self.assertIsNone(jpeg)
            self.assertTrue(self.frames.read()[0]['ready'])
        self.web_frame();(self.directory/'preview-jpeg.frame').write_bytes(b'incomplete')
        self.assertFalse(self.frames.read_preview()[0]['ready'])

    def test_web_preview_retains_hardware_freshness_gate(self):
        self.web_frame();self.frames.process_alive=lambda pid:False
        self.assertFalse(self.frames.read_preview()[0]['ready'])

    def test_external_h264_requires_live_identity_bound_workers(self):
        self.info['codec']='raw_uyvy_external_test';self.write()
        media=dict(self.cfg,ready=True,codec='h264',external_h264=True,width=960,height=540,
                   encoder_pid=os.getpid(),muxer_pid=os.getpid(),updated_at=time.monotonic(),
                   h264_encoded_at=time.monotonic(),encoded=30)
        path=self.directory/'external-video.json';path.write_text(json.dumps(media))
        state,data=self.frames.read();self.assertTrue(state['ready']);self.assertIsNone(data)
        for change in [dict(session='other'),dict(updated_at=time.monotonic()-10),
                       dict(encoder_pid=os.getpid()+100000),dict(width=1920)]:
            path.write_text(json.dumps(dict(media,**change)))
            self.assertFalse(self.frames.read()[0]['ready'])

    def test_recorder_skips_duplicate_packet_and_reads_new_frame(self):
        with patch.object(self.frames, 'read', wraps=self.frames.read) as read:
            self.assertTrue(self.frames.read_if_changed()[0]['ready'])
            self.assertEqual(self.frames.read_if_changed(), (None, None))
            self.assertEqual(read.call_count, 1)
            # Status may be published at 1 Hz; each packet still owns its metadata.
            self.info['frame_id'] = 2
            meta = json.dumps(self.info).encode()
            packet = self.directory/'latest.new'
            packet.write_bytes(struct.pack('<I', len(meta))+meta+self.jpeg)
            packet.replace(self.directory/'latest.frame')
            self.assertEqual(self.frames.read_if_changed()[0]['frame_id'], 2)

    def test_recorder_duplicate_health_recheck_detects_dead_source(self):
        self.assertTrue(self.frames.read_if_changed()[0]['ready'])
        self.frames.process_alive = lambda _: False
        self.frames._poll_health_at = 0
        self.assertFalse(self.frames.read_if_changed()[0]['ready'])

    def test_recorder_control_switch_does_not_reuse_old_session(self):
        self.frames.read_if_changed()
        self.cfg['pid'] += 1
        # Make the control version change deterministic on coarse-mtime filesystems.
        pending=self.control.with_suffix('.pending')
        pending.write_text(json.dumps(self.cfg));pending.replace(self.control)
        self.assertFalse(self.frames.read_if_changed()[0]['ready'])

    def test_stale_frame_rejected(self):
        self.info["captured_at"] -= 10
        self.write()
        self.assertIsNone(self.frames.read()[1])
        self.assertEqual(self.frames.read()[0]["state"], "no_fresh_frame")

    def test_wrong_boot_or_source_rejected(self):
        self.boot.write_text("other-boot")
        self.assertIsNone(self.frames.read()[1])
        self.boot.write_text("test-boot")
        self.cfg["source"] = "vtc"
        self.write()
        self.assertIsNone(self.frames.read()[1])

    def test_stopped_source_does_not_show_cached_image(self):
        self.info["state"] = "stopped"
        self.write()
        self.assertIsNone(self.frames.read()[1])

    def test_partial_packet_rejected(self):
        (self.directory / "latest.frame").write_bytes(struct.pack("<I", 20000))
        self.assertIsNone(self.frames.read()[1])

    def test_dead_capture_rejected(self):
        self.frames.process_alive = lambda _: False
        self.assertIsNone(self.frames.read()[1])

    def test_old_frame_cannot_enter_new_session(self):
        self.cfg["pid"] += 1
        self.control.write_text(json.dumps(self.cfg))
        self.assertIsNone(self.frames.read()[1])

    def test_http_snapshot_becomes_unavailable_when_stopped(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.frames))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            client.request("GET", "/snapshot.jpg")
            response = client.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), self.jpeg)
            client.close()
            self.info["state"] = "stopped"
            self.write()
            client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
            client.request("GET", "/snapshot.jpg")
            response = client.getresponse()
            self.assertEqual(response.status, 503)
            response.read()
            client.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
