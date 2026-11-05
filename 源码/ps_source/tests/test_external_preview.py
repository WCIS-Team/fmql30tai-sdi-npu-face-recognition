"""Verify the offloaded viewer's bounded status-only HTTP adapter."""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import sys,threading,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'npu_photo'))
from external_preview import ExternalPreview


class TestExternalPreview(unittest.TestCase):
    def setUp(self):
        self.requests=[]
        self.payload=json.dumps(dict(ready=True,transport='PL_JPEG_WJP1_UDP',width=1920,height=1080,transcoding=False,encoded=3)).encode()
        self.redirect=False
        case=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_GET(self):
                case.requests.append(self.path)
                self.send_response(302 if case.redirect else 200)
                if case.redirect:self.send_header('Location','http://127.0.0.1:1/forbidden')
                self.send_header('Content-Length',str(len(case.payload)));self.end_headers();self.wfile.write(case.payload)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin=f'http://127.0.0.1:{self.server.server_port}'
        self.client=ExternalPreview(self.origin)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def test_images_are_direct_urls_and_only_status_is_fetched(self):
        self.assertEqual(self.client.stream(),self.origin+'/stream.mjpg')
        self.assertEqual(self.client.snapshot(),self.origin+'/snapshot.jpg')
        self.assertTrue(self.client.read_status()['ready'])
        self.assertEqual(self.requests,['/api/status'])

    def test_rejects_wrong_geometry_and_oversize(self):
        self.payload=json.dumps(dict(ready=True,transport='PL_JPEG_WJP1_UDP',width=960,height=540,transcoding=False)).encode()
        with self.assertRaises(ValueError):self.client.read_status()
        self.payload=b' '*16385
        with self.assertRaises(ValueError):self.client.read_status()

    def test_tunnel_origin_does_not_change_ps_status_destination(self):
        client=ExternalPreview(self.origin,browser_url='http://127.0.0.1:18092')
        self.assertEqual(client.stream(),'http://127.0.0.1:18092/stream.mjpg')
        self.assertEqual(client.snapshot(),'http://127.0.0.1:18092/snapshot.jpg')
        self.assertTrue(client.read_status()['ready'])
        self.assertEqual(self.requests,['/api/status'])
        with self.assertRaises(ValueError):ExternalPreview(self.origin,browser_url='http://example.com:18092')

    def test_does_not_follow_status_redirect(self):
        self.redirect=True
        with self.assertRaises(OSError):self.client.read_status()
        self.assertEqual(self.requests,['/api/status'])

    def test_requires_pinned_lan_origin(self):
        for value in ('http://example.com:80','http://8.8.8.8:80','https://192.168.1.102:80',
                      'http://192.168.1.102','http://u:p@192.168.1.102:80','http://192.168.1.102:80/other',
                      'http://192.168.1.102:80/?q=1','http://0.0.0.0:80'):
            with self.subTest(value=value),self.assertRaises(ValueError):ExternalPreview(value)


if __name__=='__main__':unittest.main()
