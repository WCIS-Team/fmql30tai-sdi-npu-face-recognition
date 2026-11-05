"""Retrieve generated school models and stage a checksummed board release."""
import hashlib
import json
from pathlib import Path
import sys
from school_connection import school_connection, ROOT
from ssh_transport import board_connection

sys.stdout.reconfigure(encoding='utf-8',errors='replace')
task='/D:/yzd/tmp/wcis-face-32b2a267'
out=ROOT/'outputs/photo-board-20261014'
staging=out/'board-staging.json'
staging.write_text(json.dumps({'status':'staging','run_allowed':False}),encoding='utf-8')
models=out/'models'; models.mkdir(exist_ok=True)
roles={role:task+'/face-models-fp16/'+role+'/generate' for role in ['yunet','mobilefacenet']}
roles['yunet']=task+'/face-models-dense/yunet/generate'
roles['mobilefacenet']=task+'/face-models-conv-slope/mobilefacenet/generate'
config={'schema_version':1,'generated':True,'compiler_version':'3.39.0','precision':'fp16','output_format':'SFB','cores':1,'rows':4,'cols':2,'models':{},
        'detector_activation':'host_sigmoid',
        'detector_dense_heads':json.loads((models/'dense-heads-parity.json').read_text()),
        'yunet_logit_export':json.loads((models/'yunet-logits-parity.json').read_text()),
        'prelu_rewrite':json.loads((models/'prelu-conv-slope-parity.json').read_text())}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
with school_connection() as client:
    s=client.open_sftp()
    for role, folder in roles.items():
        files=[a.filename for a in s.listdir_attr(folder) if a.filename.endswith('.json')]
        assert len(files)==1, files
        jp=models/files[0]; rp=jp.with_suffix('.raw')
        s.get(folder+'/'+jp.name,str(jp));s.get(folder+'/'+rp.name,str(rp))
        j=json.loads(jp.read_text()); assert j['icraft_version']=='v3.39.0' and j['ai_target']=='@zhuget(330)'
        hard=[op for op in j['ops'] if op['_type_key']=='icraft::xir::HardOp'];assert hard
        inputs=[op for op in j['ops'] if op['_type_key']=='icraft::xir::Input'][0]['outputs']
        outputs=[op for op in j['ops'] if op['_type_key']=='icraft::xir::Output'][0]['inputs']
        config['models'][role]={'json':'models/'+jp.name,'raw':'models/'+rp.name,'json_sha256':sha(jp),'raw_sha256':sha(rp),
                               'hard_ops':len(hard),'inputs':[v['dtype'] for v in inputs],'outputs':[v['dtype'] for v in outputs]}
manifest=out/'models.json';manifest.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
release='/root/wcis-face/releases/20261014-'+hashlib.sha256(manifest.read_bytes()+(out/'wcis_face_npu').read_bytes()+(ROOT/'npu_photo/run_photos.py').read_bytes()).hexdigest()[:12]
uploads=[(manifest,'models.json'),(out/'wcis_face_npu','wcis_face_npu'),(ROOT/'npu_photo/run_photos.py','run_photos.py'),
         (ROOT/'photo_reference/web/index.html','index.html')]
uploads += [(models/Path(v[k]).name,v[k]) for v in config['models'].values() for k in ['json','raw']]
samples=ROOT/'photo_reference/data/public'
records=json.loads((samples/'sources.json').read_text(encoding='utf-8'))['files']
uploads += [(samples/n,'samples/'+n) for n in ['sources.json','no-face.png','two-faces.png']+[r['file'] for r in records]]
uploads += [(ROOT/'outputs/photo-reference/features'/(r['file']+'.json'),'cpu-features/'+r['file']+'.json') for r in records]
with board_connection() as client:
    s=client.open_sftp()
    def mkdir(p):
        try:s.stat(p)
        except FileNotFoundError:
            mkdir(p.rsplit('/',1)[0]);s.mkdir(p)
    mkdir(release)
    checks=[]
    for local,name in uploads:
        dest=release+'/'+name;mkdir(dest.rsplit('/',1)[0]);s.put(str(local),dest)
        with s.open(dest,'rb') as f: actual=hashlib.sha256(f.read()).hexdigest()
        assert actual==sha(local)
        checks.append({'file':name,'sha256':actual})
    s.chmod(release+'/wcis_face_npu',0o755)
    results={}
    for name,cmd in [('describe',release+'/wcis_face_npu --describe '+release+'/models.json'),
                     ('files','python3 '+release+'/run_photos.py --out '+release+'/validation')]:
        _,stdout,stderr=client.exec_command('timeout 30s '+cmd,timeout=45)
        value=stdout.read().decode(errors='replace');error=stderr.read().decode(errors='replace');code=stdout.channel.recv_exit_status()
        results[name]={'stdout':value,'stderr':error,'exit':code};print(name,json.dumps(results[name]),flush=True)
        assert code==0,results[name]
    report={'release':release,'checks':checks,'results':results,'device_opened':False}
    (out/'board-staged-release.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
staging.unlink()
print(release,flush=True)
