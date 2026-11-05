"""Measure the real JPEG RTL's cycles and compressed size; never board FPS.

Use a pinned reference checkout (for its testbench) and generated files in tmp.
Video input is decoded on the PC for simulation only, never for FPGA encoding.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'rtl/vendor/mjpegzero'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--width', type=int, default=1920)
    p.add_argument('--height', type=int, default=1080)
    p.add_argument('--quality', type=int, default=75)
    p.add_argument('--pattern', choices=['gradient', 'noise', 'flat'], default='gradient')
    source = p.add_mutually_exclusive_group()
    source.add_argument('--image', type=Path)
    source.add_argument('--video', type=Path)
    p.add_argument('--frame-index', type=int, default=200)
    p.add_argument('--out', type=Path, default=Path('D:/yzd/tmp/pl-jpeg-20261016/benchmarks'))
    p.add_argument('--reference', type=Path, default=Path('D:/yzd/tmp/pl-jpeg-20261016/upstream'))
    a = p.parse_args()
    if a.width < 16 or a.width % 16 or a.height < 8 or a.height % 8 or not 1 <= a.quality <= 100:
        p.error('Need width multiple of 16, height multiple of 8, quality 1..100')
    manifest = json.loads((VENDOR/'sources.json').read_text())
    commit = subprocess.check_output(['git','-C',str(a.reference),'rev-parse','HEAD'],text=True).strip()
    if commit != manifest['commit']:
        raise ValueError('Unpinned reference checkout')
    subprocess.run(['git','-C',str(a.reference),'diff','--exit-code','HEAD','--','sim/tb_iverilog.sv'],
                   check=True,stdout=subprocess.DEVNULL)
    for f in manifest['files']:
        if hashlib.sha256((VENDOR/f['path']).read_bytes()).hexdigest()!=f['sha256']:
            raise ValueError('Modified vendor source: '+f['path'])
    native_shape = None
    if a.image:
        original = Image.open(a.image).convert('RGB')
        native_shape = list(original.size)
        image = np.array(original.resize((a.width,a.height)))
        note = str(a.image)
    elif a.video:
        import cv2
        cap = cv2.VideoCapture(str(a.video))
        cap.set(cv2.CAP_PROP_POS_FRAMES,a.frame_index)
        ok,bgr = cap.read(); cap.release()
        if not ok:
            raise ValueError('Video frame not available')
        native_shape = [bgr.shape[1],bgr.shape[0]]
        image = cv2.cvtColor(cv2.resize(bgr,(a.width,a.height)),cv2.COLOR_BGR2RGB)
        note = str(a.video)+f' frame {a.frame_index}'
    elif a.pattern=='noise':
        image=np.random.default_rng(123).integers(0,256,(a.height,a.width,3),dtype=np.uint8)
        note='seeded independent RGB noise'
    elif a.pattern=='flat':
        image=np.full((a.height,a.width,3),128,np.uint8)
        note='uniform gray'
    else:
        yy,xx=np.mgrid[:a.height,:a.width]
        image=np.stack((xx*255//max(a.width-1,1),yy*255//max(a.height-1,1),(xx+yy)%256),2).astype(np.uint8)
        note='synthetic color ramp'
    name = 'video' if a.video else 'image' if a.image else a.pattern
    out = a.out/f'{name}-{a.width}x{a.height}-q{a.quality}'
    out.mkdir(parents=True,exist_ok=True)
    Image.fromarray(image).save(out/'input.png')
    words=(image[:,:,0].astype(np.uint32)<<16)|(image[:,:,1].astype(np.uint32)<<8)|image[:,:,2]
    np.savetxt(out/'pixels.hex',words.reshape(-1),fmt='%06x')
    cmd=['iverilog','-g2012','-s','tb_iverilog','-DLITE_MODE','-DRGB_INPUT',
         f'-DLITE_QUALITY={a.quality}',f'-DTEST_QUALITY={a.quality}',
         f'-DTB_IMG_WIDTH={a.width}',f'-DTB_IMG_HEIGHT={a.height}',
         f'-DTV_HEX_FILE="{(out/"pixels.hex").as_posix()}"','-o',str(out/'sim.vvp'),
         *map(str,(VENDOR/'rtl').glob('*.v')),str(a.reference/'sim/tb_iverilog.sv')]
    result=subprocess.run(cmd,capture_output=True,text=True)
    (out/'compile.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr)
    start=time.monotonic()
    result=subprocess.run(['vvp',str(out/'sim.vvp')],cwd=out,capture_output=True,text=True,timeout=1800)
    (out/'simulation.log').write_text(result.stdout+result.stderr)
    if result.returncode or 'ALL TESTS PASSED' not in result.stdout:
        raise RuntimeError(result.stdout[-2000:]+result.stderr)
    jpeg=(out/'sim_output.jpg').read_bytes()
    if jpeg[:2]!=b'\xff\xd8' or jpeg[-2:]!=b'\xff\xd9':
        raise ValueError('Missing JPEG SOI/EOI')
    with Image.open(out/'sim_output.jpg') as decoded:
        decoded.load()
        if decoded.size!=(a.width,a.height):
            raise ValueError('Wrong decoded dimensions')
        decoded.save(out/'decoded.png')
        reconstructed=np.array(decoded.convert('RGB'))
    t0=int(re.search(r'\[(\d+)\] Feeding frame',result.stdout)[1])
    t1=int(re.search(r'\[(\d+)\] Frame 0 complete',result.stdout)[1])
    cycles=(t1-t0)//10000
    mse=float(np.mean((image.astype(np.float64)-reconstructed)**2))
    rec=dict(width=a.width,height=a.height,quality=a.quality,input_note=note,
             native_source_size=native_shape,resized=native_shape is not None and native_shape!=[a.width,a.height],
             bytes=len(jpeg),rgb_bytes=int(image.size),rgb565_bytes=a.width*a.height*2,
             compression_rgb=float(image.size/len(jpeg)),cycles=cycles,
             hypothetical_fps_at_100mhz=1e8/cycles,at_20fps_MB_s=len(jpeg)*20/1e6,
             psnr_rgb=None if mse==0 else float(10*np.log10(255**2/mse)),
             simulation_wall_s=time.monotonic()-start,upstream_commit=commit,
             jpeg_sha256=hashlib.sha256(jpeg).hexdigest(),board_verified=False)
    (out/'result.json').write_text(json.dumps(rec,indent=2)+'\n')
    print(json.dumps(rec,indent=2))


if __name__=='__main__':
    main()
