"""Compare frozen old/new reader control against identical pixel/protocol goldens.

ModelSim runs large cases; no SDK, model build, board or case-project writes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import cv2
import numpy as np
from verify_face_pl import write_case

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from model_backend.face_geometry import detector_geometry


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline-reader',type=Path,required=True)
    p.add_argument('--baseline-sampler',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--modelsim-bin',type=Path,default=Path('C:/modeltech64_2020.4/win64'))
    a=p.parse_args();out=a.out.resolve()
    if not out.is_relative_to(Path('D:/yzd/tmp').resolve()):raise ValueError('Use a private task directory')
    if out.exists():raise FileExistsError('Use a new verification directory')
    if not cv2.__version__.startswith('4.10.'):raise RuntimeError('Use the pinned OpenCV 4.10 oracle')
    out.mkdir(parents=True)
    report=dict(passed=False,board_verified=False,bitstream_generated=False,variants={},protocol=[],pad=[])
    def save(): (out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    old=Path('D:/yzd/tmp/face-pl-20261015/verification')
    previous=json.loads((old/'verification.json').read_text())
    vectors=out/'vectors';vectors.mkdir()
    for case in previous['cases']:
        dst=vectors/case['name'];dst.mkdir()
        for name in ['source.hex','command.hex','expected.hex']:shutil.copy2(old/case['name']/name,dst/name)
    yy,xx=np.mgrid[:540,:960]
    image=np.stack(((xx*7+yy*13)%256,(xx*17+yy*3)%256,(xx*11+yy*19)%256),2).astype(np.uint8)
    added=[write_case(vectors,'camera_960_rgb565',image,detector_geometry(960,540),rgb565=True),
           write_case(vectors,'camera_960_bgrx',image,detector_geometry(960,540))]
    # Hold source/expected inputs immutable; tb_face_preprocess may write only
    # its actual.hex beneath this task's copied vectors.
    report['vectors_sha256']={str(p.relative_to(out)):sha(p) for p in vectors.glob('*/*.hex')}
    tb=(ROOT/'sim/tb_face_customop.sv').read_text().replace('string directory;','string directory; time job_started;')
    trigger="        write_reg(32'h400c2000,1);\n        write_reg(32'h400c2014,32'hbad);"
    if tb.count(trigger)!=1:raise RuntimeError('Native timing hook no longer matches')
    tb=tb.replace(trigger,"        job_started=$time;\n"+trigger)
    tb=tb.replace('wcis_face_customop dut(.*);','wcis_recording_customop dut(.*);')
    tb=tb.replace('        $display("PASS face_customop','        $display("FASTPATH_METRICS job_ns=%0d native_reads=%0d writes=%0d",$time-job_started,reads,writes);\n        $display("PASS face_customop')
    bench=out/'tb_face_customop.sv';bench.write_text(tb)
    common=[ROOT/'rtl'/n for n in ['wcis_face_preprocess.v','wcis_face_customop.v','wcis_cdc_mailbox.v','wcis_recording_customop.v','wcis_native_write_commit.v','wcis_jpeg_customop.v','wcis_jpeg_compressor.v','wcis_pad_preprocess.v']]
    common+=[ROOT/'case/rtl/adder_op'/n for n in ['adder_top.v','adder.v','reg_ctrl.v','dma.v','pulse_cross.v']]
    common+=sorted((ROOT/'case/rtl/adder_op/AVR').glob('*.v'))+sorted((ROOT/'rtl/vendor/mjpegzero/rtl').glob('*.v'))
    common += [bench,ROOT/'sim/tb_face_preprocess.sv',ROOT/'sim/tb_pad_preprocess.sv',ROOT/'sim/tb_pixel_reader_fast.sv']
    sources=list(dict.fromkeys(common+[a.baseline_reader,a.baseline_sampler,ROOT/'rtl/wcis_pixel_read_axi.v',ROOT/'rtl/wcis_affine_sampler.v']))
    report['source_sha256']={str(x.resolve()):sha(x) for x in sources}
    perf=['camera_960_rgb565','camera_960_bgrx','face_obama','detector_1080p','rotate_border_padding']
    for variant,reader,sampler in [('before',a.baseline_reader,a.baseline_sampler),('reader_only',ROOT/'rtl/wcis_pixel_read_axi.v',a.baseline_sampler),('combined',ROOT/'rtl/wcis_pixel_read_axi.v',ROOT/'rtl/wcis_affine_sampler.v')]:
        directory=out/variant;directory.mkdir()
        r=subprocess.run([str(a.modelsim_bin/'vlib.exe'),'work'],cwd=directory,capture_output=True,text=True);assert r.returncode==0,r.stderr
        r=subprocess.run([str(a.modelsim_bin/'vlog.exe'),'-sv','-timescale','1ns/1ps','-work','work',*map(str,[reader,sampler]+common)],cwd=directory,capture_output=True,text=True)
        (directory/'compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
        def run(top,name,path=None):
            command=[str(a.modelsim_bin/'vsim.exe'),'-c','-onfinish','stop','-lib','work',top,'+poll_gap=256']
            if path:command+=['+vectors='+path.as_posix()]
            command+=['-do','run -all; quit -f']
            start=time.perf_counter();r=subprocess.run(command,cwd=directory,capture_output=True,text=True,timeout=120)
            log=r.stdout+r.stderr;(directory/(name+'.log')).write_text(log)
            if r.returncode or ('PASS '+top.removeprefix('tb_')) not in log:raise RuntimeError(variant+'/'+name+' failed: '+log[-1400:])
            return log,time.perf_counter()-start
        report['variants'][variant]={}
        for name in perf:
            log,seconds=run('tb_face_customop',name,vectors/name)
            match=re.search(r'FASTPATH_METRICS job_ns=(\d+) native_reads=(\d+) writes=(\d+)',log);assert match
            report['variants'][variant][name]=dict(job_ns=int(match[1]),native_reads=int(match[2]),writes=int(match[3]),wall_s=seconds,passed=True)
            save();print(variant,name,match.group(0),flush=True)
        if variant=='combined':
            log,seconds=run('tb_pixel_reader_fast','reader-unit');assert 'checks=105' in log
            report['reader_unit']=dict(passed=True,wall_s=seconds)
            for case in previous['cases']+added:
                name=case['name'];log,seconds=run('tb_face_preprocess','protocol-'+name,vectors/name)
                report['protocol'].append(dict(name=name,passed=True,wall_s=seconds));save()
                print('protocol',name,'PASS',flush=True)
            pad_old=Path('D:/yzd/tmp/minifas-pad-20261018/pl-verification')
            pad_report=json.loads((pad_old/'verification.json').read_text())
            pad_vectors=out/'pad-vectors';pad_vectors.mkdir()
            for case in pad_report['cases']:
                name=case['name'];target=pad_vectors/name;target.mkdir()
                for file in ['command.hex','source.hex','expected.hex']:shutil.copy2(pad_old/name/file,target/file)
                log,seconds=run('tb_pad_preprocess','pad-'+name,target)
                report['pad'].append(dict(name=name,passed=True,wall_s=seconds));save();print('pad',name,'PASS',flush=True)
    report['comparisons']=[]
    for name in perf:
        before=report['variants']['before'][name];after=report['variants']['combined'][name]
        if after['job_ns']>=before['job_ns']:raise RuntimeError('Target workload did not improve: '+name)
        report['comparisons'].append(dict(name=name,before=before,reader_only=report['variants']['reader_only'][name],after=after,
                                         simulated_time_reduction=1-after['job_ns']/before['job_ns']))
    for name,digest in report['source_sha256'].items():
        if sha(Path(name))!=digest:raise RuntimeError('Source changed during verification: '+name)
    for name,digest in report['vectors_sha256'].items():
        if sha(out/name)!=digest:raise RuntimeError('Golden input changed during verification: '+name)
    report['passed']=True;save();print('PASS fastpath native comparisons, protocol faults, PAD and reader edge cases',flush=True)


if __name__=='__main__':main()
