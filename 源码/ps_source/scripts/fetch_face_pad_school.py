"""Fetch a checksum-pinned MiniFASNet reference into an isolated school task.

Upload this script and face_pad_reference.json into the same private directory.
Dependencies: read-only school Python with torch/onnx/onnxruntime; cv2 and PIL
may be installed into task/python, never into a shared environment.
"""
import hashlib
import json
import os
from pathlib import Path
import urllib.request


def main():
    root=Path(__file__).resolve().parent
    if not root.as_posix().lower().startswith('d:/yzd/tmp/wcis-face-pad-'):
        raise RuntimeError('Use an isolated school task directory')
    for name in ('scratch','cache','reference','models'):(root/name).mkdir(exist_ok=True)
    for key in ('TMP','TEMP','TMPDIR'):os.environ[key]=str(root/'scratch')
    for key in ('XDG_CACHE_HOME','TORCH_HOME','HF_HOME','PIP_CACHE_DIR'):os.environ[key]=str(root/'cache')
    manifest=json.loads((root/'face_pad_reference.json').read_text())
    commit=manifest['commit']
    if commit!='b6d5f04ad78778917853b25c778acef6d5626d15':raise ValueError('Unexpected revision')
    for name,digest in manifest['files'].items():
        target=(root/'reference'/name).resolve()
        if (root/'reference').resolve() not in target.parents:raise ValueError('Invalid reference path')
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==digest:continue
        url='https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing/'+commit+'/'+name
        request=urllib.request.Request(url,headers={'User-Agent':'wcis-pad-reference'})
        with urllib.request.urlopen(request,timeout=60) as response:
            data=response.read(32*1024*1024+1)
        if len(data)>32*1024*1024 or hashlib.sha256(data).hexdigest()!=digest:
            raise RuntimeError('Download checksum mismatch: '+name)
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        print('VERIFIED',name,flush=True)
    (root/'reference-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__=='__main__':main()
