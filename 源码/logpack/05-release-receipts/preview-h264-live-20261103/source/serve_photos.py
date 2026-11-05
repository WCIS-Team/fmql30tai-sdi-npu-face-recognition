"""LAN photo input and result viewer for the validated board face project."""
import argparse,base64,hashlib,json,os,shutil,signal,tempfile,threading,time,uuid
from contextlib import nullcontext
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote,urlsplit,parse_qs
from recognize_photo import recognize
from gallery import Gallery
from persistent_gallery import PersistentGallery
from model_backend_runtime import ModelBackend
from camera_requests import CameraRequests

parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,required=True)
parser.add_argument('--site',type=Path,required=True)
parser.add_argument('--host',default='192.168.1.113')
parser.add_argument('--port',type=int,default=8091)
parser.add_argument('--pl-executable',type=Path,required=True)
parser.add_argument('--npu-cache-executable',type=Path,required=True)
parser.add_argument('--gallery-store',type=Path)
parser.add_argument('--gallery-mount',type=Path)
parser.add_argument('--gallery-uuid')
parser.add_argument('--camera-control',type=Path)
parser.add_argument('--camera-owner-executable',type=Path)
parser.add_argument('--camera-owner-sha256')
parser.add_argument('--camera-owner-control',type=Path)
parser.add_argument('--camera-owner-fps',type=int,default=30,choices=range(1,31))
parser.add_argument('--camera-native-inputs',action='store_true',help='Fuse FAC1 tensor preparation with NPU forwarding in the native owner')
parser.add_argument('--camera-pad-bundle',type=Path,help='Same-frame PAD model evidence in the single owner; not security-calibrated access control')
parser.add_argument('--camera-pl-preview-url',help='LAN PL receiver origin; browser receives JPEG directly, PS captures only for inference')
parser.add_argument('--camera-pl-preview-browser-url',help='Optional browser-accessible LAN/tunnel origin when different from the PS receiver address')
args=parser.parse_args()
if args.camera_owner_executable and (args.camera_control or not args.camera_owner_sha256 or not args.camera_owner_control):
    parser.error('Single owner requires its SHA and control path, without the legacy camera-control')
if args.camera_pl_preview_url and not args.camera_owner_executable:parser.error('PL preview requires the single camera owner')
if args.camera_pad_bundle and not args.camera_owner_executable:parser.error('PAD requires the single camera owner')
if args.camera_pl_preview_browser_url and not args.camera_pl_preview_url:parser.error('A browser preview origin requires the PL receiver origin')
external_preview=None
if args.camera_pl_preview_url:
    from external_preview import ExternalPreview
    external_preview=ExternalPreview(args.camera_pl_preview_url,browser_url=args.camera_pl_preview_browser_url)
if any((args.gallery_store,args.gallery_mount,args.gallery_uuid)) and not all((args.gallery_store,args.gallery_mount,args.gallery_uuid)):
    parser.error('Persistent gallery requires store, mount and UUID together')
if not args.pl_executable.is_file():raise RuntimeError('Configured PL executable is missing; no CPU fallback')
busy=threading.Lock()
camera_requests=CameraRequests()
closing=threading.Event()
stream_slots=threading.BoundedSemaphore(4)
evidence=json.loads((args.root/'run-01/verification.json').read_text())
if not evidence['all_passed']:
    raise RuntimeError('Only a validated model release may serve photo requests')
gallery=(PersistentGallery(args.root,args.gallery_store,args.gallery_mount,args.gallery_uuid)
         if args.gallery_store else Gallery(args.root))
owner_workspace=None;owner_frames=None;h264_packager=None;external_h264=None
if args.camera_owner_executable:
    from camera_owner_runtime import CameraOwner
    from vpu_live_server import Frames
    owner_workspace=tempfile.TemporaryDirectory(prefix='wcis-owner-',dir='/dev/shm')
    if os.environ.get('WCIS_PREVIEW_CODEC')=='h264':
        if os.environ.get('WCIS_PREVIEW_SIZE','540')!='540':
            raise RuntimeError('The integrated H264 worker currently supports the verified 540p capture path only')
        from external_h264 import ExternalH264
        external_h264=ExternalH264(owner_workspace.name,fps=args.camera_owner_fps)
        os.environ.update(external_h264.environment())
    try:
        model_backend=CameraOwner(args.root,args.camera_owner_executable,args.camera_owner_sha256,Path(owner_workspace.name),seconds=0,fps=args.camera_owner_fps,native_inputs=args.camera_native_inputs,preview_mode='pl' if external_preview else 'vpu',pad_bundle=args.camera_pad_bundle)
    except BaseException:
        if external_h264 is not None:external_h264.close(abort=True)
        raise
    owner_control=dict(source='camera',boot_id=model_backend.boot,pid=model_backend.process.pid,
                       session=Path(owner_workspace.name).name[len('wcis-owner-'):],directory=owner_workspace.name)
    from run_photos import save
    save(args.camera_owner_control,owner_control);owner_frames=Frames(args.camera_owner_control)
    if external_h264 is not None:
        external_h264.attach(model_backend,owner_control)
    elif os.environ.get('WCIS_PREVIEW_CODEC')=='h264':
        from h264_packager import H264Packager
        h264_packager=H264Packager(owner_frames);h264_packager.start()
