"""PL WJP1 UDP -> existing MJPEG viewer. No board SDK, transcoding or gallery.

Both source IP and deployment session are mandatory. CRC is not authentication;
run on the intended LAN. Source/session errors never change the active session.
"""
import argparse
import ipaddress
import socket
import struct
import sys
import threading
import time
from http.server import ThreadingHTTPServer

from pl_jpeg_protocol import Reassembler, HEADER, CHUNK
from vpu_live_server import handler


class NetworkFrames:
    def __init__(self, session, *, timeout=.25):
        self.decoder = Reassembler(session, timeout=timeout)
        self.lock = threading.Lock()
        self.latest = None
        self.foreign_packets = 0
        self.timeout = timeout
        self.stopped = False
        self.socket_receive_buffer = None
        self.socket_dropped_packets = None

    def accept(self, packet):
        with self.lock:
            frame = self.decoder.feed(packet)
            if frame is not None:
                self.latest = frame

    def read(self):
        with self.lock:
            now = time.monotonic()
            self.decoder.expire(now)
            state = dict(ready=False, source='camera', state='waiting_for_capture',
                         session=f'{self.decoder.session:08x}', width=1920, height=1080,
                         encoded=self.decoder.stats['completed'],
                         transport='PL_JPEG_WJP1_UDP', transcoding=False,
                         age_basis='receiver_first_packet_not_camera_capture',
                         socket_receive_buffer_bytes=self.socket_receive_buffer,
                         socket_receive_buffer_limited=(self.socket_receive_buffer is not None and self.socket_receive_buffer<4*1024*1024),
                         socket_dropped_packets=self.socket_dropped_packets,
                         udp=dict(self.decoder.stats), foreign_packets=self.foreign_packets)
            if self.stopped:
                state['state'] = 'stopped'
            elif self.latest is not None:
                age = now-self.latest.first_packet_at
                state.update(frame_id=self.latest.frame_id, frame_age_s=age,
                             reassembly_ms=1000*(self.latest.completed_at-self.latest.first_packet_at))
                if 0 <= age < self.timeout:
                    state.update(ready=True,state='ready')
                    return state,self.latest.jpeg
                state['state'] = 'no_fresh_frame'
            return state,None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sender', required=True, type=lambda s:str(ipaddress.IPv4Address(s)))
    p.add_argument('--sender-port', type=int, default=5004)
    p.add_argument('--session', required=True, type=lambda s:int(s,0))
    p.add_argument('--udp-host', default='0.0.0.0', type=lambda s:str(ipaddress.IPv4Address(s)))
    p.add_argument('--udp-port', type=int, default=5004)
    p.add_argument('--host', default='127.0.0.1', type=lambda s:str(ipaddress.IPv4Address(s)))
    p.add_argument('--port', type=int, default=18092)
    p.add_argument('--frame-timeout', type=float, default=.25)
    a = p.parse_args()
    if any(not 1 <= port <= 65535 for port in (a.port,a.udp_port,a.sender_port)):
        p.error('Ports must be in 1..65535')
    frames = NetworkFrames(a.session,timeout=a.frame_timeout)
    sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4*1024*1024)
    sock.bind((a.udp_host,a.udp_port));sock.settimeout(.1)
    frames.socket_receive_buffer=sock.getsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF)
    drop_option=None
    if sys.platform.startswith('linux') and hasattr(sock,'recvmsg'):
        try:
            # Linux asm-generic/socket.h: cumulative drops for this socket.
            sock.setsockopt(socket.SOL_SOCKET,40,1)
            drop_option=40;frames.socket_dropped_packets=0
        except OSError:
            pass
    done = threading.Event()

    def receive():
        try:
            while not done.is_set():
                try:
                    if drop_option is None:
                        data,remote = sock.recvfrom(HEADER.size+CHUNK+1)
                    else:
                        data,control,flags,remote=sock.recvmsg(HEADER.size+CHUNK+1,socket.CMSG_SPACE(4))
                        if flags&socket.MSG_TRUNC:data=b''
                        for level,option,value in control:
                            if level==socket.SOL_SOCKET and option==drop_option and len(value)>=4:
                                with frames.lock:frames.socket_dropped_packets=struct.unpack_from('=I',value)[0]
                except socket.timeout:
                    continue
                if remote != (a.sender,a.sender_port):
                    with frames.lock:
                        frames.foreign_packets += 1
                    continue
                frames.accept(data)
        finally:
            with frames.lock:
                frames.stopped = True

    worker = threading.Thread(target=receive,name='pl-jpeg-receive',daemon=True)
    # A slow browser must not turn the TCP send queue into a video archive.
    server = ThreadingHTTPServer((a.host,a.port),handler(frames,stream_timeout=.5,send_buffer=65536))
    server.daemon_threads = True
    worker.start()
    print(f'PL JPEG receiver: http://{a.host}:{a.port}/; source {a.sender}:{a.sender_port}; session {a.session:08x}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        done.set();worker.join(timeout=1);sock.close();server.server_close()


if __name__ == '__main__':
    main()
