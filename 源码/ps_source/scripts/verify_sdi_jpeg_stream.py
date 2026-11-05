"""Real source bridge/FIFO/JPEG RTL with geometry failure and recovery."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
import numpy as np
from PIL import Image

R=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=Path('D:/yzd/tmp/pl-jpeg-ethernet-1080p-20261023/source-test'))
    p.add_argument('--reference',type=Path,default=Path('D:/yzd/tmp/pl-jpeg-20261016/upstream/python'))
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    files=[*map(str,(R/'rtl/vendor/mjpegzero/rtl').glob('*.v')),
        str(R/'rtl/vendor/verilog_ethernet/axis/rtl/axis_async_fifo.v'),
        str(R/'rtl/vendor/verilog_ethernet/axis/rtl/axis_fifo.v'),
        str(R/'rtl/wcis_cdc_mailbox.v'),str(R/'rtl/wcis_jpeg_compressor.v'),
        str(R/'rtl/wcis_sdi_jpeg_stream.v'),str(R/'sim/tb_sdi_jpeg_stream.sv')]
    cmd=['iverilog','-g2012','-Wall','-s','tb_sdi_jpeg_stream','-o',str(a.out/'sim.vvp'),*files]
    q=subprocess.run(cmd,capture_output=True,text=True);(a.out/'compile.log').write_text(q.stdout+q.stderr);assert q.returncode==0,q.stderr
    q=subprocess.run(['vvp',str(a.out/'sim.vvp')],cwd=a.out,capture_output=True,text=True,timeout=45)
    (a.out/'simulation.log').write_text(q.stdout+q.stderr);assert q.returncode==0 and 'PASS sdi_jpeg_stream' in q.stdout,q.stdout+q.stderr
    manifest=json.loads((R/'rtl/vendor/mjpegzero/sources.json').read_text())
    assert subprocess.check_output(['git','-C',str(a.reference),'rev-parse','HEAD'],text=True).strip()==manifest['commit']
    sys.path.insert(0,str(a.reference))
    from yuyv_convert import rtl_rgb_to_ycbcr_planes
    from jpeg_encoder import encode_jpeg_from_planes
    from verify_rtl_sim import _decode_coefficients
    y,x=np.mgrid[:16,:64]
    source=np.stack((x*255//63,y*255//15,(x*3+y*7)%256),2).astype(np.uint8)
    ref=bytes(encode_jpeg_from_planes(*rtl_rgb_to_ycbcr_planes(source),quality=75))
    expected=np.array([[v['dc'],*v['ac']] for v in _decode_coefficients(ref,64*16//128)])
    records=[]
    for fid in (1,3):
        path=a.out/f'source_frame_{fid}.jpg';data=path.read_bytes()
        decoded=Image.open(path);decoded.load();assert decoded.size==(64,16)
        blocks=np.array([[v['dc'],*v['ac']] for v in _decode_coefficients(data,64*16//128)])
        delta=int(np.max(np.abs(blocks-expected)));assert delta<=1,delta
        records.append(dict(frame_id=fid,sha256=hashlib.sha256(data).hexdigest(),coefficient_max_error=delta))
    assert not (a.out/'source_frame_2.jpg').read_bytes().endswith(b'\xff\xd9')
    report=dict(passed=True,geometry=[64,16],full_hd_geometry_tested=False,
        cases=['full-view source','asynchronous pixel FIFO','random JPEG backpressure','malformed width rejected before EOF','next-frame recovery'],frames=records,board_verified=False)
    (a.out/'summary.json').write_text(json.dumps(report,indent=2));print('SOURCE STREAM VERIFICATION PASSED')
if __name__=='__main__':main()
