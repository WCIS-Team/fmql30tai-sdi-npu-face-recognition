"""Verify JPEG's real DDR path, bus arbitration, CDC, bounds, and golden JPEG."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
OUT=Path('D:/yzd/tmp/pl-jpeg-board-20261016/verification')

def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--bench',type=Path,default=ROOT/'sim/tb_jpeg_customop.sv')
    args=parser.parse_args()
    if args.out is not None:
        OUT=args.out.resolve()
        if not OUT.is_relative_to(Path('D:/yzd/tmp').resolve()):raise ValueError('Use private task output')
    OUT.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,'D:/yzd/tmp/pl-jpeg-20261016/upstream/python')
    from yuyv_convert import rtl_rgb_to_ycbcr_planes
    from jpeg_encoder import encode_jpeg_from_planes
    from verify_rtl_sim import _decode_coefficients
    files=[ROOT/'rtl'/n for n in ('wcis_recording_customop.v','wcis_native_write_commit.v','wcis_jpeg_customop.v','wcis_jpeg_compressor.v',
        'wcis_face_customop.v','wcis_cdc_mailbox.v','wcis_face_preprocess.v','wcis_affine_sampler.v','wcis_pixel_read_axi.v')]
    files+=list((ROOT/'rtl/vendor/mjpegzero/rtl').glob('*.v'))
    files+=[ROOT/'case/rtl/adder_op'/n for n in ('adder_top.v','adder.v','reg_ctrl.v','dma.v','pulse_cross.v')]
    files+=list((ROOT/'case/rtl/adder_op/AVR').glob('*.v'))
    files+=[args.bench]
    exe=OUT/'sim.vvp'
    r=subprocess.run(['iverilog','-g2012','-Wall','-s',args.bench.stem,'-o',str(exe),*map(str,files)],capture_output=True,text=True)
    (OUT/'compile.log').write_text(r.stdout+r.stderr)
    if r.returncode: raise RuntimeError(r.stderr)
    w,h=64,16
    yy,xx=np.mgrid[:h,:w]
    images=[np.stack((xx*255//(w-1),yy*255//(h-1),(xx*3+yy*7)%256),2).astype(np.uint8),
            np.random.default_rng(321).integers(0,256,(h,w,3),dtype=np.uint8)]
    report=dict(cases=[],source_sha256={(str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else str(f)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},board_verified=False)
    for fmt in (0,1):
        out=OUT/f'format{fmt}';out.mkdir(exist_ok=True)
        originals=[]
        for idx,image in enumerate(images):
            rgb=image.astype(np.uint16)
            if fmt==0:
                p=((rgb[:,:,0]>>3)<<11)|((rgb[:,:,1]>>2)<<5)|(rgb[:,:,2]>>3)
                data=p.astype('<u2').view(np.uint8).reshape(-1)
                r5,g6,b5=p>>11,(p>>5)&63,p&31
                original=np.stack(((r5<<3)|(r5>>2),(g6<<2)|(g6>>4),(b5<<3)|(b5>>2)),2).astype(np.uint8)
            else:
                packed=np.zeros((h,w,4),np.uint8);packed[:,:,:3]=image[:,:,::-1]
                data=packed.reshape(-1);original=image
            originals.append(original)
            np.savetxt(out/f'source{idx}.hex',data,fmt='%02x')
        r=subprocess.run(['vvp',str(exe),f'+vectors={out.as_posix()}',f'+format={fmt}'],cwd=out,capture_output=True,text=True,timeout=60)
        (out/'simulation.log').write_text(r.stdout+r.stderr)
        if r.returncode or 'PASS jpeg_customop' not in r.stdout: raise RuntimeError(r.stdout+r.stderr)
        errors=[]
        for idx,original in enumerate(originals):
            data=(out/f'frame{idx}.jpg').read_bytes()
            with Image.open(out/f'frame{idx}.jpg') as image:
                image.load();assert image.size==(w,h);image.save(out/f'decoded{idx}.png')
            ref=encode_jpeg_from_planes(*rtl_rgb_to_ycbcr_planes(original),quality=75)
            actual=_decode_coefficients(data,w*h//128);expected=_decode_coefficients(ref,w*h//128)
            a=np.array([[b['dc'],*b['ac']] for b in actual]);b=np.array([[b['dc'],*b['ac']] for b in expected])
            delta=int(np.max(np.abs(a-b)));assert delta<=1,delta;errors.append(delta)
        report['cases'].append(dict(format=fmt,passed=True,complete_frames=2,coefficient_max_error=max(errors)))
        (OUT/'summary.json').write_text(json.dumps(report,indent=2))
        print(r.stdout,flush=True)
    print('ALL JPEG DDR/CDC TESTS PASSED')
if __name__=='__main__':main()
