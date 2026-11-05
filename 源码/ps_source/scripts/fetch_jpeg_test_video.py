"""Fetch OpenCV's unchanged 1080p test video to the user's local task folder."""
import hashlib, json, urllib.request, subprocess
from pathlib import Path

def main():
    out=Path('D:/yzd/tmp/pl-jpeg-board-20261016/videos')
    out.mkdir(parents=True,exist_ok=True)
    target=out/'1920x1080.avi'
    record=out/'source.json'
    if target.exists():
        if record.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==json.loads(record.read_text())['sha256']:
            print('Using verified local 1080p video:',target);return
        raise FileExistsError('Existing video has no matching source record')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    commit=subprocess.check_output(['git','ls-remote','https://github.com/opencv/opencv_extra.git','refs/heads/4.x'],
                                   text=True,timeout=45).split()[0]
    name='1920x1080.avi'
    url=f'https://raw.githubusercontent.com/opencv/opencv_extra/{commit}/testdata/cv/video/{name}'
    target=out/name
    if not target.exists():
        temp=out/(name+'.part')
        with opener.open(url,timeout=30) as source, temp.open('xb') as dest:
            size=0
            while True:
                block=source.read(1024*1024)
                if not block: break
                size+=len(block)
                if size>64*1024*1024: raise ValueError('Unexpectedly large test asset')
                dest.write(block)
        temp.replace(target)
    rec=dict(path=str(target),url=url,commit=commit,bytes=target.stat().st_size,
        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),modified=False,
        source_page='https://github.com/opencv/opencv_extra/blob/4.x/testdata/cv/video/1920x1080.avi',
        source_repository='https://github.com/opencv/opencv_extra',
        notice='Upstream public test asset; no new license or ownership claim; preserve upstream attribution')
    (out/'source.json').write_text(json.dumps(rec,indent=2))
    print(json.dumps(rec,indent=2))
if __name__=='__main__': main()
