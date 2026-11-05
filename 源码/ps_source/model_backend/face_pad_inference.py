"""Offline PAD model probe with OpenCV reference inputs and isolated NPU runner.

This prototype does not submit commands to the new PL crop RTL. It validates
model availability before that RTL is integrated into a full board bitstream.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np
from .face_pad import prepare_reference, combine_logits, MODELS, UPSTREAM_COMMIT


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def predict(bundle, image_path, bbox_xywh, frame_id, out,
            state_path=Path('/root/wcis-face/video-stream-current.json')):
    """Return model evidence for an explicit original-frame bbox.

    The caller supplies a detection from the same frame. This helper does not
    detect a face, establish identity, fuse permissions, or grant access.
    Hardware errors propagate, with no default live result and no auto retry.
    The release's existing lock covers the entire double inference.
    """
    import cv2
    if isinstance(frame_id,bool) or not isinstance(frame_id,int) or not 0 <= frame_id < 2**32:
        raise ValueError('frame_id must fit uint32')
    bundle, image_path, out = Path(bundle).resolve(), Path(image_path), Path(out)
    manifest=json.loads((bundle/'pad-models.json').read_text())
    if manifest.get('upstream_commit')!=UPSTREAM_COMMIT or manifest.get('generated') is not True:
        raise ValueError('Expected pinned generated PAD bundle')
    for rel,digest in manifest['files_sha256'].items():
        path=(bundle/rel).resolve()
        if bundle not in path.parents or sha(path)!=digest:
            raise ValueError('Bundle checksum/path mismatch: '+rel)
    required={'wcis_face_pad'}
    for role,_,_ in MODELS:
        required.update(manifest['models'][role][key] for key in ('json','raw'))
    if not required.issubset(manifest['files_sha256']):
        raise ValueError('Incomplete bundle checksum coverage')
    # Decode precisely the bytes whose identity is returned in the result.
    raw=image_path.read_bytes()
    image=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR|cv2.IMREAD_IGNORE_ORIENTATION)
    if image is None or image.shape[0]*image.shape[1]>16000000:
        raise ValueError('Unreadable image or more than 16 megapixels')
    tensors=prepare_reference(image,bbox_xywh)
    cfg=json.loads(Path(state_path).read_text())
    release=Path(cfg['release'])
    marker=Path(state_path).parent/'hardware-review-required.json'
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if cfg.get('verified_boot_id')!=boot:
        raise RuntimeError('Current boot has not been verified')
    if marker.exists() and json.loads(marker.read_text()).get('boot_id')==boot:
        raise RuntimeError('Hardware review required before inference')
    out.mkdir(parents=True,exist_ok=False)
    queries=[]
    for role,_,_ in MODELS:
        file=out/(role+'.f32');tensors[role].astype('<f4').tofile(file)
        queries.append(dict(role=role,input_f32=str(file.resolve()),output_directory=str((out/role).resolve())))
    with (release/'npu.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        started=time.monotonic()
        with (out/'runner.stderr.log').open('w') as errors:
            # No forced timeout/kill during DMA; SDK output waits have a deadline.
            process=subprocess.run([str(bundle/'wcis_face_pad'),'--run',str(bundle/'pad-models.json')],
                input=''.join(json.dumps(q)+'\n' for q in queries),text=True,stdout=subprocess.PIPE,stderr=errors)
        (out/'runner.stdout.log').write_text(process.stdout)
        records=[json.loads(line[len('WCIS_RESULT '):]) for line in process.stdout.splitlines() if line.startswith('WCIS_RESULT ')]
        forwarded=[r for r in records if r.get('status')=='forwarded']
        if process.returncode or len(forwarded)!=2:
            marker.write_text(json.dumps(dict(boot_id=boot,reason='PAD NPU error',automatic_retry=False)))
            raise RuntimeError('PAD inference failed; review saved SDK logs')
        logits={}
        for query, record in zip(queries,forwarded):
            if record['role']!=query['role'] or record['npu_bound_ops']<=0:
                raise RuntimeError('Unexpected NPU model result')
            path=Path(record['outputs'][0]['file']).resolve()
            if path.parent!=Path(query['output_directory']):raise RuntimeError('Unexpected output path')
            data=np.fromfile(path,dtype='<f4')
            if data.size!=3 or not np.all(np.isfinite(data)):raise RuntimeError('Invalid logits')
            logits[query['role']]=data.tolist()
        evidence=dict(schema_version=1,frame_id=frame_id,source_sha256=hashlib.sha256(raw).hexdigest(),
            bbox_xywh=list(bbox_xywh),boot_id=boot,upstream_commit=UPSTREAM_COMMIT,
            preprocessing='OpenCV reference crop on host; new PL crop not deployed',
            backend='zg330_npu_and_host',models=logits,model_result=combine_logits(logits),
            elapsed_ms=(time.monotonic()-started)*1000,security_calibrated=False)
        (out/'result.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        return evidence
