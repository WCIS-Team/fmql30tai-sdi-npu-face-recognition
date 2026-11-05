"""Bounded file-input ModelBackend verification using existing NPU models.

No identity database changes, website, camera, scheduling policy or CPU inference
fallback. Execute only after the FAC1 firmware deployment gate is satisfied.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from pl_preprocess import PLPreprocessor
from run_photos import Runner,decode,save


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--pl-executable',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();root=args.root.resolve();out=args.out.resolve();out.mkdir()
    config=json.loads((root/'models.json').read_text())
    for record in config['models'].values():
        for key in ['json','raw']:
            if hashlib.sha256((root/record[key]).read_bytes()).hexdigest()!=record[key+'_sha256']:
                raise RuntimeError('Immutable NPU model checksum mismatch')
    lock=(root/'npu.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    marker=root.parents[1]/'hardware-review-required.json'
    if marker.exists() and json.loads(marker.read_text()).get('boot_id')==boot:
        raise RuntimeError('Existing hardware quarantine in current boot')
    prep=PLPreprocessor(args.pl_executable,out/'preprocessing',marker)
    records=json.loads((root/'samples/sources.json').read_text())['files']
    results=[]
    try:
        for record in records:
            filename=record['file'];path=root/'samples'/filename
            if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
                raise RuntimeError('Photo provenance mismatch')
            image=cv2.imread(str(path));stem=Path(filename).stem
            padded,sx,sy=prep.prepare(image)
            # Runner initialization opens the NPU, so it must happen AFTER
            # preprocessing. forward() exits its SDK worker after each model.
            directory=out/stem;directory.mkdir();runner=Runner(root,directory)
            try:
                values,detector=runner.forward('yunet',padded.astype(np.float32),stem)
                faces=decode(values,sx,sy,config.get('detector_activation')=='host_sigmoid')
                if len(faces)!=1:raise RuntimeError('Expected one public test face')
                aligned=prep.align(image,faces[0]);cv2.imwrite(str(directory/'aligned.png'),aligned)
                tensor=(cv2.cvtColor(aligned,cv2.COLOR_BGR2RGB).astype(np.float32)-127.5)/127.5
                values,recognizer=runner.forward('mobilefacenet',tensor,stem)
                embedding=values[0].reshape(-1);embedding/=np.linalg.norm(embedding)
                reference=json.loads((root/'cpu-features'/(filename+'.json')).read_text())
                cpu=np.asarray(reference['embedding'],np.float64);cpu/=np.linalg.norm(cpu)
                cosine=float(np.dot(cpu,embedding))
                result=dict(file=filename,face=faces[0],embedding=embedding.tolist(),cpu_feature_cosine=cosine,
                    passed=bool(cosine>=0.99),detector=detector,recognizer=recognizer)
                results.append(result);save(directory/'result.json',result)
                print(filename,'CPU cosine',cosine,flush=True)
                if not result['passed']:raise RuntimeError('PL+NPU feature regression failed')
            finally:runner.close()
        for filename,wanted in [('no-face.png',0),('two-faces.png',2)]:
            image=cv2.imread(str(root/'samples'/filename));padded,sx,sy=prep.prepare(image)
            directory=out/Path(filename).stem;directory.mkdir();runner=Runner(root,directory)
            try:
                values,_=runner.forward('yunet',padded.astype(np.float32),Path(filename).stem)
                faces=decode(values,sx,sy,config.get('detector_activation')=='host_sigmoid')
                passed=len(faces)==0 if wanted==0 else len(faces)>1
                if not passed:raise RuntimeError('Failure-scene regression failed')
                results.append(dict(file=filename,faces=len(faces),passed=True))
            finally:runner.close()
        save(out/'verification.json',dict(passed=True,boot_id=boot,scope='file input PL geometry + real NPU models; no camera or identity accuracy claim',
            models_unchanged=True,frames=prep.timings,results=results))
    except BaseException as error:
        save(marker,dict(boot_id=boot,source='PL+NPU validation',error_type=type(error).__name__,message=str(error),automatic_retry=False))
        save(out/'failure.json',dict(boot_id=boot,results=results,error=str(error)));raise
    finally:lock.close()


if __name__=='__main__':main()
