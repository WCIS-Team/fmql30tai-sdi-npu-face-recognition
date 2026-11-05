"""Install the pinned JPEG RTL reference, preserving license and provenance."""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

COMMIT = '90bc0c46d2c2c4bda1020113f306a5f17dcc5f2f'
FILES = ['LICENSE', 'README.md'] + ['rtl/' + n + '.v' for n in (
    'axi4_lite_regs', 'bitstream_packer', 'bram_sdp', 'dct_1d', 'dct_2d',
    'huffman_encoder', 'input_buffer', 'jfif_writer', 'mjpegzero_enc_top',
    'quantizer', 'rgb_to_ycbcr', 'zigzag_reorder')]


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Previously fetched, unmodified checkout')
    args = parser.parse_args()
    if args.source:
        actual = subprocess.check_output(['git', '-C', str(args.source), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != COMMIT:
            raise ValueError('Reference checkout is not the pinned commit')
        subprocess.run(['git', '-C', str(args.source), 'diff', '--exit-code', 'HEAD', '--', *FILES],
                       check=True, stdout=subprocess.DEVNULL)
    dest = Path(__file__).resolve().parents[1] / 'rtl/vendor/mjpegzero'
    records = []
    for name in FILES:
        url = f'https://raw.githubusercontent.com/lcapossio/mjpegZero/{COMMIT}/{name}'
        data = (args.source / name).read_bytes() if args.source else urllib.request.urlopen(url, timeout=30).read()
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        records.append(dict(path=name, url=url, sha256=hashlib.sha256(data).hexdigest()))
    (dest / 'sources.json').write_text(json.dumps(dict(
        repository='https://github.com/lcapossio/mjpegZero', commit=COMMIT,
        license='Apache-2.0 WITH Commons Clause v1.0; see LICENSE',
        modifications=[], files=records), indent=2) + '\n', encoding='utf-8')
    print('Pinned JPEG reference installed:', dest)


if __name__ == '__main__':
    main()
