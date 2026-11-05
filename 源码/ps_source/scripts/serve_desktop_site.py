"""Loopback-only access to the board website for desktop webcam enrollment.

Run on the computer whose webcam will be used. Does not install services,
change the board, or publish a listener to the LAN.
"""
import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import threading
from urllib.parse import urlsplit

HOP_HEADERS = {'connection', 'keep-alive', 'proxy-authenticate',
               'proxy-authorization', 'te', 'trailer', 'transfer-encoding',
               'upgrade', 'host', 'content-length', 'accept-encoding'}
MAX_UPLOAD = 8 * 1024 * 1024


def make_handler(board_host, board_port, local_port, recorder_port):
    allowed_hosts = {f'localhost:{local_port}', f'127.0.0.1:{local_port}'}
    allowed_origins = {f'http://{host}' for host in allowed_hosts}

    class Proxy(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def log_message(self, *args):
            pass

        def error_json(self, code, message):
            data = json.dumps({'error': message}, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(data)

        def proxy(self):
            # Do not turn this loopback endpoint into a cross-origin LAN proxy.
            if self.headers.get('Host', '').lower() not in allowed_hosts:
                return self.error_json(403, 'Only localhost access is allowed')
            origin = self.headers.get('Origin')
            if origin and origin not in allowed_origins:
                return self.error_json(403, 'Cross-origin requests are not allowed')
            if self.headers.get('Sec-Fetch-Site') == 'cross-site' and self.command not in ('GET', 'HEAD'):
                return self.error_json(403, 'Cross-site writes are not allowed')
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or not self.path.startswith('/') or self.path.startswith('//'):
                return self.error_json(400, 'Invalid request path')
            if self.headers.get('Transfer-Encoding'):
                return self.error_json(400, 'A fixed request length is required')
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                return self.error_json(400, 'Invalid request length')
            if not 0 <= length <= MAX_UPLOAD:
                return self.error_json(413, 'Photo must be at most 8 MB')
            self.connection.settimeout(20)
            connection = http.client.HTTPConnection(board_host, board_port, timeout=20)
            sent = False
            try:
                body = self.rfile.read(length) if length else b''
                if len(body) != length:
                    return self.error_json(400, 'Incomplete request body')
                headers = {k: v for k, v in self.headers.items()
                           if k.lower() not in HOP_HEADERS | {'origin', 'referer'}}
                headers['Content-Length'] = str(length)
                connection.request(self.command, self.path, body=body, headers=headers)
                response = connection.getresponse()
                rewritten = None
                if (board_port == 8091 and self.command == 'GET'
                        and parsed.path in ('/', '/index.html')
                        and response.status == 200
                        and 'text/html' in response.getheader('Content-Type', '')):
                    data = response.read(2 * 1024 * 1024 + 1)
                    if len(data) > 2 * 1024 * 1024:
                        return self.error_json(502, 'Unexpected website size')
                    # All recorder URLs remain relative to a separate loopback
                    # proxy; no browser request needs cross-origin camera access.
                    hostname = self.headers['Host'].split(':', 1)[0]
                    meta = f'<meta name="wcis-recorder-url" content="http://{hostname}:{recorder_port}/">'.encode()
                    rewritten = data.replace(b'</head>', meta + b'</head>', 1)
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in HOP_HEADERS | {'server', 'date'}:
                        self.send_header(key, value)
                if rewritten is not None:
                    self.send_header('Content-Length', str(len(rewritten)))
                elif response.getheader('Content-Length') is not None:
                    self.send_header('Content-Length', response.getheader('Content-Length'))
                self.send_header('Connection', 'close')
                self.end_headers()
                sent = True
                if self.command == 'HEAD':
                    return
                if rewritten is not None:
                    self.wfile.write(rewritten)
                else:
                    while True:
                        chunk = response.read1(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
            except (OSError, http.client.HTTPException):
                if not sent:
                    self.error_json(502, '无法连接板卡，请确认板卡 IP、网络和网页服务。')
            finally:
                connection.close()
                self.close_connection = True

        do_GET = proxy
        do_HEAD = proxy
        do_POST = proxy
        do_DELETE = proxy

    return Proxy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board-host', default='192.168.1.113', type=ipaddress.IPv4Address)
    parser.add_argument('--port', type=int, default=18091)
    parser.add_argument('--recorder-port', type=int, default=18093)
    args = parser.parse_args()
    if args.port == args.recorder_port or not all(1024 <= port <= 65535 for port in (args.port, args.recorder_port)):
        parser.error('Choose two different ports between 1024 and 65535')
    servers = []
    try:
        for local_port, upstream in [(args.port, 8091), (args.recorder_port, 8093)]:
            server = ThreadingHTTPServer(('127.0.0.1', local_port), make_handler(str(args.board_host), upstream, local_port, args.recorder_port))
            server.daemon_threads = True
            servers.append(server)
        for server in servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f'Open http://localhost:{args.port}/#database on this computer. Ctrl+C stops the helper.', flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:
            server.server_close()


if __name__ == '__main__':
    main()
