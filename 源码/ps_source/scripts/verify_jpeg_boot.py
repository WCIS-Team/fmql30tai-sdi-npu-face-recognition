"""Verify new PL payload and byte-identical PS partitions against board backup."""
import argparse,array,hashlib,json,struct,sys
from pathlib import Path
def sha(b):return hashlib.sha256(b).hexdigest()
def partitions(data):
    if struct.unpack_from('<I',data,0x24)[0]!=0x464d5348:raise ValueError('Not an FMSH BOOT image')
    table=struct.unpack_from('<I',data,0x98)[0]
    if struct.unpack_from('<I',data,table+4)[0]!=4:raise ValueError('Expected four partitions')
    pos=struct.unpack_from('<I',data,table+8)[0]*4;result=[]
    for name in ('FSBL','PL','BL31','U-Boot'):
        size=struct.unpack_from('<I',data,pos)[0]*4;offset=struct.unpack_from('<I',data,pos+32)[0]*4
        if size<=0 or offset+size>len(data):raise ValueError('Invalid partition extent')
        result.append(dict(name=name,offset=offset,bytes=size,sha256=sha(data[offset:offset+size])))
        pos=struct.unpack_from('<I',data,pos+12)[0]*4
    return result
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task',type=Path,default=Path('D:/yzd/tmp/pl-jpeg-board-20261016'))
    a=p.parse_args();out=a.task/'boot-candidate'
    before=(a.task/'before-BOOT.bin').read_bytes();boot=(out/'BOOT.bin').read_bytes();bit=(out/'ai7030_edif_top.bit').read_bytes()
    snapshot=json.loads((a.task/'board-before.json').read_text())
    assert sha(before)==snapshot['boot_files']['BOOT.bin']['sha256']
    offset=2+struct.unpack_from('>H',bit)[0];assert struct.unpack_from('>H',bit,offset)[0]==1;offset+=2
    while True:
        tag=chr(bit[offset]);offset+=1
        if tag=='e':
            size=struct.unpack_from('>I',bit,offset)[0];offset+=4;payload=bit[offset:offset+size];assert offset+size==len(bit);break
        assert tag in 'abcd';size=struct.unpack_from('>H',bit,offset)[0];offset+=2+size
    assert sys.byteorder=='little';words=array.array('I',payload);words.byteswap()
    old=partitions(before);new=partitions(boot);pl=new[1]
    raw=boot[pl['offset']:pl['offset']+pl['bytes']]
    assert raw[:len(payload)]==words.tobytes() and raw[len(payload):] in (b'',bytes.fromhex('00000020'))
    assert all(new[i]['sha256']==old[i]['sha256'] and new[i]['bytes']==old[i]['bytes'] for i in (0,2,3))
    report=dict(boot_sha256=sha(boot),bit_sha256=sha(bit),reference_boot_sha256=sha(before),
        ps_partitions_identical=True,current_bit_payload_matches=True,partitions=new,board_verified=False)
    (out/'manifest.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
