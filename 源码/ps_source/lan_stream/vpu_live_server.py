"""LAN MJPEG viewer for the vendor SDI -> VPU JPEG worker. No hardware access."""
import argparse
import json
import os
import socket
from pathlib import Path
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PAGE = """<!doctype html><meta charset=utf-8><title>SDI 内网直播</title>
<style>body{background:#14181f;color:#eee;font:18px sans-serif;margin:2rem}img{max-width:100%;width:960px}p{min-height:2em}</style>
<h1>SDI 内网直播</h1><p id=s>正在检查输入…</p><img id=v hidden>
<script>const s=document.querySelector('#s'),v=document.querySelector('#v');
const names={waiting_for_capture:'等待启动采集',waiting_for_sdi_lock:'等待 SDI 输入锁定',input_format_mismatch:'输入格式不匹配',ready:'直播中',stopped:'采集已停止',starting:'正在启动',no_fresh_frame:'暂无新画面',boot_changed_requires_review:'重启后等待检查',capture_failed_requires_reboot:'采集异常，等待恢复',hardware_error_requires_review:'设备状态待检查'};
async function update(){try{const r=await fetch('/api/status',{cache:'no-store'}),q=await r.json();
s.textContent=(q.source==='vtc'?'板内测试图（不是摄像头）':'摄像头')+' · '+(names[q.state]||q.state)+(q.ready?' · '+q.width+'×'+q.height+' · '+q.encoded+' 帧':'');
if(q.ready){v.hidden=false;if(v.dataset.session!==q.session){v.dataset.session=q.session;v.src='/stream.mjpg?session='+encodeURIComponent(q.session)}}
else{v.hidden=true;v.removeAttribute('src');v.dataset.session=''}}catch(e){s.textContent='连接中断';v.hidden=true;v.removeAttribute('src');v.dataset.session=''}}
v.onerror=()=>{v.dataset.session='';v.hidden=true};setInterval(update,1000);update();</script>""".encode()
H264_PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>摄像头实时预览</title>
<style>body{background:#14181f;color:#eee;font:18px sans-serif;margin:1rem}video{max-width:100%;width:1280px;background:#000}p{min-height:2em}</style>
<h1>摄像头实时预览</h1><p id=s>正在连接…</p><video id=v muted autoplay playsinline hidden></video><script src=/h264_player.js></script>
<script>const v=document.querySelector('#v'),s=document.querySelector('#s'),player=new H264Player(v,'/h264/',e=>{v.hidden=true;s.textContent=e.message});
async function update(){try{const r=await fetch('/api/status',{cache:'no-store'}),q=await r.json();if(!q.ready)throw Error('暂无新鲜摄像头画面');await player.start(q.session);v.hidden=false;s.textContent=q.width+'×'+q.height+' · H.264 · 实时预览';}catch(e){player.stop();v.hidden=true;s.textContent=e.message;}setTimeout(update,500);}update();</script>""".encode()


class Frames:
    def __init__(self, control, boot_file="/proc/sys/kernel/random/boot_id", frame_root="/dev/shm", process_alive=None):
        self.control = Path(control)
        self.boot_file = Path(boot_file)
        self.frame_root = Path(frame_root)
        self.process_alive = process_alive or (lambda pid: Path("/proc", str(pid), "stat").exists())

    def read_if_changed(self):
        """Recorder polling: skip duplicate packet reads, recheck health at 4 Hz."""
        now = time.monotonic()
        try:
            control_stat = self.control.stat()
            control_key = (control_stat.st_ino, control_stat.st_mtime_ns, control_stat.st_size)
            if getattr(self, '_poll_control_key', None) != control_key:
                cfg = json.loads(self.control.read_text())
                directory = Path(cfg['directory'])
                if directory.parent != self.frame_root or not directory.name.startswith('wcis-'):
                    raise ValueError('Unexpected frame directory')
                self._poll_frame = directory / 'latest.frame'
                self._poll_control_key = control_key
                self._poll_token = None
            st = self._poll_frame.stat()
            token = (control_key, st.st_ino, st.st_mtime_ns, st.st_size)
            if token == getattr(self, '_poll_token', None) and now < getattr(self, '_poll_health_at', 0):
                return None, None
            result = self.read()
            # Token is sampled before reading: a concurrent rename forces a reread.
            self._poll_token = token
            self._poll_health_at = now + .25
            return result
        except (OSError, ValueError, KeyError, TypeError):
            self._poll_token = None
            return self.read()

    def read(self):
        state = dict(ready=False, source="camera", state="waiting_for_capture")
        try:
            cfg = json.loads(self.control.read_text())
            state.update(source=cfg["source"], session=cfg["session"])
            boot = self.boot_file.read_text().strip()
            if boot != cfg["boot_id"]:
                state["state"] = "boot_changed_requires_review"
                return state, None
            directory = Path(cfg["directory"])
            if directory.parent != self.frame_root or not directory.name.startswith("wcis-"):
                raise ValueError("Unexpected frame directory")
            status = json.loads((directory / "status.json").read_text())
            state.update(status)
            if status["boot_id"] != boot or status["source"] != cfg["source"] or status["pid"] != cfg["pid"]:
                raise ValueError("Capture session mismatch")
            if status["state"] != "ready":
                return state, None
            if not self.process_alive(cfg["pid"]):
                raise ValueError("Capture process is gone")
            if status.get('codec') in ('raw_uyvy_external_test','raw_nv12_external_test'):
                media=json.loads((directory/'external-video.json').read_text())
                if (not media.get('ready') or any(media.get(key)!=cfg[key] for key in ('boot_id','pid','session'))
                        or not 0<=time.monotonic()-media['updated_at']<=2.5
                        or (media.get('width'),media.get('height'))!=(status['width'],status['height'])
                        or not all(self.process_alive(media[key]) for key in ('encoder_pid','muxer_pid'))):
                    raise ValueError('External H264 worker is unavailable')
                state.update(media)
                age=time.monotonic()-media['h264_encoded_at']
                state.update(ready=0<=age<=4,frame_age_s=age)
                if not state['ready']:state['state']='no_fresh_frame'
                return state,None
            if status.get('codec') == 'h264':
                age = time.monotonic()-status.get('h264_encoded_at',0)
                state.update(ready=0 <= age <= 2.5, frame_age_s=age)
                if not state['ready']:state['state']='no_fresh_frame'
                return state, None
            with (directory / "latest.frame").open("rb") as f:
                packet = f.read(5 * 1024 * 1024 + 16385)
            if len(packet) < 8:
                raise ValueError("Short frame")
            n = struct.unpack_from("<I", packet)[0]
            if not 0 < n <= 16384 or len(packet) > 5 * 1024 * 1024 + 16384:
                raise ValueError("Frame bounds")
            info = json.loads(packet[4:4+n])
            jpeg = packet[4+n:]
            if any(info[key] != cfg[key] for key in ("boot_id", "pid", "source")):
                raise ValueError("Frame belongs to a different session")
            age = time.monotonic() - info["captured_at"]
            if not 0 <= age <= 2:
                state.update(state="no_fresh_frame", frame_age_s=age)
                return state, None
            if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
                raise ValueError("Incomplete JPEG")
            state.update(info, ready=True, session=cfg["session"], frame_age_s=age)
            return state, jpeg
        except (OSError, ValueError, KeyError, TypeError, struct.error):
            state.update(ready=False)
            if state["state"] == "ready":
                state["state"] = "no_valid_frame"
            return state, None

    def read_preview(self):
        """Web-only latest JPEG; read() remains the recorder's H264 source."""
        state, jpeg = self.read()
        if state.get('web_preview_codec') != 'mjpeg':
            return state, jpeg
        state = dict(state, recording_codec=state.get('codec'), codec='mjpeg')
        try:
            if not state.get('ready'):
                return state, None
            cfg = json.loads(self.control.read_text())
            if any(cfg[k] != state[k] for k in ('boot_id', 'pid', 'session')):
                raise ValueError('Preview owner changed')
            directory = Path(cfg['directory'])
            path = directory / 'preview-jpeg.frame'
            if directory.parent != self.frame_root or not directory.name.startswith('wcis-') or directory.is_symlink() or path.is_symlink():
                raise ValueError('Unexpected preview path')
            with path.open('rb') as f:
                packet = f.read(2 * 1024 * 1024 + 16389)
            if not 8 <= len(packet) <= 2 * 1024 * 1024 + 16388:
                raise ValueError('Preview packet bounds')
            n = struct.unpack_from('<I', packet)[0]
            if not 0 < n <= 16384 or n + 4 >= len(packet):
                raise ValueError('Preview metadata bounds')
            info = json.loads(packet[4:4+n]); jpeg = packet[4+n:]
            if any(info[k] != state[k] for k in ('boot_id', 'pid', 'source', 'width', 'height')) or info.get('codec') != 'mjpeg':
                raise ValueError('Preview frame identity mismatch')
            age = time.monotonic() - info['captured_at']
            if not 0 <= age <= 1 or not isinstance(info['frame_id'], int) or info['frame_id'] <= 0:
                raise ValueError('No fresh preview frame')
            if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
                raise ValueError('Incomplete preview JPEG')
            state.update(info, ready=True, frame_age_s=age)
            return state, jpeg
        except (OSError, ValueError, KeyError, TypeError, struct.error):
            state.update(ready=False, state='no_fresh_web_preview')
            return state, None


def handler(frames,*,stream_timeout=5,send_buffer=None):
    slots = threading.BoundedSemaphore(4)
    preview_read = getattr(frames, "read_preview", frames.read)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, code, content_type, data):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.connection.settimeout(5)
            url = urlsplit(self.path)
            path = url.path
            if path=='/h264/live.mp4':
                # The standalone viewer shares the photo service's one live cache.
                # It never opens a second encoder or SDK owner.
                state,_=frames.read()
                if not state.get('ready') or not slots.acquire(blocking=False):
                    return self.send(503,'text/plain',b'No fresh H264 preview')
                import http.client
                connection=http.client.HTTPConnection('127.0.0.1',8091,timeout=2)
                started=False
                try:
                    connection.request('GET','/api/camera/h264/live.mp4'+('?' + url.query if url.query else ''))
                    response=connection.getresponse()
                    if response.status!=200:return self.send(503,'text/plain',b'No fresh H264 preview')
                    self.send_response(200)
                    for key in ('Content-Type','X-Live-Codec','X-Live-End','X-Capture-End'):
                        self.send_header(key,response.getheader(key,''))
                    self.send_header('Connection','close');self.send_header('Cache-Control','no-store');self.end_headers()
                    started=True;self.close_connection=True;self.connection.settimeout(1)
                    while True:
                        data=response.read1(32768)
                        if not data:break
                        self.wfile.write(data);self.wfile.flush()
                except (OSError,http.client.HTTPException):
                    if not started:self.send(503,'text/plain',b'No fresh H264 preview')
                finally:
                    connection.close();slots.release()
                return
            if path.startswith('/h264/'):
                from h264_media import media
                try:
                    kind, data = media(frames, path[len('/h264/'):], parse_qs(url.query).get('session',[None])[0])
                    return self.send(200,kind,data)
                except (OSError,ValueError,KeyError,RuntimeError):
                    return self.send(503,'text/plain',b'No fresh H264 media')
            if path == "/":
                state,_=preview_read()
                return self.send(200, "text/html; charset=utf-8", H264_PAGE if state.get('codec')=='h264' else PAGE)
            if path=='/h264_player.js':
                return self.send(200,'text/javascript; charset=utf-8',Path(__file__).with_name('h264_player.js').read_bytes())
            if path == "/api/status":
                state, _ = preview_read()
                return self.send(200, "application/json", json.dumps(state).encode())
            if path == "/snapshot.jpg":
                state, jpeg = preview_read()
                return self.send(200, "image/jpeg", jpeg) if state["ready"] and jpeg is not None else self.send(503, "text/plain", b"No JPEG snapshot; use H264 preview")
            if path != "/stream.mjpg":
                return self.send(404, "text/plain", b"Not found")
            if not slots.acquire(blocking=False):
                return self.send(503, "text/plain", b"Viewer limit reached")
            try:
                state, jpeg = preview_read()
                if state.get('codec')=='h264':
                    return self.send(410,'text/plain',b'Use /h264/manifest.json for H264 preview')
                if not state["ready"]:
                    return self.send(503, "text/plain", b"No fresh frame")
                requested = parse_qs(url.query).get("session", [state["session"]])[0]
                if requested != state["session"]:
                    return self.send(409, "text/plain", b"Capture session changed")
                session, last = state["session"], None
                self.connection.settimeout(stream_timeout)
                if send_buffer is not None:self.connection.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,send_buffer)
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                while True:
                    state, jpeg = preview_read()
                    if not state["ready"] or state["session"] != session:
                        break
                    if state["frame_id"] != last:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpeg)).encode() + b"\r\nX-Frame-Id: " + str(state["frame_id"]).encode() + b"\r\n\r\n")
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                        last = state["frame_id"]
                    time.sleep(.01)
                self.wfile.write(b"--frame--\r\n")
            except (OSError, BrokenPipeError):
                pass
            finally:
                slots.release()

    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--host", default="192.168.1.113")
    parser.add_argument("--port", type=int, default=8092)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), handler(Frames(args.control))).serve_forever()
