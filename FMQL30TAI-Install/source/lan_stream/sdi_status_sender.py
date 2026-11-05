"""Read only the known SDIS DDR page. No SDK, MMIO, capture request or pixels.

The only write is a temporary 64-byte CPU cache invalidation through u-dma-buf.
The packed sync command follows https://github.com/ikwzm/udmabuf/blob/master/Readme.md.
Global sync_offset/size/direction are never changed. No /dev/mem fallback.
"""
import argparse
import http.client
import ipaddress
import json
import os
from pathlib import Path
import struct
import time

ATTR = Path('/sys/devices/platform/udmabuf@0/u-dma-buf/udmabuf0')
MAGIC = 0x53444953
SYNC_COMMAND = '0x0000000000000049'  # offset=0, size=64, DMA_FROM_DEVICE=2, trigger=1


def decode(words, boot, sample, timestamp, previous):
    magic, sequence, lo, mid, hi = words
    if magic & 0xffffffff != MAGIC or lo & 15 != 0xa:
        raise ValueError('SDIS identity mismatch; no hardware fallback')
    return dict(schema_version=1, source='sdi_status_ddr', boot_id=boot,
                sample_id=str(sample), timestamp_us=str(timestamp), status_sequence=str(sequence),
                signal_locked=bool(lo & (1 << 5)), transport_locked=bool(lo & (1 << 4)),
                writer_fresh=previous is not None and sequence > previous,
                progressive=bool(lo & (1 << 8)), qpll_locked=bool(lo & (1 << 19)),
                width=(lo >> 32) & 0xffff, height=(lo >> 48) & 0xffff,
                capture_state='blocked_incompatible_bitstream')


class StatusReader:
    def __init__(self):
        attrs = {key: (ATTR/key).read_text().strip() for key in ('phys_addr', 'size', 'driver_version')}
        if int(attrs['phys_addr'], 0) != 0x30100000 or int(attrs['size'], 0) < 4096 or attrs['driver_version'] != '3.2.5':
            raise ValueError('Unverified DDR layout/driver; refusing to read')
        self.fd = os.open('/dev/udmabuf0', os.O_RDONLY | os.O_SYNC)

    def read(self):
        def snapshot():
            (ATTR/'sync_for_cpu').write_text(SYNC_COMMAND)
            data = os.pread(self.fd, 40, 0)
            if len(data) != 40:
                raise ValueError('Short status page')
            return data
        # Five AXI beats are not an atomic snapshot. Reject a changing copy.
        for _ in range(5):
            first, second = snapshot(), snapshot()
            if first == second:
                return struct.unpack('<5Q', first)
        raise ValueError('No stable SDIS snapshot')

    def close(self):
        os.close(self.fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('receiver_ipv4')
    parser.add_argument('--port', type=int, default=8088)
    parser.add_argument('--seconds', type=int, default=15)
    args = parser.parse_args()
    ipaddress.IPv4Address(args.receiver_ipv4)
    if not 1 <= args.port <= 65535 or not 1 <= args.seconds <= 3600:
        parser.error('Port/duration outside limits')
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    reader = StatusReader()
    previous = None
    sample = time.monotonic_ns() // 1000
    end = time.monotonic() + args.seconds
    try:
        while time.monotonic() < end:
            sample += 1
            value = decode(reader.read(), boot, sample, time.monotonic_ns() // 1000, previous)
            previous = int(value['status_sequence'])
            conn = http.client.HTTPConnection(args.receiver_ipv4, args.port, timeout=2)
            try:
                conn.request('POST', '/api/device-status', json.dumps(value).encode(), {'Content-Type': 'application/json'})
                reply = conn.getresponse()
                reply.read()
                if reply.status != 204:
                    raise ValueError('Status receiver rejected packet: %s' % reply.status)
            finally:
                conn.close()
            print(json.dumps(value), flush=True)
            time.sleep(1)
    finally:
        reader.close()


if __name__ == '__main__':
    main()