else:model_backend=ModelBackend(args.root,args.npu_cache_executable)
if args.camera_control:
    from camera_interlock import CameraInterlock
    camera_control=CameraInterlock(args.camera_control,args.root)
else:camera_control=None

def infer(photo,out,*,from_camera=False,**kwargs):
    if owner_frames is not None:
        if from_camera:
            result,jpeg=model_backend.infer_camera(out,gallery.templates());photo.write_bytes(jpeg.read_bytes())
        else:
            result=recognize(args.root,photo,out,gallery.templates(),pl_executable=args.pl_executable,
                             model_backend=model_backend,**kwargs)
            result.update(input_source='uploaded_photo',presentation_attack_detection={'status':'not_evaluated','security_calibrated':False})
        if not from_camera:result['model_lifecycle']='single_owner_cpu_models'
        return result
    if from_camera and camera_control is None:raise RuntimeError('Camera input is not configured')
    with (camera_control.request(snapshot=from_camera) if camera_control else nullcontext(None)) as sample:
        if sample is not None:photo.write_bytes(sample['data'])
        result=recognize(args.root,photo,out,gallery.templates(),pl_executable=args.pl_executable,
                         model_backend=model_backend,save_aligned=not from_camera,**kwargs)
        result['input_source']='camera_snapshot' if from_camera else 'uploaded_photo'
        result['presentation_attack_detection']={'status':'not_evaluated','security_calibrated':False}
        if sample is not None:
            result['camera_frame']=sample['identity']
            result['timing']['camera_handoff']=sample['handoff_timing_ms']
        return result

