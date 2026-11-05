"""Exercise the vendor bus + real adder + ModelBackend under asynchronous clocks."""
import hashlib
import argparse
import json
from pathlib import Path
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
OUT=Path('D:/yzd/tmp/face-pl-integration-20261015/customop-sim')


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recording',action='store_true',help='Run the same face/adder tests through the JPEG shared-port wrapper')
    parser.add_argument('--resume',action='store_true',help='Reuse successful cases only when every RTL/TB SHA is unchanged')
    parser.add_argument('--timeout',type=int,default=300)
    parser.add_argument('--out',type=Path,help='Isolated verification directory under D:/yzd/tmp')
    parser.add_argument('--cases',nargs='+',choices=['identity_odd_pitch','rotate_border_padding','rgb565_odd_pitch','cache_new_frame','face_obama','detector_1080p'])
    parser.add_argument('--verified-writes',action='store_true',help='Enable candidate write visibility bridge; requires --recording')
    parser.add_argument('--poll-gap',type=int,default=0,help='Simulation-only GP cycles between completion polls')
    parser.add_argument('--simulator',choices=['iverilog','modelsim'],default='iverilog')
    parser.add_argument('--modelsim-bin',type=Path,default=Path('C:/modeltech64_2020.4/win64'))
    parser.add_argument('--posted-write-cycles',type=int,default=0,help='Simulation-only native acceptance to memory-visibility delay')
    args=parser.parse_args()
    if args.verified_writes and not args.recording:parser.error('--verified-writes requires --recording')
    if args.poll_gap<0:parser.error('--poll-gap must be nonnegative')
    if args.posted_write_cycles<0 or (args.posted_write_cycles and not args.verified_writes):parser.error('Posted-write pass regression requires --verified-writes and nonnegative delay')
    if args.recording:OUT=Path('D:/yzd/tmp/pl-jpeg-board-20261016/face-regression')
    if args.out:
        OUT=args.out.resolve()
        if not OUT.is_relative_to(Path('D:/yzd/tmp').resolve()):raise ValueError('Use private task output')
    OUT.mkdir(parents=True,exist_ok=True)
    if not args.resume:(OUT/'verification.json').unlink(missing_ok=True)
    files=[ROOT/'rtl'/name for name in ['wcis_cdc_mailbox.v','wcis_face_customop.v',
        'wcis_face_preprocess.v','wcis_affine_sampler.v','wcis_pixel_read_axi.v']]
    files += [ROOT/'case/rtl/adder_op'/name for name in ['adder_top.v','adder.v','reg_ctrl.v','dma.v','pulse_cross.v']]
    files += sorted((ROOT/'case/rtl/adder_op/AVR').glob('*.v'))
    if args.recording:
        files += [ROOT/'rtl'/n for n in ['wcis_recording_customop.v','wcis_native_write_commit.v','wcis_jpeg_customop.v','wcis_jpeg_compressor.v']]
        files += sorted((ROOT/'rtl/vendor/mjpegzero/rtl').glob('*.v'))
        bench=OUT/'tb_face_customop.sv'
        text=(ROOT/'sim/tb_face_customop.sv').read_text()
        if args.posted_write_cycles:
            from verify_native_write_commit import deferred
            text=deferred(text,True).replace('write_remaining<=100;',f'write_remaining<={args.posted_write_cycles};')
            # Factory adder DONE precedes its write drain. Wait for the model's
            # last posted write before restoring the source, without changing RTL.
            text=text.replace('repeat(20) @(negedge ra_clk);','wait(writes==16); @(negedge clk); wait(!write_pending); repeat(2) @(negedge ra_clk);')
        assert text.count('wcis_face_customop dut(.*);')==1
        bench.write_text(text.replace('wcis_face_customop dut(.*);',f'wcis_recording_customop #(.VERIFY_NATIVE_WRITES({int(args.verified_writes)})) dut(.*);'))
        files += [bench]
    else:files += [ROOT/'sim/tb_face_customop.sv']
    hashes={(str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    if args.simulator=='modelsim':
        library=OUT/'work'
        if not library.exists():
            subprocess.run([str(args.modelsim_bin/'vlib.exe'),str(library)],cwd=OUT,check=True,capture_output=True)
        compile_command=[str(args.modelsim_bin/'vlog.exe'),'-sv','-timescale','1ns/1ps','-work',str(library),*map(str,files)]
    else:
        compile_command=['C:/msys64/ucrt64/bin/iverilog.exe','-g2012','-Wall','-s','tb_face_customop','-o',str(OUT/'customop.vvp'),*map(str,files)]
    result=subprocess.run(compile_command,cwd=OUT,capture_output=True,text=True)
    (OUT/'compile.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(result.stderr)
    report=dict(board_verified=False,bitstream_generated=False,source_sha256=hashes,cases=[],verified_writes=args.verified_writes,poll_gap=args.poll_gap,simulator=args.simulator,posted_write_cycles=args.posted_write_cycles)
    if args.resume and (OUT/'verification.json').exists():
        previous=json.loads((OUT/'verification.json').read_text())
        if previous['source_sha256']!=hashes or previous.get('poll_gap',0)!=args.poll_gap or previous.get('simulator','iverilog')!=args.simulator:raise RuntimeError('Cannot resume: RTL/TB source, polling or simulator changed')
        report=previous
    report['all_requested_passed']=False
    for name in args.cases or ['identity_odd_pitch','rotate_border_padding','rgb565_odd_pitch','cache_new_frame','face_obama','detector_1080p']:
        if any(c['name']==name and c['passed'] for c in report['cases']):
            print('Reusing unchanged successful case:',name,flush=True);continue
        directory=Path('D:/yzd/tmp/face-pl-20261015/verification')/name
        plusargs=['+vectors='+directory.as_posix(),'+poll_gap='+str(args.poll_gap),'+progress_every=1000000']
        command=([str(args.modelsim_bin/'vsim.exe'),'-c','-onfinish','stop','-lib','work','tb_face_customop',*plusargs,'-do','run -all; quit -f']
                 if args.simulator=='modelsim' else ['C:/msys64/ucrt64/bin/vvp.exe','-i',str(OUT/'customop.vvp'),*plusargs])
        report['cases']=[c for c in report['cases'] if c['name']!=name]
        started=time.perf_counter()
        try:
            result=subprocess.run(command,cwd=OUT,capture_output=True,text=True,timeout=args.timeout)
        except subprocess.TimeoutExpired as error:
            partial=(error.stdout or b'')
            if isinstance(partial,bytes):partial=partial.decode(errors='replace')
            (OUT/(name+'.log')).write_text(partial+'\nSimulation wall-clock timeout; no functional verdict.\n')
            report['cases'].append(dict(name=name,passed=False,incomplete=True,reason='simulation_wall_clock_timeout',timeout_s=args.timeout))
            (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
            raise RuntimeError('Simulation exceeded wall-clock budget: '+name) from error
        text=result.stdout+result.stderr;(OUT/(name+'.log')).write_text(text)
        print(name,'\n'.join(line for line in text.splitlines() if 'PASS face_customop' in line or 'PROGRESS ' in line or 'FATAL' in line),flush=True)
        passed=result.returncode==0 and 'PASS face_customop' in text
        report['cases'].append(dict(name=name,passed=passed,simulation_wall_s=time.perf_counter()-started))
        (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
        if not passed:raise RuntimeError('Failed CustomOp integration test: '+name)
    if any(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h for p,h in hashes.items()):
        raise RuntimeError('Sources changed while verification was running')
    report['all_requested_passed']=True
    (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS all requested CustomOp integration cases')


if __name__=='__main__':main()
