"""Compare the old and new native line cache against the same pixel golden.

No model compilation, board use, case project mutation or bitstream generation.
All generated vectors, baseline copies and logs live in the private --out task.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model_backend.face_geometry import inverse_q16
from verify_face_pl import write_case


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path, help='Unmodified previous wcis_face_customop.v')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.baseline.resolve() == (ROOT / 'rtl/wcis_face_customop.v').resolve():
        parser.error('Baseline must be an independent unchanged snapshot')
    bench_text = (ROOT / 'sim/tb_face_customop.sv').read_text()
    # Two cached source rows must both be invalidated across a new job using
    # the same DDR address. Only this generated testbench has the extra job.
    bench_text = bench_text.replace('string directory;', 'string directory,second_directory; time job_started;')
    bench_text = bench_text.replace('        wait_face();\n        if(status[7:4]!==0',
                                    '        job_started=$time;\n        wait_face();\n        if(status[7:4]!==0', 1)
    marker = '        $display("PASS face_customop'
    extra = '''        $display("CACHE_METRICS native_reads=%0d job_ns=%0d",reads,$time-job_started);
        if($value$plusargs("second_vectors=%s",second_directory)) begin
            $readmemh({second_directory,"/source.hex"},memory,0,memory_words-1);
            $readmemh({second_directory,"/expected.hex"},expected,0,pixels-1);
            write_reg(32'h400c2010,config_words[0]+1);
            write_reg(32'h400c2000,1);wait_face();
            if(status[7:4]!==0) $fatal(1,"second source job failed");
            for(i=0;i<pixels;i=i+1)
                if(memory[out_word+i/2][(i%2)*32 +: 32]!=={8'd0,expected[i]})
                    $fatal(1,"two-row cache stale across frame at pixel %0d",i);
            read_reg(32'h400c2008,readback);
            if(readback!==config_words[0]+1) $fatal(1,"wrong second source frame id");
            $display("PASS both cached source rows invalidated");
        end
'''
    if bench_text.count(marker) != 1:
        raise RuntimeError('Unexpected testbench structure')
    bench = args.out / 'tb_face_customop.sv'
    bench.write_text(bench_text.replace(marker, extra + marker))
    yy, xx = np.mgrid[:16, :64]
    source = np.stack(((xx * 3 + yy * 7) % 256, (xx * 11 + yy * 5) % 256,
                       (xx * 13 + yy * 17) % 256), axis=2).astype(np.uint8)
    geometry = dict(content=(64, 16), canvas=(64, 16), border=0, replicate=True,
                    matrix=inverse_q16([[.5, 0, .25], [0, .5, .25]]))
    vectors = args.out / 'vectors'
    write_case(vectors, 'two_row_bilinear', source, geometry)
    write_case(vectors, 'two_row_changed_source', 255 - source, geometry)
    old_vectors = Path('D:/yzd/tmp/face-pl-20261015/verification')
    cases = [(name, old_vectors / name) for name in (
        'identity_odd_pitch', 'rotate_border_padding', 'rgb565_odd_pitch',
        'cache_new_frame', 'face_obama', 'detector_1080p')]
    cases.insert(0, ('two_row_bilinear', vectors / 'two_row_bilinear'))
    common = [ROOT / 'rtl' / name for name in ('wcis_cdc_mailbox.v',
        'wcis_face_preprocess.v', 'wcis_affine_sampler.v', 'wcis_pixel_read_axi.v')]
    common += [ROOT / 'case/rtl/adder_op' / name for name in ('adder_top.v',
        'adder.v', 'reg_ctrl.v', 'dma.v', 'pulse_cross.v')]
    common += sorted((ROOT / 'case/rtl/adder_op/AVR').glob('*.v'))
    report = dict(board_verified=False, bitstream_generated=False, comparisons=[],
                  baseline_sha256=sha(args.baseline),
                  candidate_sha256=sha(ROOT / 'rtl/wcis_face_customop.v'))
    results = {}
    for variant, module in [('before', args.baseline), ('after', ROOT / 'rtl/wcis_face_customop.v')]:
        output = args.out / variant
        output.mkdir(exist_ok=True)
        files = [module] + common + [bench]
        compiled = subprocess.run(['C:/msys64/ucrt64/bin/iverilog.exe', '-g2012', '-Wall',
            '-s', 'tb_face_customop', '-o', str(output / 'test.vvp')] + [str(p) for p in files],
            capture_output=True, text=True)
        (output / 'compile.log').write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode:
            raise RuntimeError('Cache comparison compilation failed: ' + variant)
        results[variant] = {}
        for name, directory in cases:
            command = ['C:/msys64/ucrt64/bin/vvp.exe', str(output / 'test.vvp'),
                       '+vectors=' + directory.as_posix()]
            if name == 'two_row_bilinear':
                command.append('+second_vectors=' + (vectors / 'two_row_changed_source').as_posix())
            run = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout)
            log = run.stdout + run.stderr
            (output / (name + '.log')).write_text(log)
            if run.returncode or 'PASS face_customop' not in log:
                raise RuntimeError('Cache comparison failed: ' + variant + '/' + name)
            metrics = re.search(r'CACHE_METRICS native_reads=(\d+) job_ns=(\d+)', log)
            if metrics is None:
                raise RuntimeError('Missing cache measurements')
            results[variant][name] = dict(native_reads=int(metrics[1]), job_ns=int(metrics[2]))
            print(json.dumps(dict(variant=variant, case=name, **results[variant][name])), flush=True)
            (args.out / 'progress.json').write_text(json.dumps(results, indent=2))
    for name, _ in cases:
        before, after = results['before'][name], results['after'][name]
        report['comparisons'].append(dict(case=name, before=before, after=after,
            read_reduction_fraction=1 - after['native_reads'] / before['native_reads']))
    targeted = next(row for row in report['comparisons'] if row['case'] == 'two_row_bilinear')
    if targeted['after']['native_reads'] >= targeted['before']['native_reads']:
        raise RuntimeError('Two-row workload did not reduce DDR reads')
    if report['candidate_sha256'] != sha(ROOT / 'rtl/wcis_face_customop.v'):
        raise RuntimeError('Candidate source changed during verification')
    report['passed'] = True
    (args.out / 'verification.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
