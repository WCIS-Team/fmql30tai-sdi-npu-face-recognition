"""Fetch the pinned, inspected alignment reference into task scratch only."""
import hashlib
import json
from pathlib import Path
import urllib.request

COMMIT='81929474ec02e54e3655f6841bced800009c592d'
SHA='a8b34ddd06716f5ca7e7501415cbd3789ccbce18db9e557b35e537695290d922'


def main():
    out=Path('D:/yzd/tmp/face-pl-20261015/upstream')
    out.mkdir(parents=True,exist_ok=True)
    base='https://raw.githubusercontent.com/deepinsight/insightface/'+COMMIT+'/'
    url=base+'python-package/insightface/utils/face_align.py'
    data=urllib.request.urlopen(url,timeout=30).read()
    if hashlib.sha256(data).hexdigest()!=SHA:
        raise ValueError('Pinned upstream source changed')
    (out/'face_align.py').write_bytes(data)
    (out/'README.md').write_bytes(urllib.request.urlopen(base+'README.md',timeout=30).read())
    (out/'sources.json').write_text(json.dumps(dict(commit=COMMIT,url=url,sha256=SHA),indent=2)+'\n')
    print('Pinned InsightFace alignment source verified:',out)


if __name__=='__main__':main()
