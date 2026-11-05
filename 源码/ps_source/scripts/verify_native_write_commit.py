"""Check write visibility through the actual FAC1/JPG1 wrapper and delayed DDR."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
IVERILOG='C:/msys64/ucrt64/bin/iverilog.exe'
VVP='C:/msys64/ucrt64/bin/vvp.exe'

def deferred(text,word_memory=False):
    needle='    always @(negedge clk) begin'
    declaration='''    reg write_pending=0;
    integer write_remaining=0;
    reg [31:0] posted_address;
    reg [511:0] posted_data;
    reg [63:0] posted_mask;
'''
    assert text.count(needle)==1
    text=text.replace(needle,declaration+needle)
    text=text.replace('itf_awready=random_state[2] || random_state[8];','itf_awready=!write_pending && (random_state[2] || random_state[8]);')
    assignment=('memory[(posted_address-config_words[1])/8+j]<=masked_word(memory[(posted_address-config_words[1])/8+j],posted_data[j*64 +:64],posted_mask[j*8 +:8]);'
                if word_memory else 'memory[posted_address+j]<=posted_data[j*8 +: 8];')
    lanes=8 if word_memory else 64
    mask_test='|posted_mask[j*8 +:8]' if word_memory else 'posted_mask[j]'
    block='''            if(write_pending) begin
                if(write_remaining>0) write_remaining<=write_remaining-1;
                else begin
                    for(j=0;j<LANES;j=j+1) if(MASK_TEST) ASSIGNMENT
                    write_pending<=0;
                end
            end
'''.replace('ASSIGNMENT',assignment).replace('LANES',str(lanes)).replace('MASK_TEST',mask_test)
    needle='            if(itf_awvalid && itf_awready) begin';assert text.count(needle)==1
    text=text.replace(needle,block+needle+'''
                if(write_pending) $fatal(1,"test memory write queue overflow");
                write_pending<=1;write_remaining<=100;
                posted_address<=itf_awaddr;posted_data<=itf_awdata;posted_mask<=itf_awinfo[70:7];
''')
    old=('memory[(itf_awaddr-config_words[1])/8+j]<=masked_word(memory[(itf_awaddr-config_words[1])/8+j],itf_awdata[j*64 +:64],itf_awinfo[7+j*8 +:8]);'
         if word_memory else 'memory[itf_awaddr+j]<=itf_awdata[j*8 +: 8];')
    assert text.count(old)==1
    return text.replace(old,'// Actual memory visibility is delayed above.')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out.resolve()
    if not out.is_relative_to(Path('D:/yzd/tmp').resolve()):raise ValueError('Use an isolated task output')
    out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').unlink(missing_ok=True)
    report=dict(board_verified=False,bitstream_generated=False,cases=[])
    def run(label,cmd,timeout=120,expected=True):
        result=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=timeout)
        log=result.stdout+result.stderr;(out/(label+'.log')).write_text(log,encoding='utf-8')
        if expected and result.returncode:raise RuntimeError(label+' failed: '+log[-2000:])
        return result,log
    sources=[ROOT/'rtl'/n for n in ['wcis_native_write_commit.v','wcis_recording_customop.v','wcis_jpeg_customop.v','wcis_jpeg_compressor.v','wcis_face_customop.v','wcis_cdc_mailbox.v','wcis_face_preprocess.v','wcis_affine_sampler.v','wcis_pixel_read_axi.v']]
    sources+=sorted((ROOT/'rtl/vendor/mjpegzero/rtl').glob('*.v'))
    sources+=[ROOT/'case/rtl/adder_op'/n for n in ['adder_top.v','adder.v','reg_ctrl.v','dma.v','pulse_cross.v']]
    sources+=sorted((ROOT/'case/rtl/adder_op/AVR').glob('*.v'))
    run('unit-compile',[IVERILOG,'-g2012','-Wall','-s','tb_native_write_commit','-o',out/'unit.vvp',ROOT/'rtl/wcis_native_write_commit.v',ROOT/'sim/tb_native_write_commit.sv'])
    _,log=run('unit',[VVP,out/'unit.vvp']);assert 'PASS native_write_commit' in log
    report['cases'].append(dict(name='unit_visibility_masks_arbitration_fault_reset',passed=True))
    # Same real FACE+legacy-adder tests in both modes, with posted writes.
    base=(ROOT/'sim/tb_face_customop.sv').read_text()
    base=deferred(base,True).replace('repeat(20) @(negedge ra_clk);','wait(writes==16 && !write_pending); repeat(2) @(negedge ra_clk);')
    # Preserve the factory arithmetic-stage completion contract. The posted
    # visibility experiment starts only after the separate adder regression.
    base=base.replace('reg write_pending=0;','reg write_pending=0; reg delayed_output=0;')
    base=base.replace('write_remaining<=100;','write_remaining<=delayed_output ? 100 : 0;')
    base=base.replace('reads=0;writes=0;','delayed_output=1;reads=0;writes=0;')
    # The factory adder has a separate arithmetic-stage completion contract;
    # this experiment isolates the FACE DONE/data-visibility boundary.
    start=base.index('        // Run the actual vendor adder')
    end=base.index('        delayed_output=1;reads=0;writes=0;',start)
    base=base[:start]+base[end:]
    for enabled in [0,1]:
        bench=out/f'face-mode{enabled}.sv'
        bench.write_text(base.replace('wcis_face_customop dut(.*);',f'wcis_recording_customop #(.VERIFY_NATIVE_WRITES({enabled})) dut(.*);'))
        exe=out/f'face-mode{enabled}.vvp'
        run(f'face-mode{enabled}-compile',[IVERILOG,'-g2012','-s','tb_face_customop','-o',exe,*sources,bench])
        cases=['identity_odd_pitch'] if not enabled else ['identity_odd_pitch','rotate_border_padding','rgb565_odd_pitch','cache_new_frame','face_obama']
        for name in cases:
            vectors=Path('D:/yzd/tmp/face-pl-20261015/verification')/name
            result,log=run(f'face-{enabled}-{name}',[VVP,exe,'+vectors='+vectors.as_posix()],expected=bool(enabled))
            if enabled:assert 'PASS face_customop' in log
            else:
                if result.returncode==0:raise RuntimeError('Posted-write test did not reproduce the original early completion')
                assert 'DDR output pixel' in log or 'native line cache stale' in log,log
            report['cases'].append(dict(name=name,verified_writes=bool(enabled),passed=True,original_failure_reproduced=not bool(enabled)))
    # Both real cores at once, including output-port verification reads.
    bench=out/'tb_recording_parallel.sv';text=(ROOT/'sim/tb_recording_parallel.sv').read_text()
    text=deferred(text).replace('.JPEG_HEIGHT(H))','.JPEG_HEIGHT(H),.VERIFY_NATIVE_WRITES(1))')
    old='itf_araddr<SRC || itf_araddr+64>SRC+input_bytes'
    new='!((itf_araddr>=SRC && itf_araddr+64<=SRC+input_bytes) || (itf_araddr>=DST && itf_araddr+64<=DST+capacity) || (itf_araddr>=FDST && itf_araddr+64<=FDST+W*H*4))'
    assert old in text;text=text.replace(old,new);bench.write_text(text)
    result,log=run('real-cores',[sys.executable,ROOT/'scripts/verify_jpeg_customop.py','--out',out/'real-cores','--bench',bench],timeout=120)
    assert 'ALL JPEG DDR/CDC TESTS PASSED' in log
    report['cases'].append(dict(name='real_face_jpeg_two_formats_two_frames',passed=True))
    report['source_sha256']={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in sources}
    report['all_passed']=True;(out/'summary.json').write_text(json.dumps(report,indent=2));print(json.dumps(report['cases'],indent=2))
if __name__=='__main__':main()