class Handler(SimpleHTTPRequestHandler):
    def reply(self,code,data):
        value=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(value)));self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(value)

    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/camera/h264/live.mp4':
            acquired=False;started=False
            try:
                session=parse_qs(urlsplit(self.path).query).get('session',[None])[0]
                if external_h264 is None or session!=external_h264.identity['session']:
                    raise RuntimeError('Camera session changed')
                model_backend.guard();state,_=owner_frames.read()
                if not state['ready'] or state['session']!=session:
                    raise RuntimeError('No fresh camera')
                init,rows=external_h264.live.read()
                acquired=stream_slots.acquire(blocking=False)
                if not acquired:raise RuntimeError('Preview connections full')
                import socket
                self.connection.settimeout(1)
                self.connection.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,65536)
                offset=init.find(b'avcC')
                if offset<0:raise RuntimeError('Missing live codec')
                codec='avc1.'+init[offset+5:offset+8].hex()
                self.send_response(200);self.send_header('Content-Type','video/mp4')
                self.send_header('Cache-Control','no-store');self.send_header('Connection','close')
                self.send_header('X-Live-Codec',codec)
                self.send_header('X-Live-End',str(rows[-1]['end']))
                self.send_header('X-Capture-End',str(rows[-1]['capture']['end']))
                self.end_headers();started=True;self.close_connection=True
                self.wfile.write(init+b''.join(row['data'] for row in rows));self.wfile.flush()
                last=rows[-1]['sequence'];checked=time.monotonic()
                while not closing.is_set():
                    if time.monotonic()-checked>=.25:
                        model_backend.guard();state,_=owner_frames.read()
                        if not state['ready'] or state['session']!=session:break
                        checked=time.monotonic()
                    _,rows=external_h264.live.read(last)
                    if not rows:external_h264.live.wait();continue
                    self.wfile.write(b''.join(row['data'] for row in rows));self.wfile.flush()
                    last=rows[-1]['sequence']
            except (OSError,ValueError,KeyError,RuntimeError,TypeError):
                if not started:return self.reply(503,{'error':'等待新鲜 H.264 画面'})
            finally:
                if acquired:stream_slots.release()
            return
        if path=='/api/camera/h264/live-status':
            try:
                model_backend.guard();init,rows=external_h264.live.read()
                last=rows[-1]
                return self.reply(200,dict(external_h264.identity,ready=True,pts_end=last['end'],
                    capture_end=last['capture']['end'],published_at=last['published_at'],
                    now=time.monotonic(),sequence=last['sequence'],cache_bytes=external_h264.live.bytes))
            except (OSError,ValueError,KeyError,RuntimeError,AttributeError):
                return self.reply(503,{'ready':False})
        if path=='/h264_player.js':
            data=Path(__file__).with_name('h264_player.js').read_bytes()
            self.send_response(200);self.send_header('Content-Type','text/javascript; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();return self.wfile.write(data)
        if path.startswith('/api/camera/h264/'):
            try:
                if owner_frames is None:raise RuntimeError('Continuous camera is unavailable')
                model_backend.guard()
                from h264_media import media
                session=parse_qs(urlsplit(self.path).query).get('session',[None])[0]
                kind,data=media(owner_frames,path[len('/api/camera/h264/'):],session)
                self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();return self.wfile.write(data)
            except (OSError,ValueError,KeyError,RuntimeError):return self.reply(503,{'error':'等待新鲜 H.264 画面'})
        if external_preview and path in ('/api/camera/status','/api/camera/stream.mjpg','/api/camera/preview.jpg'):
            try:
                model_backend.guard()
                if path.endswith('/status'):return self.reply(200,external_preview.read_status())
                target=external_preview.stream() if path.endswith('/stream.mjpg') else external_preview.snapshot()
                self.send_response(302);self.send_header('Location',target);self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length','0');self.end_headers();return
            except (RuntimeError,OSError,ValueError,KeyError):return self.reply(503,{'error':'PL 摄像头预览暂不可用'})
        if path in ('/api/camera/status','/api/camera/stream.mjpg'):
            if owner_frames is None:return self.reply(404,{'error':'Continuous camera owner is not configured'})
            try:
                model_backend.guard();state,jpeg=owner_frames.read()
                if path.endswith('/status'):return self.reply(200,state)
                if state.get('codec')=='h264':return self.reply(410,{'error':'Preview uses H264; use /api/camera/h264/manifest.json'})
                if not state['ready']:return self.reply(503,{'error':'暂无新鲜摄像头画面'})
            except (RuntimeError,OSError,ValueError,KeyError):return self.reply(503,{'error':'摄像头暂不可用'})
            if not stream_slots.acquire(blocking=False):return self.reply(503,{'error':'预览连接数已满'})
            try:
                self.connection.settimeout(3)
                session=state['session'];last=None
                self.send_response(200);self.send_header('Content-Type','multipart/x-mixed-replace; boundary=frame')
                self.send_header('Cache-Control','no-store');self.send_header('X-Capture-Session',session);self.end_headers()
                while not closing.is_set():
                    model_backend.guard();state,jpeg=owner_frames.read()
                    if not state['ready'] or state['session']!=session:break
                    if state['frame_id']!=last:
                        self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(jpeg)).encode()+b'\r\nX-Frame-Id: '+str(state['frame_id']).encode()+b'\r\n\r\n'+jpeg+b'\r\n')
                        self.wfile.flush();last=state['frame_id']
                    closing.wait(.01)
            except (RuntimeError,OSError,ValueError,KeyError):pass
            finally:stream_slots.release()
        elif path=='/api/camera/preview.jpg':
            try:
                if owner_frames is not None:
                    model_backend.guard();state,jpeg=owner_frames.read()
                    if not state['ready'] or jpeg is None:raise RuntimeError('Continuous JPEG snapshots are unavailable; use H264 preview or request detection')
                    sample=dict(data=jpeg,identity=dict(frame_id=state['frame_id'],session=state['session']))
                else:
                    if camera_control is None:raise RuntimeError('Camera input is not configured')
                    boot=camera_control.guard()
                    if camera_control.state()!='active':raise RuntimeError('Camera is paused for inference')
                    sample=camera_control.snapshot(camera_control.current(boot))
                self.send_response(200);self.send_header('Content-Type','image/jpeg')
                self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(sample['data'])))
                self.send_header('X-Frame-Id',str(sample['identity']['frame_id']))
                self.send_header('X-Capture-Session',sample['identity']['session'])
                self.end_headers();self.wfile.write(sample['data'])
            except (RuntimeError,OSError,ValueError,KeyError):self.reply(503,{'error':'暂无新鲜摄像头画面'})
        elif path=='/api/gallery':
            self.reply(200,gallery.public())
        elif path.startswith('/gallery-media/'):
            try:
                photo_id=path[len('/gallery-media/'):]
                image,mime=(gallery.media(photo_id) if args.gallery_store else
                            (gallery.photo_path(photo_id).read_bytes(),'image/png'))
                self.send_response(200);self.send_header('Content-Type',mime)
                self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(image)))
                self.end_headers();self.wfile.write(image)
            except (KeyError,FileNotFoundError):self.reply(404,{'error':'登记照片不存在'})
        elif path=='/api/health':
            model_ready=not model_backend.broken
            if owner_frames is not None:model_ready=model_ready and model_backend.process.poll() is None
            storage_ready=True
            if args.gallery_store:
                try:gallery.guard()
                except (RuntimeError,OSError):storage_ready=False
            hardware_ready=True
            if camera_control:
                try:camera_control.guard()
                except (RuntimeError,OSError,ValueError):hardware_ready=False
            if owner_frames is not None:
                try:model_backend.guard()
                except (RuntimeError,OSError,ValueError):hardware_ready=False
            ready=model_ready and storage_ready and hardware_ready
            self.reply(200 if ready else 503,{'status':'ready' if ready else 'unavailable','backend':'zg330_npu_pl_and_host',
                            'preprocessing_backend':'FAC1_customop_PL','release':str(args.root),
                            'frame_transport':'single_upload_retained_PL_DDR',
                            'model_lifecycle':('single_owner_cached_sessions' if model_backend.ready.get('session_cache_enabled') else 'single_owner_cpu_models') if owner_frames is not None else 'resident_process_per_model',
                            'model_cache_ready':model_ready,
                            'npu_session_cache_enabled':bool(model_backend.ready.get('session_cache_enabled')) if owner_frames is not None else False,
                            'hardware_admission_ready':hardware_ready,
                            'validation_passed':True,'photo_input':True,'camera_input':camera_control is not None or owner_frames is not None,
                            'camera_input_mode':'single_owner_raw_sdi' if owner_frames is not None else (('warm_snapshot_handoff' if camera_control.config.get('handoff')=='warm_process' else 'snapshot_pause_capture') if camera_control else None),
                            'camera_capture_scheduler':('on_demand' if external_preview else 'continuous') if owner_frames is not None or camera_control else None,
                            'camera_preview_transport':('PL_JPEG_WJP1_UDP' if external_preview else ('PS_VPU_H264' if os.environ.get('WCIS_PREVIEW_CODEC')=='h264' else 'PS_VPU_JPEG')) if owner_frames is not None or camera_control else None,
                            'presentation_attack_detection':'same_frame_model_evidence' if args.camera_pad_bundle else 'not_evaluated',
                            'pad_security_calibrated':False,
                            'pad_face_limit':4 if args.camera_pad_bundle else 0,
                            'pad_result_scope':'per_face' if args.camera_pad_bundle else 'not_evaluated',
                            'camera_request_policy':'share_inflight_only',
                            'gallery_management':True,
                            'gallery_storage':'emmc' if args.gallery_store else 'sd',
                            'gallery_storage_ready':storage_ready,
                            'gallery_storage_policy':'one_original_per_person' if args.gallery_store else 'image_per_sample',
                            'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()})
        else:
            super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path=='/api/recognize-camera' and self.headers.get('Content-Length')=='0':
            response=camera_requests.run(self.post_response)
        else:response=self.post_response()
        self.reply(*response)

    def post_response(self):
        if closing.is_set():return 503,{'error':'服务正在更新，请稍后重试'}
        path=urlsplit(self.path).path
        if path not in ('/api/recognize','/api/enroll','/api/recognize-camera'):
            return 404,{'error':'Unknown request'}
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:length=0
        from_camera=path=='/api/recognize-camera'
        if (from_camera and length!=0) or (not from_camera and not 0<length<=8*1024*1024):
            return 413,{'error':'照片需在 8 MB 以内'}
        if not busy.acquire(blocking=False):
            return 409,{'error':'正在处理照片或人员库操作，请稍后再试'}
        record=None;camera_temp=None
        try:
            self.connection.settimeout(15)
            data=self.rfile.read(length)
            if len(data)!=length:raise ValueError('照片传输不完整')
            key=uuid.uuid4().hex
            if from_camera or owner_frames is not None:
                camera_temp=tempfile.TemporaryDirectory(prefix='request-',dir=model_backend.work) if owner_frames is not None else tempfile.TemporaryDirectory(prefix='wcis-camera-request-',dir='/dev/shm')
                record=Path(camera_temp.name)
            else:
                record=args.root.parents[1]/'runtime'/key;record.mkdir(parents=True)
            photo=record/'input';photo.write_bytes(data)
            name=Path(unquote(self.headers.get('X-Photo-Name','上传照片'))).name[:128]
            if from_camera:name='SDI现场帧'
            if path=='/api/enroll':
                person=gallery.check_new(unquote(self.headers.get('X-Person-Name','')),hashlib.sha256(data).hexdigest())
                result=infer(photo,record/'job',return_embedding=True,require_single_face=True)
                if result['face_count']!=1:
                    response=(422,{'error':'登记照片必须恰好包含一张人脸','status':result['status']})
                else:
                    updated=gallery.add(person,photo,result['embedding'],name)
                    response=(200,{'gallery':updated,'name':person,'elapsed_ms':result['elapsed_ms']})
            else:
                result=infer(photo,record/'job',from_camera=from_camera)
                aligned=None
                if from_camera:
                    # Return the JPEG of the same selected camera frame. Raw
                    # owner input has a separate RGB565 SHA; no per-frame SD files.
                    preview_url='data:image/jpeg;base64,'+base64.b64encode(photo.read_bytes()).decode('ascii')
                else:
                    images=args.site/'uploads';images.mkdir(exist_ok=True)
                    import cv2
                    preview=images/(key+'.jpg')
                    if not cv2.imwrite(str(preview),cv2.imread(str(photo),cv2.IMREAD_COLOR|cv2.IMREAD_IGNORE_ORIENTATION),
                                       [cv2.IMWRITE_JPEG_QUALITY,85]):
                        raise RuntimeError('Cannot write photo preview')
                    preview_url='uploads/'+key+'.jpg'
                    if result.get('aligned'):
                        shutil.copyfile(result['aligned'],images/(key+'-aligned.png'))
                        aligned='uploads/'+key+'-aligned.png'
                response=(200,{'entry':{'file':name,'role':'live','image':preview_url,'aligned':aligned,
                                        'backend':result['backend'],'sha256':result['photo_sha256'],
                                        'face':result.get('face'),'faces':result['faces'],'result':result,'url':None}})
        except ValueError as error:
            response=(400,{'error':str(error)})
        except (RuntimeError,BlockingIOError) as error:
            response=(503,{'error':str(error)})
        except Exception as error:
            response=(500,{'error':str(error)})
        finally:
            try:
                if camera_temp is not None:camera_temp.cleanup()
                # Enrollment inference files are transient. The persistent
                # gallery retains the original only for a person's first sample.
                if args.gallery_store and path=='/api/enroll' and record is not None and camera_temp is None:
                    if record.parent!=args.root.parents[1]/'runtime' or len(record.name)!=32:
                        raise RuntimeError('Unexpected enrollment work directory')
                    shutil.rmtree(record)
            except (OSError,RuntimeError):
                response=(503,{'error':'登记临时文件清理失败，请检查存储；请刷新登记库确认本次结果'})
            finally:busy.release()
        # Release admission only after durable storage and enrollment cleanup.
        # Otherwise an immediate next upload can receive a spurious busy reply.
        return response

    def do_DELETE(self):
        if closing.is_set():self.reply(503,{'error':'服务正在更新，请稍后重试'});return
        pieces=urlsplit(self.path).path.strip('/').split('/')
        if len(pieces) not in (3,4) or pieces[:2]!=['api','gallery']:
            self.reply(404,{'error':'Unknown request'});return
        if not busy.acquire(blocking=False):
            self.reply(409,{'error':'正在处理照片，请稍后再试'});return
        try:self.reply(200,gallery.delete(pieces[2],pieces[3] if len(pieces)==4 else None))
        except KeyError as error:self.reply(404,{'error':str(error)})
        except Exception as error:self.reply(500,{'error':str(error)})
        finally:busy.release()

server=ThreadingHTTPServer((args.host,args.port),partial(Handler,directory=str(args.site)))
server.daemon_threads=False
def stop(signum,frame):
    closing.set();threading.Thread(target=server.shutdown,daemon=True).start()
signal.signal(signal.SIGTERM,stop)
print('Photo face service ready',args.host,args.port,flush=True)
try:server.serve_forever()
finally:
    server.server_close()
    if h264_packager is not None:h264_packager.close()
    model_backend.close()
    if external_h264 is not None:external_h264.close()
    if owner_workspace is not None:owner_workspace.cleanup()
