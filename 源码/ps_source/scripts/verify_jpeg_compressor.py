"""Run the actual JPEG RTL, exercise stream failures, decode and check images.

Artifacts/dependencies belong under D:/yzd/tmp. This does not program a board.
--reference is the pinned mjpegZero checkout for its independent software model.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'rtl/vendor/mjpegzero'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=Path('D:/yzd/tmp/pl-jpeg-20261016/verification'))
    p.add_argument('--reference', type=Path, default=Path('D:/yzd/tmp/pl-jpeg-20261016/upstream/python'))
    p.add_argument('--pipelined-fifo', action='store_true', help='Verify preview BRAM FIFO instead of the legacy FWFT path')
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((VENDOR / 'sources.json').read_text())
    for f in manifest['files']:
        assert hashlib.sha256((VENDOR / f['path']).read_bytes()).hexdigest() == f['sha256'], f['path']
    actual_commit = subprocess.check_output(['git', '-C', str(args.reference), 'rev-parse', 'HEAD'], text=True).strip()
    if actual_commit != manifest['commit']:
        raise ValueError('Software reference must match the pinned RTL commit')
    subprocess.run(['git', '-C', str(args.reference), 'diff', '--exit-code', 'HEAD', '--', '.'],
                   check=True, stdout=subprocess.DEVNULL)
    sys.path.insert(0, str(args.reference))
    from yuyv_convert import rtl_rgb_to_ycbcr_planes
    from jpeg_encoder import encode_jpeg_from_planes
    from verify_rtl_sim import _decode_coefficients
    cases = [(64, 16, q, 0, 12) for q in (50, 75, 95)]
    cases += [(128, 24, 75, 0, 8), (64, 16, 75, 1, 5),
              (64, 16, 75, 2, 8), (64, 16, 75, 3, 8)]
    records = []
    for w, h, q, mode, faw in cases:
        name = f'{w}x{h}-q{q}-mode{mode}-fifo{1<<faw}'
        out = args.out / name
        out.mkdir(exist_ok=True)
        rng = np.random.default_rng(1920+w+h)
        yy, xx = np.mgrid[:h, :w]
        ramp = np.stack((xx*255//(w-1), yy*255//(h-1), (xx*3+yy*7)%256), 2).astype(np.uint8)
        noise = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
        words = np.concatenate([ramp, noise], axis=0).astype(np.uint32)
        words = (words[:,:,0]<<16) | (words[:,:,1]<<8) | words[:,:,2]
        np.savetxt(out/'pixels.hex', words.reshape(-1), fmt='%06x')
        cmd = ['iverilog', '-g2012', '-Wall', '-s', 'tb_jpeg_compressor',
               f'-Ptb_jpeg_compressor.W={w}', f'-Ptb_jpeg_compressor.H={h}',
               f'-Ptb_jpeg_compressor.Q={q}', f'-Ptb_jpeg_compressor.FAW={faw}',
               f'-Ptb_jpeg_compressor.PF={int(args.pipelined_fifo)}',
               '-o', str(out/'sim.vvp'), *map(str, (VENDOR/'rtl').glob('*.v')),
               str(ROOT/'rtl/vendor/verilog_ethernet/axis/rtl/axis_fifo.v'),
               str(ROOT/'rtl/wcis_jpeg_compressor.v'), str(ROOT/'sim/tb_jpeg_compressor.sv')]
        compile_run = subprocess.run(cmd, capture_output=True, text=True)
        (out/'compile.log').write_text(compile_run.stdout+compile_run.stderr)
        if compile_run.returncode:
            raise RuntimeError(compile_run.stderr)
        start = time.monotonic()
        sim = subprocess.run(['vvp', str(out/'sim.vvp'), f'+HEX={(out/"pixels.hex").as_posix()}',
                              f'+MODE={mode}'], cwd=out, capture_output=True, text=True, timeout=180)
        (out/'simulation.log').write_text(sim.stdout+sim.stderr)
        if sim.returncode or 'PASS jpeg_compressor' not in sim.stdout:
            raise RuntimeError(name+'\n'+sim.stdout+sim.stderr)
        frames = []
        for ident, count, cycles in re.findall(r'FRAME id=(\d+) bytes=(\d+) cycles=(\d+)', sim.stdout):
            ident = int(ident)
            path = out/f'frame_{ident}.jpg'
            data = path.read_bytes()
            assert len(data) == int(count) and data[:2] == b'\xff\xd8' and data[-2:] == b'\xff\xd9'
            with Image.open(path) as decoded:
                decoded.load()
                assert decoded.size == (w,h)
                decoded.save(out/f'decoded_{ident}.png')
            original = ramp if ident == 101 else noise
            # Software model + independent entropy decoding catch silent lost,
            # duplicated or reordered bytes that SOI/EOI-only checks miss.
            ref = encode_jpeg_from_planes(*rtl_rgb_to_ycbcr_planes(original), quality=q)
            if not isinstance(ref, bytes):
                ref = bytes(ref)
            (out/f'reference_{ident}.jpg').write_bytes(ref)
            actual_blocks = _decode_coefficients(data, w*h//128)
            expected_blocks = _decode_coefficients(ref, w*h//128)
            actual = np.array([[b['dc'], *b['ac']] for b in actual_blocks], dtype=np.int32)
            expected = np.array([[b['dc'], *b['ac']] for b in expected_blocks], dtype=np.int32)
            delta = int(np.max(np.abs(actual-expected)))
            assert delta <= 1, (name, ident, delta)
            frames.append(dict(id=ident, bytes=len(data), cycles=int(cycles), coefficient_max_error=delta,
                               sha256=hashlib.sha256(data).hexdigest()))
        rec = dict(name=name, passed=True, frames=frames, wall_s=time.monotonic()-start)
        records.append(rec)
        print('PASS', name, 'frames=',len(frames), flush=True)
    source_hashes = {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest()
                     for f in (ROOT/'rtl/wcis_jpeg_compressor.v', ROOT/'sim/tb_jpeg_compressor.sv')}
    report = dict(upstream_commit=manifest['commit'], source_sha256=source_hashes, cases=records,
                  pipelined_fifo=args.pipelined_fifo,
                  board_verified=False, bitstream_generated=False)
    (args.out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print('ALL JPEG ADAPTER TESTS PASSED:', len(records))


if __name__ == '__main__':
    main()
