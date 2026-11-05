"""Verify actual PAD RTL against OpenCV and pinned upstream crop geometry."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from model_backend.face_pad import plan_crops, PadCrop, UPSTREAM_COMMIT
from verify_face_pl import expected_remap


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--reference',type=Path,required=True,help='Collected school-results with pinned source/manifest/samples')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve()
    if not out.is_relative_to(Path('D:/yzd/tmp').resolve()):raise ValueError('Use a private task output')
    out.mkdir(parents=True,exist_ok=True)
    if not cv2.__version__.startswith('4.10.'):raise RuntimeError('Use pinned OpenCV 4.10')
    manifest=json.loads((args.reference/'reference-manifest.json').read_text())
    assert manifest['commit']==UPSTREAM_COMMIT
    source=args.reference/'reference/src/generate_patches.py'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['files']['src/generate_patches.py']
    spec=importlib.util.spec_from_file_location('official_pad_crop',source)
    upstream=importlib.util.module_from_spec(spec);spec.loader.exec_module(upstream)
    cropper=upstream.CropImage();cases=[]
    def add(name,image,crop,fault=0,official=None):
        directory=out/name;directory.mkdir(exist_ok=True)
        h,w=image.shape[:2];pitch=((w*4+7)//8)*8
        storage=np.zeros((h,pitch),np.uint8)
        pixels=np.zeros((h,w,4),np.uint8);pixels[:,:,:3]=image
        storage[:,:w*4]=pixels.reshape(h,w*4)
        local=image[crop.top:crop.top+crop.height,crop.left:crop.left+crop.width]
        expected=expected_remap(local,crop.pl_command())
        oracle=cv2.resize(local,(80,80)) if official is None else official
        words=storage.reshape(-1).view('<u8')
        rgb=expected[:,:,0].astype(np.uint32)|(expected[:,:,1].astype(np.uint32)<<8)|(expected[:,:,2].astype(np.uint32)<<16)
        config=[101,0x1000,pitch,0,w,h,80,80,80,80,
                crop.left,crop.top,crop.width,crop.height,0,0,0,1,
                2 if fault in (1,2,9) else 1 if fault in (3,4,5,6) else 0,
                6400,len(words),fault]
        np.savetxt(directory/'source.hex',words,fmt='%016x')
        np.savetxt(directory/'expected.hex',rgb.reshape(-1),fmt='%06x')
        np.savetxt(directory/'command.hex',np.array(config,dtype='<u4'),fmt='%08x')
        cv2.imwrite(str(directory/'expected.png'),expected)
        cv2.imwrite(str(directory/'official.png'),oracle)
        diff=np.abs(expected.astype(np.int16)-oracle.astype(np.int16))
        cases.append({'name':name,'model':crop.model,'fault':fault,'roi':[crop.left,crop.top,crop.width,crop.height],
                      'opencv_resize_difference':{'max':int(diff.max()),'mean':float(diff.mean())}})
    rng=np.random.default_rng(20261018)
    image=rng.integers(0,256,(67,103,3),dtype=np.uint8)
    for name,crop in [('odd_roi',PadCrop('synthetic',13,17,41,29)),
                      ('tiny_roi',PadCrop('synthetic',13,17,2,3)),
                      ('edge_roi',PadCrop('synthetic',100,65,3,2)),
                      ('full_frame',PadCrop('synthetic',0,0,103,67))]:add(name,image,crop)
    one=image[:1,:1]
    add('single_pixel',one,PadCrop('synthetic',0,0,1,1))
    add('cache_new_frame',one,PadCrop('synthetic',0,0,1,1),fault=8)
    for fault in (1,2,3,4,5,6,7,9):add('fault_'+str(fault),image,PadCrop('synthetic',13,17,41,29),fault=fault)
    reference=json.loads((args.reference/'reference-parity.json').read_text())
    for sample in reference['samples']:
        file=args.reference/'reference/images/sample'/(sample['name']+'.jpg')
        assert hashlib.sha256(file.read_bytes()).hexdigest()==sample['source_sha256']
        photo=cv2.imread(str(file));bbox=sample['bbox_xywh']
        for crop,scale in zip(plan_crops(photo.shape[1],photo.shape[0],bbox),(2.7,4.0)):
            official=cropper.crop(photo,bbox,scale,80,80,True)
            add(sample['name']+'-'+crop.model,photo,crop,official=official)
    sources=['rtl/wcis_pad_preprocess.v','rtl/wcis_affine_sampler.v','rtl/wcis_pixel_read_axi.v','sim/tb_pad_preprocess.sv']
    command=['C:/msys64/ucrt64/bin/iverilog.exe','-g2012','-Wall','-s','tb_pad_preprocess','-o',str(out/'pad.vvp'),*[str(ROOT/p) for p in sources]]
    run=subprocess.run(command,capture_output=True,text=True)
    (out/'compile.log').write_text(run.stdout+run.stderr)
    if run.returncode:raise RuntimeError(run.stderr)
    for case in cases:
        directory=out/case['name']
        p=subprocess.run(['C:/msys64/ucrt64/bin/vvp.exe',str(out/'pad.vvp'),'+vectors='+directory.as_posix()],capture_output=True,text=True,timeout=60)
        (directory/'simulation.log').write_text(p.stdout+p.stderr)
        if p.returncode or 'PASS pad_preprocess' not in p.stdout:raise RuntimeError(case['name']+' '+p.stdout+p.stderr)
        case['passed']=True
        print(case['name'],'PASS',case['opencv_resize_difference'],flush=True)
    report={'passed':True,'cases':cases,'upstream_commit':UPSTREAM_COMMIT,
            'scope':'RTL simulation only, Q5 bilinear vs cv2.resize differences recorded; no full design/board proof',
            'sources_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources}}
    (out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('PASS',len(cases),'cases')


if __name__=='__main__':main()
