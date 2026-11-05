"""LAN atomic pixel/result receiver; legacy JPEG viewer. No hardware access."""
import argparse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as _ThreadingHTTPServer
import json
from pathlib import Path
import socket
import threading
import time
from urllib.parse import parse_qs, urlsplit
from raw_protocol import RawHub, MAX_PACKET, MAX_META
from device_status import DeviceStatusHub

ROOT = Path(__file__).resolve().parent
MAX_JPEG = 2 * 1024 * 1024


class ThreadingHTTPServer(_ThreadingHTTPServer):
    # Short polling/upload connections can arrive in a burst from several viewers.
    request_queue_size = 64


def jpeg_dimensions(data):
    """Validate bounded JPEG marker geometry, not a full entropy decode."""
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise ValueError("Expected JPEG")
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 255:
            raise ValueError("Invalid JPEG marker")
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos >= len(data):
            break
        marker = data[pos]
        pos += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xDA:
            break
        length = int.from_bytes(data[pos:pos + 2], "big")
        if length < 2 or pos + length > len(data):
            raise ValueError("Invalid JPEG segment")
        if marker in (0xC0, 0xC1, 0xC2):
            if length < 8:
                raise ValueError("Invalid JPEG geometry")
            height = int.from_bytes(data[pos + 3:pos + 5], "big")
            width = int.from_bytes(data[pos + 5:pos + 7], "big")
            if not (1 <= width <= 4096 and 1 <= height <= 4096):
                raise ValueError("JPEG dimensions out of range")
            return width, height
        pos += length
    raise ValueError("JPEG has no supported frame header")


class FrameHub:
    def __init__(self, stale_seconds=2):
        self.condition = threading.Condition()
        self.frame = None
        self.sequence = 0
        self.arrivals = deque(maxlen=120)
        self.stale_seconds = stale_seconds
        self.viewers = 0

    def publish(self, jpeg, source, source_sequence):
        width, height = jpeg_dimensions(jpeg)
        now = time.monotonic()
        with self.condition:
            self.sequence += 1
            self.frame = (jpeg, now, source, source_sequence, width, height)
            self.arrivals.append(now)
            self.condition.notify_all()

    def status(self):
        with self.condition:
            if self.frame is None:
                return dict(live=False, source="none", frames_received=0, viewers=self.viewers)
            jpeg, timestamp, source, sequence, width, height = self.frame
            now = time.monotonic()
            age = now - timestamp
            window = [t for t in self.arrivals if now - t < 3]
            elapsed = window[-1] - window[0] if len(window) > 1 else 0
            fps = (len(window) - 1) / elapsed if elapsed > 0 else 0
            return dict(live=age <= self.stale_seconds, source=source,
                        frames_received=self.sequence, source_sequence=sequence,
                        width=width, height=height, jpeg_bytes=len(jpeg),
                        receive_fps=round(fps, 1), frame_age_ms=round(age * 1000), viewers=self.viewers)


def handler_type(hub, raw_hub=None, device_hub=None):
    raw_hub = raw_hub or RawHub()
    device_hub = device_hub or DeviceStatusHub()
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def respond(self, code, payload=b"", mime="application/json; charset=utf-8"):
            keep = self.path.startswith("/api/") and code in (200, 204, 409, 503) and self.headers.get("Connection", "").lower() != "close"
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive" if keep else "close")
            self.end_headers()
            if payload:
                self.wfile.write(payload)
            self.close_connection = not keep

        def do_POST(self):
            if self.path in ("/api/frame", "/api/results", "/api/device-status"):
                try:
                    if self.headers.get("Transfer-Encoding"):
                        return self.respond(400)
                    length = int(self.headers.get("Content-Length", "0"))
                    limit = MAX_PACKET if self.path == "/api/frame" else MAX_META
                    if not 1 <= length <= limit:
                        return self.respond(413)
                    payload = self.rfile.read(length)
                    if len(payload) != length:
                        return self.respond(400)
                    if self.path == "/api/frame":
                        raw_hub.publish(payload)
                    elif self.path == "/api/results":
                        raw_hub.results(json.loads(payload))
                    else:
                        device_hub.publish(json.loads(payload))
                except LookupError:
                    return self.respond(409)
                except (ValueError, TypeError, AttributeError, UnicodeError, OSError):
                    return self.respond(400)
                return self.respond(204)
            if self.path != "/ingest":
                return self.respond(404)
            if self.headers.get("Transfer-Encoding"):
                return self.respond(400)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= MAX_JPEG:
                    return self.respond(413)
                source = self.headers.get("X-Frame-Source", "unverified")
                if source not in ("demo", "camera", "unverified"):
                    return self.respond(400)
                sequence = int(self.headers.get("X-Frame-Sequence", "0"))
                if not 0 <= sequence < 2**64:
                    return self.respond(400)
                jpeg = self.rfile.read(length)
                if len(jpeg) != length:
                    return self.respond(400)
                hub.publish(jpeg, source, sequence)
            except (ValueError, TimeoutError, OSError):
                return self.respond(400)
            self.respond(204)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/":
                return self.respond(200, (ROOT / "dist/index.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/jpeg-preview":
                return self.respond(200, (ROOT / "dist/jpeg-preview.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/frame":
                try:
                    after = int(parse_qs(urlsplit(self.path).query).get("after", ["-1"])[0])
                except ValueError:
                    return self.respond(400)
                code, payload = raw_hub.snapshot(after)
                return self.respond(code, payload, "application/octet-stream")
            if path == "/api/status":
                return self.respond(200, json.dumps(dict(raw_hub.status(), device=device_hub.status())).encode())
            if path == "/status":
                return self.respond(200, json.dumps(hub.status()).encode())
            if path == "/snapshot.jpg":
                with hub.condition:
                    frame = hub.frame
                if not frame or time.monotonic() - frame[1] > hub.stale_seconds:
                    return self.respond(503)
                return self.respond(200, frame[0], "image/jpeg")
            if path != "/stream.mjpg":
                return self.respond(404)
            with hub.condition:
                if hub.viewers >= 4:
                    return self.respond(503)
                hub.viewers += 1
            try:
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=wcis_frame")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                sequence = -1
                while True:
                    with hub.condition:
                        hub.condition.wait_for(lambda: hub.sequence != sequence and hub.frame is not None, timeout=1)
                        frame, current = hub.frame, hub.sequence
                    # Close a stalled source instead of presenting an old frame as live.
                    if not frame or time.monotonic() - frame[1] > hub.stale_seconds:
                        break
                    if current == sequence:
                        continue
                    jpeg = frame[0]
                    header = ("--wcis_frame\r\nContent-Type: image/jpeg\r\n"
                              f"Content-Length: {len(jpeg)}\r\nX-Sequence: {current}\r\n\r\n").encode()
                    self.wfile.write(header + jpeg + b"\r\n")
                    self.wfile.flush()
                    sequence = current
            except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
                pass
            finally:
                with hub.condition:
                    hub.viewers -= 1
                self.close_connection = True
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), handler_type(FrameHub()))
    server.daemon_threads = True
    print(f"Local viewer: http://127.0.0.1:{args.port}/", flush=True)
    print(f"Listening on {args.host}:{args.port}; no camera hardware is opened.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
