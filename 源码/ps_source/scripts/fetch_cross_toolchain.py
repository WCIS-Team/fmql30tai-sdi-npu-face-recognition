"""Fetch the official Arm GNU Windows aarch64 toolchain into this project."""
from pathlib import Path
import urllib.request
import hashlib
import tarfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'gcc-arm-10.3-2021.07-mingw-w64-i686-aarch64-none-linux-gnu'
URL = 'https://armkeil.blob.core.windows.net/developer/Files/downloads/gnu-a/10.3-2021.07/binrel/' + NAME + '.tar.xz'
dest = ROOT / '.tools/cross'
dest.mkdir(parents=True, exist_ok=True)
archive = dest / (NAME + '.tar.xz')
if not archive.exists():
    with urllib.request.urlopen(URL, timeout=30) as stream, archive.open('wb') as out:
        total = 0
        while chunk := stream.read(1024 * 1024):
            out.write(chunk); total += len(chunk)
            if total % (16 * 1024 * 1024) == 0:
                print('Downloaded toolchain: ' + str(total // (1024 * 1024)) + ' MiB', flush=True)
digest = hashlib.md5(archive.read_bytes()).hexdigest()
if digest != '9d82d7fa093421ddf9bad81f308dc17a':
    raise SystemExit('Toolchain checksum differs from documented reference; not extracting.')
print('Toolchain checksum verified. Extracting...', flush=True)
with tarfile.open(archive, 'r:xz') as tar:
    # Official archive is untrusted input; prevent out-of-tree extraction.
    tar.extractall(dest, filter='data')
print('Toolchain ready: ' + str(dest / NAME), flush=True)
