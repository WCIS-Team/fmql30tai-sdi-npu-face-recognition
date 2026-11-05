"""Run on school Windows; all downloaded segments and caches stay in task root."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
URL = "https://university-program.fdwmy.com/data/2026%E5%B5%8C%E8%B5%9B/04_ICraft/v3.39.0/ICraft_V3.39.0%E5%AE%89%E8%A3%85%E5%8C%85/Icraft_Setup_v3.39.0.exe"
TOTAL = 1829435970


def main():
    assert str(ROOT).replace("\\", "/").lower().startswith("d:/yzd/tmp/wcis-face-")
    segments = ROOT / "download-parts"
    segments.mkdir(exist_ok=True)
    for key in ("TMP", "TEMP", "TMPDIR"):
        os.environ[key] = str(ROOT / "scratch")
    ranges = [(i, TOTAL * i // 8, TOTAL * (i + 1) // 8 - 1) for i in range(8)]

    def fetch(args):
        i, start, end = args
        path = segments / (str(i) + ".bin")
        expected = end - start + 1
        if path.exists() and path.stat().st_size == expected:
            print("Segment", i, "already complete", flush=True)
            return
        offset = path.stat().st_size if path.exists() else 0
        for attempt in range(3):
            request = urllib.request.Request(URL, headers={"Range": f"bytes={start + offset}-{end}", "User-Agent": "WCIS-task-build"})
            try:
                with urllib.request.urlopen(request, timeout=40) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start + offset}-{end}/{TOTAL}":
                        raise RuntimeError("Server did not honor the exact segment range")
                    with path.open("ab") as stream:
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            stream.write(chunk)
                if path.stat().st_size != expected:
                    raise RuntimeError("Incomplete segment")
                print("Segment", i, "complete", flush=True)
                return
            except (OSError, TimeoutError):
                offset = path.stat().st_size if path.exists() else 0
                if attempt == 2:
                    raise
                time.sleep(1)
        raise RuntimeError("Download did not finish")

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch, ranges))
    combined = ROOT / "Icraft_Setup_v3.39.0.complete.exe"
    digest = hashlib.sha256()
    with combined.open("wb") as stream:
        for i, start, end in ranges:
            path = segments / (str(i) + ".bin")
            assert path.stat().st_size == end - start + 1
            with path.open("rb") as part:
                while True:
                    chunk = part.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    stream.write(chunk)
    assert combined.stat().st_size == TOTAL
    record = {"source": URL, "bytes": TOTAL, "sha256": digest.hexdigest(), "filename": str(combined)}
    (ROOT / "installer-download.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
