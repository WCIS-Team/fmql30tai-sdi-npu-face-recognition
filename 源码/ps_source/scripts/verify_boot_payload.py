"""Prove that BOOT's PL partition contains this build's patched bit payload."""
from pathlib import Path
from array import array
import struct
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / 'outputs/release-candidate'
bit = (out / 'ai7030_edif_top.bit').read_bytes()
boot = (out / 'BOOT.bin').read_bytes()
position = 2 + struct.unpack_from('>H', bit)[0]
assert struct.unpack_from('>H', bit, position)[0] == 1
position += 2
metadata = {}
while True:
    tag = chr(bit[position]); position += 1
    if tag == 'e':
        length = struct.unpack_from('>I', bit, position)[0]; position += 4
        payload = bit[position:position+length]
        assert position + length == len(bit)
        break
    assert tag in 'abcd'
    length = struct.unpack_from('>H', bit, position)[0]; position += 2
    metadata[tag] = bit[position:position+length].decode(errors='replace').rstrip('\0')
    position += length
assert struct.unpack_from('<I', boot, 0x24)[0] == 0x464d5348, 'Not an FMSH boot image'
table = struct.unpack_from('<I', boot, 0x98)[0]
assert struct.unpack_from('<I', boot, table + 4)[0] == 4, 'Expected FSBL, PL, BL31, U-Boot'
header = struct.unpack_from('<I', boot, table + 8)[0] * 4
header = struct.unpack_from('<I', boot, header + 12)[0] * 4
pl_size = struct.unpack_from('<I', boot, header)[0] * 4
pl_offset = struct.unpack_from('<I', boot, header + 32)[0] * 4
words = array('I', payload)
assert words.itemsize == 4
words.byteswap()
assert pl_size >= len(payload)
assert boot[pl_offset:pl_offset+len(payload)] == words.tobytes(), 'BOOT contains a different bitstream'
padding = boot[pl_offset+len(payload):pl_offset+pl_size]
# Procise appends a configuration NOP word after the bit payload.
assert padding in (b'', bytes.fromhex('00000020')), 'Unexpected PL partition suffix'
result = {'boot_size':len(boot), 'boot_sha256':hashlib.sha256(boot).hexdigest(),
          'patched_bit_sha256':hashlib.sha256(bit).hexdigest(), 'bit_metadata':metadata,
          'pl_partition_offset':pl_offset, 'pl_partition_bytes':pl_size,
          'bit_payload_bytes':len(payload), 'pl_partition_suffix_hex':padding.hex(),
          'payload_matches_after_32bit_byte_swap':True,
          'packaged_partitions':['FSBL','PL','BL31','U-Boot'],
          'timing_passed':False, 'deployed':False, 'board_verified':False}
(out / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print('PASS BOOT payload: exact patched bit contents, four partitions, FMSH header.')
print('BOOT SHA256: ' + result['boot_sha256'])
