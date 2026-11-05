"""Fetch a completed bounded recording, decode every JPEG, report real timings."""
import argparse,hashlib,io,json,re,statistics,sys
from pathlib import Path
import numpy as np
from PIL import Image
from ssh_transport import board_connection

def stats(values):
    a=np.asarray(values,dtype=np.float64)
    return dict(min=float(a.min()),median=float(np.median(a)),p95=float(np.percentile(a,95)),max=float(a.max()))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--golden',action='store_true',help='Compare the first hardware JPEG against the pinned software DCT model')
    a=p.parse_args();local=json.loads((a.run/'summary.json').read_text(encoding='utf-8'))
    assert local['passed'] and local['backend']=='jpeg'
    remote=local['board_done']['out']
    if not re.fullmatch(r'/mnt/wcis-emmc/wcis-face/recording-tests/jpeg-[0-9a-f]{32}',remote):raise ValueError('Unexpected recording path')
    with board_connection() as c:
        s=c.open_sftp()
        for name in ('summary.json','output.mjpeg','frames.jsonl'):
            target=a.run/('board-'+name if name=='summary.json' else name)
            if not target.exists():s.get(remote+'/'+name,str(target))
        command="python3 - <<'PY'\nimport hashlib,json\np="+repr(remote+'/output.mjpeg')+"\nh=hashlib.sha256()\nwith open(p,'rb') as f:\n for b in iter(lambda:f.read(1048576),b''):h.update(b)\nprint(json.dumps(dict(sha256=h.hexdigest())))\nPY"
        _,out,err=c.exec_command(command,timeout=20);digest=json.loads(out.read())['sha256']
        assert out.channel.recv_exit_status()==0
    path=a.run/'output.mjpeg'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    board=json.loads((a.run/'board-summary.json').read_text())
    assert board['passed'] and board['device_closed']
    jobs=[r['hardware'] for r in board['frames']]
    for batch in board['benchmarks']:jobs.extend(batch['results'])
    expected_reads=1920*1080*(4 if local['pixel_format']=='BGRX8' else 2)//64
    for job in jobs:
        assert job['read_blocks']==expected_reads,'Compression did not request a complete DDR source frame'
        assert job['write_blocks']==(job['jpeg_bytes']+63)//64,'JPEG DDR output request count mismatch'
        assert job['hw_cycles']>0 and job['encoder_cycles']>0
    written=[r['hardware'] for r in board['frames']]
    for b in board['benchmarks']:
        if b['record']:written.extend(b['results'])
    cursor=0;hashes=[];first_bytes=None
    source_only=a.run/'source-only.mjpeg'
    with path.open('rb') as f,source_only.open('wb') as fresh_file:
        for index,r in enumerate(written):
            assert r['record_offset']==cursor
            data=f.read(r['jpeg_bytes']);assert len(data)==r['jpeg_bytes']
            assert data[:2]==b'\xff\xd8' and data[-2:]==b'\xff\xd9'
            with Image.open(io.BytesIO(data)) as image:
                image.load();assert image.size==(1920,1080)
                if index in (0,len(board['frames'])-1):image.save(a.run/f'decoded-{index}.png')
            if index==0:first_bytes=data
            if index<len(board['frames']):fresh_file.write(data)
            hashes.append(hashlib.sha256(data).hexdigest());cursor+=len(data)
        assert not f.read(1)
    assert cursor==board['closed']['record_bytes']
    # The resident source is unchanged. JPEG has no frame-dependent metadata;
    # every recorded replay must exactly equal the last fresh source encoding.
    if len(written)>len(board['frames']):
        assert all(h==hashes[len(board['frames'])-1] for h in hashes[len(board['frames']):]),'Resident JPEG changed without a new source'
    fresh=local['results']
    assert all(r['hardware']['source_verified'] for r in fresh),'Fresh DDR uploads were not all checked'
    report=dict(passed=True,native_resolution=[1920,1080],source_video=local['video'],source_fps=local['source_fps'],
        source_frames=len(fresh),decoded_complete_jpegs=len(written),distinct_fresh_jpegs=len(set(hashes[:len(fresh)])),
        resident_recordings_equal_source=True,all_fresh_ddr_uploads_verified=True,
        native_request_counters_verified=True,
        local_source_to_emmc_fps=len(fresh)*1000/local['source_committed_ms'],
        local_source_committed_ms=local['source_committed_ms'],jpeg_bytes=stats([r['jpeg_bytes'] for r in fresh]),
        hardware_ms=stats([r['hardware']['hardware_ms'] for r in fresh]),
        round_trip_ms=stats([r['local_timing']['round_trip_ms'] for r in fresh]),
        board_receive_ms=stats([r['timing']['board_receive_ms'] for r in fresh]),
        upload_ms=stats([r['hardware']['upload_ms'] for r in fresh]),
        source_verification_ms=stats([r['hardware']['source_verification_ms'] for r in fresh]),
        readback_ms=stats([r['hardware']['readback_ms'] for r in fresh]),
        record_ms=stats([r['hardware']['record_ms'] for r in fresh]),
        record_sha256=digest,source_only_mjpeg=str(source_only),board_boot_id=board['boot_id'],benchmarks=[],camera_input=False,cpu_jpeg_encoding=False)
    for b in local['benchmarks']:
        report['benchmarks'].append(dict(kind=b['kind'],iterations=b['iterations'],measured_batch_fps=b['batch_fps'],
            batch_ms=b['batch_ms'],fsync_ms=b['fsync_ms'],hardware_ms=stats([r['hardware_ms'] for r in b['results']]),
            readback=b['readback'],record=b['record'],source='resident_DDR_replay_not_new_capture'))
    if a.golden:
        import cv2
        sys.path.insert(0,'D:/yzd/tmp/pl-jpeg-20261016/upstream/python')
        from yuyv_convert import rtl_rgb_to_ycbcr_planes
        from jpeg_encoder import encode_jpeg_from_planes
        from verify_rtl_sim import _decode_coefficients
        cap=cv2.VideoCapture(local['video']);cap.set(cv2.CAP_PROP_POS_FRAMES,fresh[0]['sequence']-1)
        ok,bgr=cap.read();cap.release();assert ok
        rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
        if local['pixel_format']=='RGB565LE':
            v=rgb.astype(np.uint16);r5=v[:,:,0]>>3;g6=v[:,:,1]>>2;b5=v[:,:,2]>>3
            rgb=np.stack(((r5<<3)|(r5>>2),(g6<<2)|(g6>>4),(b5<<3)|(b5>>2)),2).astype(np.uint8)
        ref=encode_jpeg_from_planes(*rtl_rgb_to_ycbcr_planes(rgb),quality=board['worker_ready']['quality'])
        (a.run/'reference-first.jpg').write_bytes(ref)
        one=_decode_coefficients(first_bytes,1920*1080//128);two=_decode_coefficients(ref,1920*1080//128)
        aa=np.array([[b['dc'],*b['ac']] for b in one]);bb=np.array([[b['dc'],*b['ac']] for b in two])
        delta=int(np.max(np.abs(aa-bb)));assert delta<=1,delta
        report['first_full_frame_coefficient_max_error']=delta
    (a.run/'performance.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
