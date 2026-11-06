"""Verify bundled original weights without downloading or loading them."""

import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    failed = False
    for item in manifest["models"]:
        path = root / item["path"]
        try:
            data = path.read_bytes()
            ok = (len(data) == item["size"] and
                  hashlib.sha256(data).hexdigest() == item["sha256"])
        except OSError as exc:
            print("ERROR: {}: {}".format(item["path"], exc))
            failed = True
            continue
        print("{}: {}".format("OK" if ok else "MISMATCH", item["path"]))
        failed |= not ok
    print("File verification only; no inference or board installation performed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
