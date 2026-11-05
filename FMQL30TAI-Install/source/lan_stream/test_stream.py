"""Real HTTP integration checks; the optional C++ sender never uses hardware."""
import argparse
import http.client
import json
from pathlib import Path
import socket
import subprocess
import threading
import time
from server import FrameHub, handler_type, ThreadingHTTPServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jpeg", type=Path, required=True)
    parser.add_argument("--sender", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    hub = FrameHub(stale_seconds=.35)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_type(hub))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port
    results = []

    def request(method, path, data=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            conn.request(method, path, body=data, headers=headers or {})
            reply = conn.getresponse()
            return reply.status, reply.read()
        finally:
            conn.close()

    try:
        assert json.loads(request("GET", "/status")[1])["live"] is False
        assert request("GET", "/snapshot.jpg")[0] == 503
        assert request("GET", "/../server.py")[0] == 404
        assert request("POST", "/ingest", b"not jpeg")[0] == 400
        assert request("POST", "/ingest", b"a", {"Content-Length": str(3*1024*1024)})[0] == 413
        jpeg = args.jpeg.read_bytes()
        assert request("POST", "/ingest", jpeg, {"X-Frame-Source": "demo", "X-Frame-Sequence": "1"})[0] == 204
        assert request("GET", "/snapshot.jpg") == (200, jpeg)
        status = json.loads(request("GET", "/status")[1])
        assert status["live"] and status["source"] == "demo" and status["width"] == 640 and status["height"] == 360
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("GET", "/stream.mjpg")
        reply = conn.getresponse()
        assert reply.status == 200 and "multipart/x-mixed-replace" in reply.headers["Content-Type"]
        assert reply.readline() == b"--wcis_frame\r\n"
        headers = {}
        while True:
            line = reply.readline()
            if line == b"\r\n":
                break
            key, value = line.decode().strip().split(":", 1)
            headers[key] = value.strip()
        assert reply.read(int(headers["Content-Length"])) == jpeg
        reply.close(); conn.close()
        time.sleep(.45)
        assert not json.loads(request("GET", "/status")[1])["live"]
        assert request("GET", "/snapshot.jpg")[0] == 503
        results += ["initial offline", "malformed/oversize rejection", "snapshot byte identity", "multipart JPEG framing", "stale-frame suppression"]

        deadline = time.monotonic() + 2
        while hub.status()["viewers"] and time.monotonic() < deadline:
            time.sleep(.02)
        assert hub.status()["viewers"] == 0

        # Four slow readers cannot block the producer; the fifth is rejected.
        request("POST", "/ingest", jpeg, {"X-Frame-Source": "demo"})
        readers = []
        for _ in range(4):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            c.request("GET", "/stream.mjpg")
            r = c.getresponse()
            assert r.status == 200
            readers.append((c, r))
        extra = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        extra.request("GET", "/stream.mjpg")
        assert extra.getresponse().status == 503
        extra.close()
        before = time.monotonic()
        for n in range(20):
            assert request("POST", "/ingest", jpeg, {"X-Frame-Sequence": str(n)})[0] == 204
        assert time.monotonic() - before < 3
        for c, r in readers:
            r.close(); c.close()
        time.sleep(.5)
        results.append("bounded viewers / producer independent of slow viewers")
        if args.sender:
            for mode in ([], ["rgb565"]):
                proc = subprocess.run([str(args.sender.resolve()), "127.0.0.1", str(port), "2"] + mode,
                                      capture_output=True, text=True, timeout=8)
                assert proc.returncode == 0, proc.stdout + proc.stderr
                stats = json.loads(proc.stdout.strip().splitlines()[-1])
                assert stats["sent"] >= 10 and stats["failed"] == 0
                results.append("C++ " + ("RGB565" if mode else "BGR") + " encoder and HTTP sender")
            # A silent receiver enforces the network deadline and bounded shutdown.
            silent = socket.socket()
            silent.bind(("127.0.0.1", 0)); silent.listen()
            silent_port = silent.getsockname()[1]
            start = time.monotonic()
            proc = subprocess.run([str(args.sender.resolve()), "127.0.0.1", str(silent_port), "1"],
                                  capture_output=True, text=True, timeout=6)
            elapsed = time.monotonic() - start
            silent.close()
            assert proc.returncode == 1 and elapsed < 4
            stats = json.loads(proc.stdout.strip().splitlines()[-1])
            assert stats["replaced"] > 0 and stats["failed"] > 0 and stats["sent"] == 0
            results.append("silent receiver timeout / latest-frame replacement / bounded shutdown")
        record = dict(passed=True, checks=results, camera_opened=False, npu_opened=False, board_runtime_verified=False)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(json.dumps(record))
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == "__main__":
    main()
