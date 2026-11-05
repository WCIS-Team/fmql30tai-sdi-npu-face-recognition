"""Read-only verification of a portable candidate/rollback bundle. Never flashes."""
import argparse
import array
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
from verify_jpeg_boot import partitions


def verify(root):
    root = root.resolve()
    manifest = json.loads((root / 'release-manifest.json').read_text(encoding='utf-8'))
    if manifest['deployed'] or manifest['board_verified'] or manifest['production_timing_signoff']:
        raise ValueError('Offline bundle cannot claim deployment/board/timing signoff')
    expected_files = manifest['files']
    actual_files = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual_files != set(expected_files) | {'release-manifest.json'}:
        raise ValueError('Bundle file set differs from manifest')
    for name, item in expected_files.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Bundle entry escapes root')
        data = path.read_bytes()
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Integrity check failed: ' + name)
    before = (root / 'rollback/BOOT.bin').read_bytes()
    boot = (root / 'candidate/BOOT.bin').read_bytes()
    old, new = partitions(before), partitions(boot)
    if any(old[i]['sha256'] != new[i]['sha256'] or old[i]['bytes'] != new[i]['bytes'] for i in (0, 2, 3)):
        raise ValueError('PS partitions differ from rollback image')
    if old[1]['sha256'] == new[1]['sha256']:
        raise ValueError('Candidate does not contain a new PL payload')
    bit = (root / 'candidate/ai7030_edif_top.bit').read_bytes()
    offset = 2 + struct.unpack_from('>H', bit)[0]
    if struct.unpack_from('>H', bit, offset)[0] != 1:
        raise ValueError('Invalid bit header')
    offset += 2
    while True:
        tag = chr(bit[offset])
        offset += 1
        if tag == 'e':
            size = struct.unpack_from('>I', bit, offset)[0]
            offset += 4
            payload = bit[offset:offset+size]
            if offset + size != len(bit):
                raise ValueError('Invalid bit payload extent')
            break
        if tag not in 'abcd':
            raise ValueError('Unknown bit header tag')
        length = struct.unpack_from('>H', bit, offset)[0]
        offset += 2 + length
    words = array.array('I', payload)
    if sys.byteorder == 'little':
        words.byteswap()
    pl = new[1]
    raw = boot[pl['offset']:pl['offset']+pl['bytes']]
    if raw[:len(payload)] != words.tobytes() or raw[len(payload):] not in (b'', bytes.fromhex('00000020')):
        raise ValueError('BOOT PL payload differs from included bit')
    return dict(passed=True, files=len(expected_files), ps_partitions_identical=True,
                current_bit_payload_matches=True, board_verified=False, deployed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    print(json.dumps(verify(args.bundle), indent=2))


if __name__ == '__main__':
    main()
