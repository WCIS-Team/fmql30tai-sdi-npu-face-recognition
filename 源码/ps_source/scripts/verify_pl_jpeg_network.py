"""Drive the real pinned MAC/ARP/IP/UDP stack through its RGMII pins."""
from pathlib import Path
import argparse,hashlib,json,struct,subprocess,zlib

R=Path(__file__).resolve().parents[1]
def checksum(data):
    if len(data)%2:data+=b'\0'
    n=sum(struct.unpack('!'+str(len(data)//2)+'H',data))
    while n>>16:n=(n&65535)+(n>>16)
    return (~n)&65535

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=Path('D:/yzd/tmp/pl-jpeg-ethernet-1080p-20261023/network-test'))
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    v=R/'rtl/vendor/verilog_ethernet';manifest=json.loads((v/'sources.json').read_text())
    for f in manifest['files']:assert hashlib.sha256((v/f['path']).read_bytes()).hexdigest()==f['sha256']
    host=bytes.fromhex('020000000002');board=bytes.fromhex('025743495302')
    hostip=bytes([192,168,1,102]);boardip=bytes([192,168,1,114])
    arp=bytes.fromhex('ffffffffffff')+host+bytes.fromhex('0806')
    arp+=struct.pack('!HHBBH',1,0x0800,6,4,1)+host+hostip+bytes(6)+boardip
    arp+=bytes(60-len(arp));arp+=struct.pack('<I',zlib.crc32(arp))
    arp=b'\x55'*7+b'\xd5'+arp;assert len(arp)==72
    # Use an actual payload emitted by the already-tested packetizer.
    transport=a.out.parent/'transport-test'
    previous=json.loads((transport/'summary.json').read_text())
    assert previous['passed'] and previous['geometry']==[1920,1080]
    payload=(transport/str(previous['rtl_cases'][-1]['bytes'])/'packet_0.bin').read_bytes()
    (a.out/'arp.hex').write_text(''.join(f'{x:02x}\n' for x in arp))
    (a.out/'payload.hex').write_text(''.join(f'{x:02x}\n' for x in payload))
    files=[str(v/f['path']) for f in manifest['files'] if f['path'].endswith('.v')]
    cmd=['iverilog','-g2012','-Wall','-s','tb_jpeg_network',f'-Ptb_jpeg_network.PAYLOAD_BYTES={len(payload)}','-o',str(a.out/'sim.vvp'),*files,str(R/'rtl/wcis_jpeg_network.v'),str(R/'sim/tb_jpeg_network.sv')]
    q=subprocess.run(cmd,capture_output=True,text=True);(a.out/'compile.log').write_text(q.stdout+q.stderr);assert q.returncode==0,q.stderr
    q=subprocess.run(['vvp',str(a.out/'sim.vvp'),f'+ARP={(a.out/"arp.hex").as_posix()}',f'+PAYLOAD={(a.out/"payload.hex").as_posix()}'],cwd=a.out,capture_output=True,text=True,timeout=90)
    (a.out/'simulation.log').write_text(q.stdout+q.stderr);assert q.returncode==0 and 'PASS jpeg_network' in q.stdout,q.stdout+q.stderr
    frames=[]
    for name in ('ethernet_0.bin','ethernet_1.bin'):
        frame=(a.out/name).read_bytes();assert frame[:8]==b'\x55'*7+b'\xd5'
        frame=frame[8:];assert zlib.crc32(frame[:-4])==int.from_bytes(frame[-4:],'little')
        frames.append(frame[:-4])
    reply,datagram=frames
    assert reply[:14]==host+board+b'\x08\x06' and reply[20:22]==b'\0\2'
    assert datagram[:14]==host+board+b'\x08\0'
    ip=datagram[14:34];assert ip[0]==0x45 and ip[9]==17 and checksum(ip)==0
    assert ip[12:16]==boardip and ip[16:20]==hostip
    total=int.from_bytes(ip[2:4],'big');udp=datagram[34:14+total]
    assert struct.unpack('!HHH',udp[:6])==(5004,5004,len(payload)+8)
    assert checksum(ip[12:20]+b'\0\x11'+len(udp).to_bytes(2,'big')+udp)==0
    assert udp[8:]==payload
    report=dict(passed=True,simulation='RGMII DDR with 125 MHz PHY clocks and 200 MHz logic',
        cases=['bad RX FCS rejected','ARP learned and answered','MAC destination','IPv4 header checksum','UDP checksum','Ethernet FCS','exact WJP1 payload'],
        board_verified=False,bitstream_generated=False,upstream_commit=manifest['commit'])
    (a.out/'summary.json').write_text(json.dumps(report,indent=2));print('NETWORK VERIFICATION PASSED')

if __name__=='__main__':main()
