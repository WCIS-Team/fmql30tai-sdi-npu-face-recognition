"""Run the same public photo before/after the JPEG bitstream, without enrollment."""
import argparse,hashlib,json
from pathlib import Path
from ssh_transport import ROOT,board_connection
TASK=Path('D:/yzd/tmp/pl-jpeg-board-20261016')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=('before','after'),required=True);a=p.parse_args()
    source=ROOT/'photo_reference/data/public/biden.jpg'
    remote_path='/root/wcis-face/candidates/jpeg-20261016/regression.jpg'
    code=r'''
from pathlib import Path
import json,urllib.request,hashlib
photo=Path('/root/wcis-face/candidates/jpeg-20261016/regression.jpg').read_bytes()
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
q=urllib.request.Request('http://192.168.1.113:8091/api/recognize',data=photo,
headers={'Content-Type':'image/jpeg','X-Photo-Name':'JPG1-regression.jpg'})
with opener.open(q,timeout=60) as r:data=json.loads(r.read())
data['input_sha256']=hashlib.sha256(photo).hexdigest()
data['board_boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
print(json.dumps(data))
'''
    with board_connection() as c:
        s=c.open_sftp();s.put(str(source),remote_path)
        _,out,err=c.exec_command("python3 - <<'PY'\n"+code+'\nPY',timeout=65)
        data=out.read();error=err.read()
        if out.channel.recv_exit_status():raise RuntimeError(error.decode())
        report=json.loads(data);assert report['input_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    (TASK/f'face-{a.stage}.json').write_text(json.dumps(report,indent=2))
    result=report['entry']['result']
    summary=dict(board_boot_id=report['board_boot_id'],input_sha256=report['input_sha256'],status=result['status'],face_count=result['face_count'],
                 faces=result['faces'],backend=result['backend'])
    summary['outputs']={role:[x['sha256'] for x in result['timing'][role]['outputs']]
        for role in ('detector','recognizer') if role in result['timing']}
    if a.stage=='after':
        before=json.loads((TASK/'face-before.json').read_text());old=before['entry']['result']
        old_outputs={role:[x['sha256'] for x in old['timing'][role]['outputs']]
            for role in ('detector','recognizer') if role in old['timing']}
        assert before['input_sha256']==report['input_sha256'] and old_outputs==summary['outputs'] and old['faces']==result['faces']
        summary['model_outputs_equal_before']=True
    (TASK/f'face-{a.stage}-summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
