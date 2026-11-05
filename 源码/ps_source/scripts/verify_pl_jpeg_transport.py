"""Exercise actual packetizer RTL plus bounded reassembly and HTTP freshness."""
from pathlib import Path
import argparse, hashlib, io, json, random, struct, subprocess, sys, zlib
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lan_stream'))
from pl_jpeg_protocol import HEADER,CHUNK,START,END,ABORT,Reassembler,jpeg_size


def packets(data,fid=1,session=0x12345678):
    result=[]
    for offset in range(0,len(data),CHUNK):
        body=data[offset:offset+CHUNK];final=offset+len(body)==len(data)
        flags=(START if offset==0 else 0)|(END if final else 0)
        result.append(HEADER.pack(b'WJP1',1,flags,HEADER.size,session,fid,offset,
            len(data) if final else 0,len(body),1920,1080,0,zlib.crc32(body),b'JPEG')+body)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=Path('D:/yzd/tmp/pl-jpeg-ethernet-1080p-20261023/transport-test'))
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    image=Image.new('RGB',(1920,1080));pixels=image.load()
    for y in range(1080):
        for x in range(1920):pixels[x,y]=(x%256,y%256,255 if (x//32+y//32)%2 else 0)
    out=io.BytesIO();image.save(out,format='JPEG',quality=75,subsampling=1);jpeg=out.getvalue()
    assert jpeg_size(jpeg)==(1920,1080)
    (a.out/'reference.jpg').write_bytes(jpeg)
    records=[]
    for size in (1,1399,1400,1401,2800,2801,len(jpeg)):
        folder=a.out/str(size);folder.mkdir(exist_ok=True)
        payload=jpeg if size==len(jpeg) else bytes((i*31+7)%256 for i in range(size))
        (folder/'input.hex').write_text(''.join(f'{x:02x}\n' for x in payload))
        command=['iverilog','-g2012','-Wall','-s','tb_jpeg_udp_packetizer',
                 f'-Ptb_jpeg_udp_packetizer.BYTES={size}','-o',str(folder/'sim.vvp'),
                 str(ROOT/'rtl/vendor/verilog_ethernet/axis/rtl/axis_fifo.v'),
                 str(ROOT/'rtl/wcis_jpeg_udp_packetizer.v'),str(ROOT/'sim/tb_jpeg_udp_packetizer.sv')]
        result=subprocess.run(command,capture_output=True,text=True)
        (folder/'compile.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stderr
        result=subprocess.run(['vvp',str(folder/'sim.vvp'),f'+HEX={(folder/"input.hex").as_posix()}'],cwd=folder,capture_output=True,text=True,timeout=45)
        (folder/'simulation.log').write_text(result.stdout+result.stderr)
        assert result.returncode==0 and 'PASS jpeg_udp_packetizer' in result.stdout,result.stdout+result.stderr
        actual=[q.read_bytes() for q in sorted(folder.glob('packet_*.bin'),key=lambda q:int(q.stem.split('_')[1]))]
        frames={fid:[] for fid in range(100,107)}
        for packet in actual:
            h=HEADER.unpack_from(packet);body=packet[HEADER.size:]
            assert h[0:4]==(b'WJP1',1,h[2],40) and h[4]==0x12345678
            assert h[8]==len(body) and h[12]==zlib.crc32(body)
            assert len(packet)+8+20<=1500
            frames[h[5]].append(packet)
        for fid in (100,101,103,106):assert frames[fid]==packets(payload,fid)
        assert HEADER.unpack_from(frames[102][-1])[2]==ABORT
        for fid in (104,105):
            assert len(frames[fid])==2
            first=HEADER.unpack_from(frames[fid][0]);cancel=HEADER.unpack_from(frames[fid][1])
            assert first[2]==START and first[6:9]==(0,0,CHUNK)
            assert frames[fid][0][HEADER.size:]==bytes(payload[i%size] for i in range(CHUNK))
            assert cancel[2]==ABORT and cancel[6:9]==(CHUNK,0,0)
            assert frames[fid][1][HEADER.size:]==b''
        if size==len(jpeg):
            decoder=Reassembler(0x12345678);complete=[]
            for packet in actual:
                q=decoder.feed(packet)
                if q:complete.append(q)
            assert [q.frame_id for q in complete]==[100,101,103,106]
            assert all(q.jpeg==jpeg for q in complete)
            for q in complete:
                decoded=Image.open(io.BytesIO(q.jpeg));decoded.load();assert decoded.size==(1920,1080)
        records.append(dict(bytes=size,packets=len(actual),passed=True))
        print('PASS RTL packet bytes',size,flush=True)
    clock=[10.]
    def decoder():return Reassembler(0x12345678,clock=lambda:clock[0])
    original=packets(jpeg)
    # Reordering, duplicate delivery, exact reproduction.
    d=decoder();shuffled=original+original[::3];random.Random(71).shuffle(shuffled)
    results=[v for b in shuffled if (v:=d.feed(b)) is not None]
    assert len(results)==1 and results[0].jpeg==jpeg
    # Missing fragment never commits; stale frame cannot be resurrected.
    d=decoder()
    for b in original[1:]:assert d.feed(b) is None
    clock[0]+=.3;d.expire();assert d.feed(original[0]) is None
    # Corruption, wrong session, hostile length and geometry cannot publish.
    d=decoder();bad=bytearray(original[0]);bad[-1]^=1
    assert d.feed(bad) is None and d.current is None
    wrong=list(HEADER.unpack_from(original[0]));wrong[4]+=1
    assert d.feed(HEADER.pack(*wrong)+original[0][HEADER.size:]) is None
    for index,value in ((6,0xfffffff0),(8,65535),(9,8192),(11,1)):
        h=list(HEADER.unpack_from(original[0]));h[index]=value
        assert d.feed(HEADER.pack(*h)+original[0][HEADER.size:]) is None
    assert d.current is None
    # A CRC-valid conflicting duplicate poisons only its own frame.
    d=decoder();d.feed(original[0]);body=bytearray(original[0][HEADER.size:]);body[-1]^=1
    h=list(HEADER.unpack_from(original[0]));h[12]=zlib.crc32(body)
    assert d.feed(HEADER.pack(*h)+body) is None and d.current is None
    assert all(d.feed(b) is None for b in original[1:])
    # New frames supersede incomplete old frames; IDs wrap modulo 2**32.
    d=decoder();d.feed(packets(jpeg,0xffffffff)[0]);d.feed(packets(jpeg,0)[0]);assert d.current==0
    assert d.feed(packets(jpeg,0xffffffff)[1]) is None
    # Existing viewer reads the new source adapter, and stops stale display.
    import receive_pl_jpeg as receiver
    frames=receiver.NetworkFrames(0x12345678,timeout=.25)
    for b in original:frames.accept(b)
    assert frames.read()[0]['ready'] and frames.read()[1]==jpeg
    from dataclasses import replace
    frames.latest=replace(frames.latest,first_packet_at=frames.latest.first_packet_at-1)
    assert not frames.read()[0]['ready'] and frames.read()[1] is None
    report=dict(passed=True,rtl_cases=records,protocol_fault_cases=True,
                full_hd_payload_sha256=hashlib.sha256(jpeg).hexdigest(),
                geometry=[1920,1080],board_verified=False,bitstream_generated=False,
                source_sha256={str(q.relative_to(ROOT)):hashlib.sha256(q.read_bytes()).hexdigest() for q in
                    [ROOT/'rtl/wcis_jpeg_udp_packetizer.v',ROOT/'rtl/vendor/verilog_ethernet/axis/rtl/axis_fifo.v',ROOT/'lan_stream/pl_jpeg_protocol.py',ROOT/'lan_stream/receive_pl_jpeg.py',ROOT/'sim/tb_jpeg_udp_packetizer.sv']})
    (a.out/'summary.json').write_text(json.dumps(report,indent=2))
    print('TRANSPORT VERIFICATION PASSED')


if __name__=='__main__':main()
