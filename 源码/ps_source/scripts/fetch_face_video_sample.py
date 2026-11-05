"""Download Intel's public inference sample into the user's local D: drive."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path('D:/yzd/tmp/face-video-input/videos'))
    args=parser.parse_args();args.directory.mkdir(parents=True,exist_ok=True)
    name='head-pose-face-detection-female.mp4'
    target=args.directory/name;record=args.directory/'source.json'
    if target.exists():
        if record.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==json.loads(record.read_text(encoding='utf-8'))['sha256']:
            print('Using verified local video: '+str(target));return
        raise FileExistsError('Existing video is not matched by source.json; choose another directory')
    urls=['https://raw.githubusercontent.com/intel-iot-devkit/sample-videos/master/'+name,
          'https://storage.openvinotoolkit.org/test_data/videos/'+name]
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    errors=[]
    for url in urls:
        temp=None
        try:
            with tempfile.NamedTemporaryFile(prefix='video-',suffix='.part',dir=args.directory,delete=False) as out:
                temp=Path(out.name);size=0;digest=hashlib.sha256()
                with opener.open(url,timeout=30) as response:
                    while True:
                        block=response.read(1024*1024)
                        if not block:break
                        size+=len(block)
                        if size>64*1024*1024:raise ValueError('Sample exceeds 64 MiB download limit')
                        digest.update(block);out.write(block)
            temp.replace(target)
            metadata=dict(file=name,path=str(target.resolve()),url=url,repository='https://github.com/intel-iot-devkit/sample-videos',
                license='CC-BY-4.0',license_url='https://github.com/intel-iot-devkit/sample-videos/blob/master/LICENSE',
                attribution='Intel Corporation, intel-iot-devkit/sample-videos',modified=False,
                sha256=digest.hexdigest(),bytes=size,fetched_utc=datetime.now(timezone.utc).isoformat())
            record.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(metadata,ensure_ascii=False),flush=True)
            break
        except Exception as error:
            if temp is not None and temp.exists():temp.unlink()
            errors.append(type(error).__name__)
    else:raise RuntimeError('Official sample download failed: '+', '.join(errors))
    try:
        with opener.open('https://raw.githubusercontent.com/intel-iot-devkit/sample-videos/master/LICENSE',timeout=20) as response:
            license_text=response.read(100000)
        (args.directory/'Intel-sample-videos-LICENSE.txt').write_bytes(license_text)
    except OSError:
        print('License URL preserved in source.json; text download unavailable',flush=True)


if __name__=='__main__':
    main()
