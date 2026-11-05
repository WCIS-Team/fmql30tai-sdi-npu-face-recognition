"""Raw RGB565 labelled demo. Never opens a camera or invents model results."""
import argparse
import http.client
import time
import uuid
from raw_protocol import pack


def demo_packet(sequence, stream_id, width=320, height=180):
    colors = (0xf800, 0x07e0, 0x001f, 0xffff, 0xffe0, 0x07ff)
    row = b''.join(colors[min(x*6//width,5)].to_bytes(2, 'little') for x in range(width))
    pixels = bytearray(row*height)
    left = sequence % max(1, width-20)
    for y in range(height//2, height//2+15):
        pixels[(y*width+left)*2:(y*width+left+20)*2] = b'\x00\x00'*20
    return pack(dict(schema_version=1, stream_id=stream_id, frame_id=str(sequence),
        timestamp_us=str(time.monotonic_ns()//1000), timestamp_basis="ps_dma_done_monotonic",
        source="demo", pixel_format="RGB565LE", width=width, height=height, stride_bytes=width*2), pixels)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--seconds', type=float, default=3600)
    args = parser.parse_args()
    sequence = 0
    stream_id = 'demo-'+uuid.uuid4().hex
    deadline = time.monotonic()+10
    end = time.monotonic()+args.seconds
    connection = http.client.HTTPConnection('127.0.0.1', args.port, timeout=3)
    while time.monotonic() < end:
        sequence += 1
        try:
            connection.request('POST', '/api/frame', demo_packet(sequence, stream_id), {'Content-Type':'application/octet-stream'})
            response = connection.getresponse(); response.read()
            if response.status != 204:
                raise SystemExit('Demo ingest rejected: HTTP '+str(response.status))
            deadline = time.monotonic()+10
        except OSError as error:
            connection.close()
            if time.monotonic() > deadline:
                raise SystemExit('Demo receiver unavailable: '+type(error).__name__)
        time.sleep(.2)
    connection.close()


if __name__ == '__main__':
    main()
