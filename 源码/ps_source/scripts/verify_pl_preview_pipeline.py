"""Decode actual RGMII output from a coupled source/JPEG/UDP/MAC simulation."""
from pathlib import Path
import argparse,hashlib,io,json,re,struct,subprocess,sys,zlib
import numpy as np
from PIL import Image
from verify_pl_jpeg_network import checksum

R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'lan_stream'))
from pl_jpeg_protocol import Reassembler

def check_capture(folder,w,h,allow_recovery=False,tx_only=False):
    raw=(folder/'ethernet-stream.bin').read_bytes();p=0;udp_count=0;frames=[];arp=0
    simulation=(folder/'simulation.log').read_text()
    gradient='noise=0' in simulation
    counts=re.search(r'PASS pipeline input=(\d+) JPEG=(\d+) rejected=(\d+) UDP=(\d+) aborted=(\d+)',simulation)
    assert counts,simulation
    inputs,encoded,rejected,done,aborted=map(int,counts.groups())
    config_path=folder/'simulation-config.json'
    expected_frames=json.loads(config_path.read_text())['frames'] if config_path.exists() else 3
    if type(expected_frames) is not int or expected_frames<1:raise ValueError('Invalid configured input frame count')
    if allow_recovery:assert encoded>=1 and rejected>=1 and aborted>=1 and done==encoded,simulation
    else:assert (inputs,encoded,rejected,done,aborted)==(expected_frames,expected_frames,0,expected_frames,0),simulation
    current_time=[0.0]
    receiver=Reassembler(0x23001080,width=w,height=h,clock=lambda:current_time[0])
    while p<len(raw):
        assert p+10<=len(raw)
        size=int.from_bytes(raw[p:p+2],'big');stamp=int.from_bytes(raw[p+2:p+10],'big')*1e-12;p+=10
        assert 72<=size<=1538 and p+size<=len(raw),(p,size)
        eth=raw[p:p+size];p+=size
        assert eth[:8]==b'\x55'*7+b'\xd5';eth=eth[8:]
        assert zlib.crc32(eth[:-4])==int.from_bytes(eth[-4:],'little');eth=eth[:-4]
        assert eth[6:12]==bytes.fromhex('025743495302')
        if eth[12:14]==b'\x08\x06':
            assert eth[:6] in (bytes.fromhex('020000000002'),b'\xff'*6)
            arp+=1;continue
        assert eth[:6]==bytes.fromhex('020000000002')
        assert eth[12:14]==b'\x08\0'
        ip=eth[14:34];assert ip[0]==0x45 and checksum(ip)==0 and ip[9]==17
        assert ip[12:20]==bytes([192,168,1,240 if tx_only else 114,192,168,1,102])
        total=int.from_bytes(ip[2:4],'big');udp=eth[34:14+total]
        assert struct.unpack('!HHH',udp[:6])==(5004,5004,len(udp))
        assert checksum(ip[12:20]+b'\0\x11'+len(udp).to_bytes(2,'big')+udp)==0
        current_time[0]=stamp
        udp_count+=1;frame=receiver.feed(udp[8:])
        if frame:
            im=Image.open(io.BytesIO(frame.jpeg));im.load();assert im.size==(w,h)
            pix=np.asarray(im)
            assert np.std(pix)>10,'Blank/corrupt decoded image'
            pixel_mae=None
            if gradient:
                yy,xx=np.indices((h,w))
                expected=np.stack((xx*255//(w-1),yy*255//(h-1),(xx*3+yy*7)%256),axis=-1)
                pixel_mae=float(np.mean(np.abs(pix.astype(float)-expected)))
                assert pixel_mae<10,('Decoded camera pixels differ',pixel_mae)
            path=folder/f'received-{frame.frame_id}.jpg';path.write_bytes(frame.jpeg)
            frames.append(dict(frame_id=frame.frame_id,bytes=len(frame.jpeg),sha256=hashlib.sha256(frame.jpeg).hexdigest(),
                completed_at_s=stamp,width=w,height=h,pixel_mean_absolute_error=pixel_mae,
                top_green=float(np.median(pix[0,:,1])),bottom_green=float(np.median(pix[-1,:,1]))))
    assert (arp==0 if tx_only else arp>=1 if allow_recovery else arp==1) and len(frames)==encoded,(arp,len(frames),udp_count,encoded)
    fps=(len(frames)-1)/(frames[-1]['completed_at_s']-frames[0]['completed_at_s']) if len(frames)>1 else None
    report=dict(passed=True,geometry=[w,h],frames=frames,udp_packets=udp_count,arp_packets=arp,
        recovery_test=allow_recovery,source_counts=dict(inputs=inputs,encoded=encoded,rejected=rejected,done=done,aborted=aborted),
        complete_frame_interval_fps=fps,board_verified=False,
        source='actual coupled SDI source bridge + JPEG RTL + WJP1 + MAC RGMII output',
        source_hashes={str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
            [R/('sim/tb_pl_preview_pipeline_tx.sv' if tx_only else 'sim/tb_pl_preview_pipeline.sv'),R/'rtl/wcis_sdi_jpeg_stream.v',R/'rtl/wcis_jpeg_compressor.v',
             R/'rtl/wcis_jpeg_udp_packetizer.v',R/('rtl/wcis_jpeg_network_tx.v' if tx_only else 'rtl/wcis_jpeg_network.v')]})
    report['tx_only']=tx_only
    # A generated fault-injection bench differs from the normal camera bench;
    # retain the exact compiled-file manifest rather than implying equivalence.
    manifest=folder/'source-hashes.json'
    if manifest.exists():
        hashes=json.loads(manifest.read_text())
        assert all(hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest for name,digest in hashes.items())
        report['compiled_source_hashes']=hashes
        report['generated_bench']=any(Path(name).parent.resolve()==folder.resolve() and Path(name).suffix=='.sv' for name in hashes)
    config=folder/'simulation-config.json'
    if config.exists():
        report['simulation_config']=json.loads(config.read_text())
        assert (report['simulation_config']['width'],report['simulation_config']['height'],report['simulation_config']['frames'])==(w,h,inputs)
    (folder/'summary.json').write_text(json.dumps(report,indent=2));return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=Path('D:/yzd/tmp/pl-jpeg-ethernet-1080p-20261023/pipeline-test'))
    p.add_argument('--check-only',action='store_true');p.add_argument('--width',type=int,default=64);p.add_argument('--height',type=int,default=16)
    p.add_argument('--allow-recovery',action='store_true',help='Validate an intentionally blocked then restored network capture')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    if not a.check_only:
        v=R/'rtl/vendor/verilog_ethernet';manifest=json.loads((v/'sources.json').read_text())
        host=bytes.fromhex('020000000002');boardip=bytes([192,168,1,114]);hostip=bytes([192,168,1,102])
        arp=bytes.fromhex('ffffffffffff')+host+b'\x08\x06'+struct.pack('!HHBBH',1,0x800,6,4,1)+host+hostip+bytes(6)+boardip
        arp+=bytes(60-len(arp));arp=b'\x55'*7+b'\xd5'+arp+struct.pack('<I',zlib.crc32(arp))
        (a.out/'arp.hex').write_text(''.join(f'{v:02x}\n' for v in arp))
        files=[str(v/f['path']) for f in manifest['files'] if f['path'].endswith('.v')]+list(map(str,(R/'rtl/vendor/mjpegzero/rtl').glob('*.v')))
        files += [str(R/f'rtl/{n}.v') for n in ('wcis_cdc_mailbox','wcis_jpeg_compressor','wcis_sdi_jpeg_stream','wcis_jpeg_udp_packetizer','wcis_jpeg_network')]
        files += [str(R/'sim/tb_pl_preview_pipeline.sv')]
        q=subprocess.run(['iverilog','-g2012','-s','tb_pl_preview_pipeline',f'-Ptb_pl_preview_pipeline.W={a.width}',f'-Ptb_pl_preview_pipeline.H={a.height}',
            '-o',str(a.out/'sim.vvp'),*files],capture_output=True,text=True)
        (a.out/'compile.log').write_text(q.stdout+q.stderr);assert q.returncode==0,q.stderr
        q=subprocess.run(['vvp',str(a.out/'sim.vvp'),f'+ARP={(a.out/"arp.hex").as_posix()}'],cwd=a.out,capture_output=True,text=True,timeout=180)
        (a.out/'simulation.log').write_text(q.stdout+q.stderr);assert q.returncode==0 and 'PASS pipeline' in q.stdout,q.stdout+q.stderr
    report=check_capture(a.out,a.width,a.height,a.allow_recovery)
    print(json.dumps({k:report[k] for k in ('passed','geometry','udp_packets','complete_frame_interval_fps')}))
if __name__=='__main__':main()
