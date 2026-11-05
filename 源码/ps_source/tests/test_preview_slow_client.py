"""A stalled MJPEG viewer must release its bounded connection slot."""
import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import socket,sys,threading,time,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lan_stream'))
from vpu_live_server import handler


class Frames:
    def __init__(self):self.counter=0;self.jpeg=b'\xff\xd8'+b'x'*(2*1024*1024)+b'\xff\xd9'
    def read(self):
        self.counter+=1
        return dict(ready=True,session='slow-client-test',frame_id=self.counter),self.jpeg


class TestSlowViewer(unittest.TestCase):
    def test_stalled_clients_release_slots(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(Frames(),stream_timeout=.5,send_buffer=65536))
        server.daemon_threads=True
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        sockets=[]
        def response():
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
            connection.request('GET','/stream.mjpg');reply=connection.getresponse()
            result=reply.status;connection.close();return result
        try:
            for _ in range(4):
                client=socket.socket();client.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4096)
                client.settimeout(2);client.connect(('127.0.0.1',server.server_port))
                client.sendall(b'GET /stream.mjpg HTTP/1.1\r\nHost: localhost\r\n\r\n')
                header=b''
                while b'\r\n\r\n' not in header:header+=client.recv(1)
                self.assertIn(b' 200 ',header.split(b'\r\n')[0]);sockets.append(client)
            self.assertEqual(response(),503)
            time.sleep(.8)
            self.assertEqual(response(),200)
        finally:
            for client in sockets:client.close()
            server.shutdown();server.server_close();worker.join(2)


if __name__=='__main__':unittest.main()
