"""Identify one board-local photo using the validated NPU enrollment gallery."""
import argparse,fcntl,json,os,subprocess,time
from pathlib import Path
os.environ.setdefault('OPENCV_IO_MAX_IMAGE_PIXELS','16000000')
import cv2
from run_photos import prepare,sha,save
from recognize_frame import infer_prepared

def recognize(root,photo,out,gallery=None,return_embedding=False,pl_executable=None,model_backend=None,
              require_single_face=False,save_aligned=True):
    request_started=time.monotonic()
    root,photo,out=Path(root),Path(photo),Path(out)
    if model_backend is not None and model_backend.root.resolve()!=root.resolve():
        raise ValueError('Model cache belongs to a different release')
    config=json.loads((root/'models.json').read_text())
    evidence=json.loads((root/'run-01/verification.json').read_text())
    if gallery is None:
        from gallery import Gallery
        gallery=Gallery(root).templates()
    pipeline='yunet-mf-'+config['precision']+'-npu:'+sha(root/'models.json')
    if not evidence['all_passed'] or gallery['pipeline_id']!=pipeline or evidence['pipeline_id']!=pipeline:
        raise RuntimeError('This gallery is not validated for the deployed models')
    if model_backend is not None:
        # Startup verifies every SHA-256. An immutable release version check
        # avoids rereading all model weights for every incoming camera frame.
        model_backend.validate_release()
    else:
        for role,record in config['models'].items():
            for key in ('json','raw'):
                if sha(root/record[key])!=record[key+'_sha256']:
                    raise RuntimeError('Model checksum mismatch: '+role)
    image=cv2.imread(str(photo),cv2.IMREAD_COLOR|cv2.IMREAD_IGNORE_ORIENTATION)
    if image is None or image.shape[0]*image.shape[1]>16000000:
        raise ValueError('Cannot decode photo, or image exceeds 16 megapixels')
    if pl_executable is not None:
        height,width=image.shape[:2];pitch=((width*4+7)//8)*8
        allocation=((pitch*height+63)//64)*64+640*640*4+(128 if model_backend is not None else 0)
        if width>8192 or height>8192 or allocation>64*1024*1024:
            raise ValueError('图片尺寸超出当前PL预处理范围，请缩小图片')
    shared_owner=getattr(model_backend,'exclusive_owner',False)
    lock=None if shared_owner else (root/'npu.lock').open('w')
    if lock is not None:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for arguments in (['pgrep','-x','wcis_face_npu'],['pgrep','-f','^./sdicamera']):
        if subprocess.run(arguments,stdout=subprocess.DEVNULL).returncode==0:
            raise RuntimeError('Another program owns the NPU')
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    review=root.parents[1]/'hardware-review-required.json'
    if review.exists() and json.loads(review.read_text()).get('boot_id')==boot:
        raise RuntimeError('Review the previous device error before another inference')
    out.mkdir(parents=True,exist_ok=False)
    start=time.monotonic();preprocessor=None;host={}
    def elapsed(since):return (time.monotonic()-since)*1000
    try:
        phase=time.monotonic()
        if pl_executable is not None:
            from pl_preprocess import PLPreprocessor
            preprocessor=(model_backend.preprocessor(out/'preprocessing',photo=True) if shared_owner else
                          PLPreprocessor(pl_executable,out/'preprocessing',review,memory_transport=model_backend is not None))
            padded,sx,sy=preprocessor.prepare(image)
        else:
            padded,sx,sy=prepare(image)
        host['prepare_ms']=elapsed(phase)
        return infer_prepared(padded,sx,sy,root=root,out=out,config=config,evidence=evidence,
            gallery=gallery,preprocessor=preprocessor,model_backend=model_backend,image=image,
            return_embedding=return_embedding,identity={'photo_sha256':sha(photo),'boot_id':boot},
            host=host,start=start,request_started=request_started,require_single_face=require_single_face,
            save_aligned=save_aligned)
    except BaseException as error:
        save(review,{'boot_id':boot,'error_type':type(error).__name__,'message':str(error),'automatic_retry':False})
        raise
    finally:
        try:
            if preprocessor is not None:preprocessor.close()
        finally:
            if lock is not None:lock.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--photo',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--pl-executable',type=Path)
    args=parser.parse_args()
    print(json.dumps(recognize(args.root,args.photo,args.out,pl_executable=args.pl_executable),ensure_ascii=False),flush=True)
