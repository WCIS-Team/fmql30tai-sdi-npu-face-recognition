"""Send exported test JPEGs. No hardware access; source is always marked demo."""
import argparse
import http.client
from pathlib import Path
import time
from urllib.parse import urlsplit

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8088/ingest")
parser.add_argument("--frames", type=Path, required=True)
parser.add_argument("--seconds", type=float, default=30)
parser.add_argument("--fps", type=float, default=10)
args = parser.parse_args()
if not 0 < args.fps <= 30 or not 0 < args.seconds <= 3600:
    parser.error("fps must be 0..30 and seconds 0..3600")
url = urlsplit(args.url)
if url.scheme != "http" or not url.hostname:
    parser.error("Use an HTTP LAN endpoint")
images = [p.read_bytes() for p in sorted(args.frames.glob("*.jpg"))]
if not images:
    parser.error("No exported test JPEGs found")
start = time.monotonic()
sequence = 0
while time.monotonic() - start < args.seconds:
    sequence += 1
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=2)
    try:
        conn.request("POST", url.path or "/ingest", images[(sequence - 1) % len(images)],
                     {"Content-Type": "image/jpeg", "X-Frame-Source": "demo", "X-Frame-Sequence": str(sequence)})
        reply = conn.getresponse()
        reply.read()
        if reply.status != 204:
            raise RuntimeError(f"Receiver rejected frame: {reply.status}")
    finally:
        conn.close()
    time.sleep(max(0, start + sequence / args.fps - time.monotonic()))
print(f"DEMO sent {sequence} test frames; no camera was opened.")
