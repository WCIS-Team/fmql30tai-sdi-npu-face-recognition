"""Generate OpenCV/InsightFace golden vectors and execute actual RTL.

No model compilation/inference, board access, service changes or case mutation.
All generated test inputs, dependencies and reports belong under D:/yzd/tmp.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model_backend.face_geometry import detector_geometry, face_geometry, inverse_q16, ARCFACE_DST


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_remap(image, geometry):
    """Independent oracle: let OpenCV interpolate the exact quantized maps."""
    cw, ch = geometry['content']
    w, h = geometry['canvas']
    yy, xx = np.mgrid[:ch, :cw].astype(np.int64)
    a = geometry['matrix']
    mx = (a[0, 0]*xx + a[0, 1]*yy + a[0, 2] + 1024) // 2048
    my = (a[1, 0]*xx + a[1, 1]*yy + a[1, 2] + 1024) // 2048
    border = geometry['border']
    bgr = (border & 255, (border >> 8) & 255, (border >> 16) & 255)
    result = np.empty((h, w, 3), np.uint8)
    result[:] = bgr
    result[:ch, :cw] = cv2.remap(image, (mx / 32).astype(np.float32),
        (my / 32).astype(np.float32), cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE if geometry['replicate'] else cv2.BORDER_CONSTANT,
        borderValue=bgr)
    return result


def write_case(out, name, image, geometry, reference=None, rgb565=False, fault=0):
    directory = out / name
    directory.mkdir(parents=True, exist_ok=True)
    h, w = image.shape[:2]
    bytes_per_pixel = 2 if rgb565 else 4
    pitch = ((w * bytes_per_pixel + 7) // 8) * 8
    stored = np.zeros((h, pitch), dtype=np.uint8)
    b, g, r = [image[:, :, i].astype(np.uint16) for i in range(3)]
    if rgb565:
        packed = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        stored[:, :w*2] = packed.astype('<u2').view(np.uint8).reshape(h, w*2)
        p = packed.astype(np.uint32)
        r5, g6, b5 = p >> 11, (p >> 5) & 63, p & 31
        image = np.stack(((b5 << 3) | (b5 >> 2), (g6 << 2) | (g6 >> 4),
                          (r5 << 3) | (r5 >> 2)), axis=2).astype(np.uint8)
    else:
        pixels = np.zeros((h, w, 4), dtype=np.uint8)
        pixels[:, :, :3] = image
        stored[:, :w*4] = pixels.reshape(h, w*4)
    words = stored.reshape(-1).view('<u8')
    expected = expected_remap(image, geometry)
    values = expected[:, :, 0].astype(np.uint32) | (expected[:, :, 1].astype(np.uint32) << 8) | (expected[:, :, 2].astype(np.uint32) << 16)
    np.savetxt(directory / 'source.hex', words, fmt='%016x')
    np.savetxt(directory / 'expected.hex', values.reshape(-1), fmt='%06x')
    cw, ch = geometry['content']; dw, dh = geometry['canvas']
    error = 2 if fault in (1,2,9) else (1 if fault in (3,4,5,6) else 0)
    config = [101, 0x1000, pitch, int(rgb565), w, h, cw, ch, dw, dh,
              *geometry['matrix'].reshape(-1), geometry['border'], int(geometry['replicate']),
              error, dw*dh, len(words), fault]
    np.savetxt(directory / 'command.hex', np.asarray([int(x) & 0xffffffff for x in config], dtype=np.uint32), fmt='%08x')
    cv2.imwrite(str(directory / 'expected.png'), expected)
    record = dict(name=name, pixels=dw*dh, source_shape=[h, w], rgb565=rgb565,
                  fault=fault, source_sha256=sha(directory/'source.hex'),
                  expected_sha256=sha(directory/'expected.hex'),
                  command_sha256=sha(directory/'command.hex'))
    if reference is not None:
        diff = np.abs(expected.astype(np.int16) - reference.astype(np.int16))
        record['unquantized_opencv_difference'] = dict(max=int(diff.max()), mean=float(diff.mean()),
            changed_channels=int(np.count_nonzero(diff)), total_channels=int(diff.size))
        cv2.imwrite(str(directory / 'upstream.png'), reference)
    return record


def generate(out, upstream):
    # Run the pinned, inspected mature implementation, rather than an oracle
    # copied from the new descriptor builder.
    spec = importlib.util.spec_from_file_location('insightface_face_align_reference', upstream/'face_align.py')
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    source_record = json.loads((upstream/'sources.json').read_text())
    from fetch_face_pl_reference import COMMIT, SHA
    if source_record['commit']!=COMMIT or source_record['sha256']!=SHA or sha(upstream/'face_align.py')!=SHA:
        raise ValueError('Pinned InsightFace reference checksum mismatch')
    np.testing.assert_array_equal(ARCFACE_DST, reference.arcface_dst)
    records = []
    yy, xx = np.mgrid[:9, :13]
    image = np.stack(((xx*47+yy*11)%256, (xx*19+yy*43)%256, (xx*7+yy*61)%256), axis=2).astype(np.uint8)
    identity = dict(content=(13,9), canvas=(13,9), matrix=inverse_q16([[1,0,0],[0,1,0]]), replicate=False, border=0)
    records.append(write_case(out,'identity_odd_pitch',image,identity,reference=image))
    fractional = dict(content=(17,12),canvas=(19,15),matrix=inverse_q16([[0.9,0.25,-1.3],[-0.2,0.8,-0.7]]),replicate=False,border=0x1d5361)
    records.append(write_case(out,'rotate_border_padding',image,fractional))
    replicate = dict(fractional,replicate=True)
    records.append(write_case(out,'replicate_border',image,replicate))
    records.append(write_case(out,'rgb565_odd_pitch',image,identity,rgb565=True))
    single = dict(content=(3,3),canvas=(4,4),matrix=inverse_q16([[1,0,-1],[0,1,-1]]),replicate=False,border=0)
    records.append(write_case(out,'one_pixel',image[:1,:1],single))
    # Both signs and large outside coordinates exercise sign extension and
    # accumulator widths without issuing any out-of-range AXI transaction.
    extreme = dict(content=(4,3),canvas=(4,3),matrix=inverse_q16([[32767,-32767,32767],[-32767,32767,-32767]]),replicate=False,border=0)
    records.append(write_case(out,'wide_coordinates',image,extreme))
    for fault in range(1,8):
        records.append(write_case(out,'fault_'+str(fault),image,identity,fault=fault))
    one = dict(content=(1,1),canvas=(1,1),matrix=inverse_q16([[1,0,0],[0,1,0]]),replicate=False,border=0)
    records.append(write_case(out,'cache_new_frame',image[:1,:1],one,fault=8))
    records.append(write_case(out,'fault_after_partial_frame',image,identity,fault=9))
    records.append(write_case(out,'reset_command_check',image[:1,:1],single,fault=10))
    records.append(write_case(out,'reset_command_send',image[:1,:1],single,fault=11))
    real_entries = json.loads((ROOT/'outputs/photo-board-20261014/accepted-results/site/results.json').read_text(encoding='utf-8'))['entries']
    for filename in ['obama.jpg','obama2.jpg','biden.jpg','img1.jpg']:
        entry = next(e for e in real_entries if e['file']==filename)
        photo_path=ROOT/'photo_reference/data/public'/filename
        if sha(photo_path)!=entry['sha256']:
            raise ValueError('Photo/landmark frame binding checksum mismatch: '+filename)
        photo = cv2.imread(str(photo_path))
        if photo is None: raise ValueError('Missing public test photo: '+filename)
        landmarks = np.asarray(entry['face']['landmarks'])
        geometry = face_geometry(landmarks)
        upstream_matrix = reference.estimate_norm(landmarks)
        np.testing.assert_allclose(geometry['forward_matrix'],upstream_matrix,rtol=0,atol=1e-12)
        records.append(write_case(out,'face_'+Path(filename).stem,photo,geometry,reference=reference.norm_crop(photo,landmarks)))
    photo = cv2.imread(str(ROOT/'photo_reference/data/public/obama.jpg'))
    photo = cv2.resize(photo,(1920,1080))
    geometry = detector_geometry(1920,1080)
    detector_reference = np.zeros((640,640,3),np.uint8)
    detector_reference[:360,:640] = cv2.resize(photo,(640,360),interpolation=cv2.INTER_LINEAR)
    records.append(write_case(out,'detector_1080p',photo,geometry,reference=detector_reference))
    # Portrait noninteger mapping: quantization difference is measured, never
    # passed off as bit-exact equivalence to cv2.resize.
    photo = cv2.imread(str(ROOT/'photo_reference/data/public/obama2.jpg'))
    geometry = detector_geometry(photo.shape[1],photo.shape[0])
    detector_reference = np.zeros((640,640,3),np.uint8)
    cw,ch = geometry['content'];detector_reference[:ch,:cw] = cv2.resize(photo,(cw,ch))
    records.append(write_case(out,'detector_portrait',photo,geometry,reference=detector_reference))
    # Descriptor validation, beyond positive vectors.
    for bad in [np.zeros((5,2)), np.ones((5,2))*np.nan, np.ones((3,2))]:
        try: face_geometry(bad)
        except ValueError: pass
        else: raise AssertionError('Invalid landmarks accepted')
    provenance = dict(insightface=source_record,opencv_version=cv2.__version__,
        opencv_source='https://github.com/opencv/opencv/blob/4.10.0/modules/imgproc/src/imgwarp.cpp',
        vendor_sources={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'case/rtl/display/aq_axi_master.v',ROOT/'case/rtl/display/frame_fifo_read.v',ROOT/'case/rtl/display/cmos_resize_24bit.v']})
    return records,provenance


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,default=Path('D:/yzd/tmp/face-pl-20261015/verification'))
    parser.add_argument('--upstream',type=Path,default=Path('D:/yzd/tmp/face-pl-20261015/upstream'))
    parser.add_argument('--iverilog',default='C:/msys64/ucrt64/bin/iverilog.exe')
    parser.add_argument('--vvp',default='C:/msys64/ucrt64/bin/vvp.exe')
    args=parser.parse_args();out=args.out.resolve()
    if not out.is_relative_to(Path('D:/yzd/tmp').resolve()):
        raise ValueError('Generated artifacts must stay under D:/yzd/tmp')
    if not cv2.__version__.startswith('4.10.'):
        raise RuntimeError('Use pinned OpenCV 4.10 for this golden reference; 5.0 changes rounding')
    out.mkdir(parents=True,exist_ok=True)
    records,provenance=generate(out,args.upstream)
    sources=['rtl/wcis_affine_sampler.v','rtl/wcis_pixel_read_axi.v','rtl/wcis_face_preprocess.v','sim/tb_face_preprocess.sv']
    command=[args.iverilog,'-g2012','-Wall','-s','tb_face_preprocess','-o',str(out/'face.vvp'),*[str(ROOT/s) for s in sources]]
    run=subprocess.run(command,capture_output=True,text=True);(out/'compile.log').write_text(run.stdout+run.stderr)
    if run.returncode:raise RuntimeError(run.stderr)
    for record in records:
        started=time.monotonic();directory=out/record['name']
        run=subprocess.run([args.vvp,str(out/'face.vvp'),'+vectors='+directory.as_posix()],capture_output=True,text=True,timeout=300)
        (directory/'simulation.log').write_text(run.stdout+run.stderr)
        record.update(passed=run.returncode==0 and 'PASS face_preprocess' in run.stdout,wall_seconds=time.monotonic()-started)
        print(record['name'],run.stdout.strip(),flush=True)
        if not record['passed']:raise RuntimeError('RTL regression failed: '+record['name'])
    report=dict(scope='RTL pixel/protocol verification; no NPU inference, full-board timing, bitstream or deployment',
                passed=True,cases=records,provenance=provenance,
                rtl_sha256={s:sha(ROOT/s) for s in sources},
                verifier_sha256=sha(Path(__file__)),
                geometry_sha256=sha(ROOT/'model_backend/face_geometry.py'))
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS all',len(records),'cases; report',out/'verification.json',flush=True)


if __name__=='__main__':main()
