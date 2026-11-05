"""Run real FAC1/JPG1 concurrency against a frozen case, without rebuilding PL."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np
from PIL import Image


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--golden-python', type=Path, required=True)
    parser.add_argument('--iverilog', default='C:/msys64/ucrt64/bin/iverilog.exe')
    parser.add_argument('--vvp', default='C:/msys64/ucrt64/bin/vvp.exe')
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(Path('D:/yzd/tmp').resolve()):
        raise ValueError('Use a private task output under D:/yzd/tmp')
    out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.golden_python.resolve()))
    from yuyv_convert import rtl_rgb_to_ycbcr_planes
    from jpeg_encoder import encode_jpeg_from_planes
    from verify_rtl_sim import _decode_coefficients

    root = Path(__file__).resolve().parents[1]
    bench_source = root / 'sim/tb_recording_parallel.sv'
    # Only the private testbench changes. Never patch the frozen candidate RTL.
    bench_text = bench_source.read_text(encoding='utf-8')
    edits = {
        'integer overlap_cycles=0,face_writes=0;':
            'integer overlap_cycles=0,face_writes=0,slow_memory=0;',
        'itf_awready=random_state[2] || random_state[8];':
            'itf_awready=slow_memory ? (random_state[2] && random_state[8]) : (random_state[2] || random_state[8]);',
        'itf_arready=!pending && !itf_rvalid && (random_state[5] || random_state[11]);':
            'itf_arready=!pending && !itf_rvalid && (slow_memory ? (&random_state[8:5]) : (random_state[5] || random_state[11]));',
        'delay_count<=random_state[17:14];':
            'delay_count<=slow_memory ? random_state[20:14] : random_state[17:14];',
        'if(!$value$plusargs("format=%d",format)) format=0;':
            'if(!$value$plusargs("format=%d",format)) format=0;\n'
            '        if(!$value$plusargs("seed=%h",random_state)) random_state=32\'h623eebf7;\n'
            '        if(!$value$plusargs("slow_memory=%d",slow_memory)) slow_memory=0;'
    }
    for old, new in edits.items():
        if bench_text.count(old) != 1:
            raise ValueError('Testbench changed: cannot apply unique stress adaptation: ' + old)
        bench_text = bench_text.replace(old, new)
    bench = out / bench_source.name
    bench.write_text(bench_text, encoding='utf-8')
    rtl = args.case.resolve() / 'rtl/wcis'
    files = [rtl / name for name in (
        'wcis_recording_customop.v', 'wcis_face_customop.v',
        'wcis_face_preprocess.v', 'wcis_affine_sampler.v', 'wcis_pixel_read_axi.v',
        'wcis_cdc_mailbox.v', 'wcis_jpeg_customop.v', 'wcis_jpeg_compressor.v')]
    files += sorted((rtl / 'jpeg_vendor').glob('*.v'))
    adder = args.case.resolve() / 'rtl/adder_op'
    files += [adder / name for name in ('adder_top.v', 'adder.v', 'reg_ctrl.v', 'dma.v', 'pulse_cross.v')]
    files += sorted((adder / 'AVR').glob('*.v'))
    files.append(bench)
    hashes = {str(f): sha(f) for f in files}
    exe = out / 'sim.vvp'
    proc = subprocess.run([args.iverilog, '-g2012', '-Wall', '-s', bench.stem,
                           '-o', str(exe), *map(str, files)], capture_output=True, text=True, timeout=120)
    (out / 'compile.log').write_text(proc.stdout + proc.stderr, encoding='utf-8')
    if proc.returncode:
        raise RuntimeError('Compilation failed; see compile.log')
    w, h = 64, 16
    yy, xx = np.mgrid[:h, :w]
    images = [np.stack((xx*255//(w-1), yy*255//(h-1), (xx*3+yy*7)%256), 2).astype(np.uint8),
              np.random.default_rng(321).integers(0, 256, (h, w, 3), dtype=np.uint8)]
    report = dict(passed=False, board_verified=False, simulation_dimensions=[w, h],
                  source_sha256=hashes, upstream_bench_sha256=sha(bench_source),
                  runner_sha256=sha(Path(__file__)), cases=[],
                  scope='Finite concurrent FAC1/JPG1 jobs; not a fairness or board throughput proof',
                  golden_sha256={str(p): sha(p) for p in sorted(args.golden_python.glob('*.py'))})
    for fmt in (0, 1):
        for profile, seed, slow in (('normal', '623eebf7', 0), ('slow_ddr', 'd1cebeef', 1)):
            work = out / f'format{fmt}_{profile}'
            work.mkdir()
            originals = []
            for idx, image in enumerate(images):
                rgb = image.astype(np.uint16)
                if fmt == 0:
                    p = ((rgb[:, :, 0] >> 3) << 11) | ((rgb[:, :, 1] >> 2) << 5) | (rgb[:, :, 2] >> 3)
                    data = p.astype('<u2').view(np.uint8).reshape(-1)
                    r, g, b = p >> 11, (p >> 5) & 63, p & 31
                    original = np.stack(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)), 2).astype(np.uint8)
                else:
                    packed = np.zeros((h, w, 4), np.uint8)
                    packed[:, :, :3] = image[:, :, ::-1]
                    data, original = packed.reshape(-1), image
                originals.append(original)
                np.savetxt(work / f'source{idx}.hex', data, fmt='%02x')
            proc = subprocess.run([args.vvp, str(exe), f'+vectors={work.as_posix()}',
                                   f'+format={fmt}', f'+seed={seed}', f'+slow_memory={slow}'],
                                  cwd=work, capture_output=True, text=True, timeout=120)
            log = proc.stdout + proc.stderr
            (work / 'simulation.log').write_text(log, encoding='utf-8')
            if proc.returncode or 'PASS jpeg_customop' not in log:
                raise RuntimeError(f'Concurrent regression failed: {work}\n{log[-1800:]}')
            overlaps = list(map(int, re.findall(r'REAL_CORE_OVERLAP cycles=(\d+)', log)))
            if len(overlaps) != 2 or min(overlaps) <= 0:
                raise RuntimeError('Actual core overlap not established')
            errors = []
            for idx, original in enumerate(originals):
                data = (work / f'frame{idx}.jpg').read_bytes()
                with Image.open(work / f'frame{idx}.jpg') as decoded:
                    decoded.load()
                    if decoded.size != (w, h):
                        raise ValueError('JPEG dimensions differ')
                expected = encode_jpeg_from_planes(*rtl_rgb_to_ycbcr_planes(original), quality=75)
                actual_coeff = _decode_coefficients(data, w*h//128)
                expected_coeff = _decode_coefficients(expected, w*h//128)
                a = np.array([[b['dc'], *b['ac']] for b in actual_coeff])
                b = np.array([[b['dc'], *b['ac']] for b in expected_coeff])
                if a.shape != b.shape:
                    raise ValueError('JPEG block count differs')
                delta = int(np.max(np.abs(a - b)))
                if delta > 1:
                    raise ValueError(f'JPEG golden coefficient error: {delta}')
                errors.append(delta)
            case = dict(format=fmt, profile=profile, seed=seed, passed=True, frames=2,
                        overlap_cycles=overlaps, coefficient_max_error=max(errors),
                        log_sha256=sha(work / 'simulation.log'))
            report['cases'].append(case)
            (out / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(case), flush=True)
    if any(sha(Path(p)) != value for p, value in hashes.items()):
        raise RuntimeError('Source changed while simulating')
    report['passed'] = True
    (out / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PASS frozen candidate concurrent FAC1/JPG1, both formats and DDR stress')


if __name__ == '__main__':
    main()
