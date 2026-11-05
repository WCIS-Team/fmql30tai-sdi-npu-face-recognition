"""Publish a verified SDK trial receipt plus live PS heartbeat, without hardware access.

Factory BOOT has no independent SDIS status page. Lock flags are unknown, not
inferred from the previous bitstream. A receipt from another boot is rejected.
"""
import argparse
import http.client
import ipaddress
import json
from pathlib import Path
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('receiver_ipv4')
    parser.add_argument('receipt',type=Path)
    parser.add_argument('--port',type=int,default=8088)
    parser.add_argument('--seconds',type=int,default=15)
    args=parser.parse_args()
    ipaddress.IPv4Address(args.receiver_ipv4)
    if not 1 <= args.port <= 65535 or not 1 <= args.seconds <= 3600:
        parser.error('Port/duration outside limits')
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    receipt=json.loads(args.receipt.read_text())
    if receipt.get('boot_id') != boot or receipt.get('bridge_verified') is not True or receipt.get('capture_state') not in ('bridge_verified','capture_timeout'):
        raise ValueError('Receipt does not establish this boot\'s verified bridge/trial')
    sequence=time.monotonic_ns()//1000
    end=time.monotonic()+args.seconds
    while time.monotonic() < end:
        sequence+=1
        value=dict(schema_version=1,source='ps_capture',boot_id=boot,
                   sample_id=str(sequence),timestamp_us=str(time.monotonic_ns()//1000),status_sequence=str(sequence),
                   signal_locked=None,transport_locked=None,writer_fresh=None,progressive=None,qpll_locked=None,
                   width=0,height=0,capture_state=receipt['capture_state'],path_test_passed=receipt.get('path_test_passed',False))
        conn=http.client.HTTPConnection(args.receiver_ipv4,args.port,timeout=2)
        try:
            conn.request('POST','/api/device-status',json.dumps(value).encode(),{'Content-Type':'application/json'})
            reply=conn.getresponse();reply.read()
            if reply.status!=204:raise ValueError('Status receiver rejected packet: %s' % reply.status)
        finally:conn.close()
        print(json.dumps(value),flush=True)
        time.sleep(1)


if __name__=='__main__':main()
