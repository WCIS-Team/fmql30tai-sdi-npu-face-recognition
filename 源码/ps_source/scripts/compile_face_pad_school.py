"""Isolated school iCraft build for the two pinned MiniFASNet models."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--variant',choices=('original','conv-slope'),default='original')
    parser.add_argument('--icraft-bin',type=Path,default=Path('D:/yzd/tmp/wcis-face-32b2a267/icraft-portable/bin'))
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    if not root.as_posix().lower().startswith('d:/yzd/tmp/wcis-face-pad-'):
        raise RuntimeError('Run inside the isolated school task')
    # Read-only reuse; do not stage DLLs into this older task or shared SDK.
    binary=args.icraft_bin.resolve()
    if not all((binary/('icraft-'+s+'.exe')).is_file() for s in ('parse','optimize','quantize','adapt','generate')):
        raise RuntimeError('Native school iCraft stage executables are unavailable')
    env=os.environ.copy()
    env['PATH']=str(binary)+';D:/yzd/tools/msvc1450;'+env['PATH']
    for key in ('TMP','TEMP','TMPDIR'):env[key]=str(root/'scratch')
    env['XDG_CACHE_HOME']=str(root/'cache')
    empty=root/'no-custom-ops';empty.mkdir(exist_ok=True)
    env['ICRAFT_CUSTOM_DIR']=str(empty)
    ctypes.windll.kernel32.SetErrorMode(0x8003)
    report={'variant':args.variant,'rows':4,'cols':2,'precision':'fp16','stages':{},'generated':False,'board_accessed':False}
    for model in ('MiniFASNetV2','MiniFASNetV1SE'):
        source=root/'models'/(model+('' if args.variant=='original' else '-conv-slope')+'.onnx')
        for stage in ('parse','optimize','quantize','adapt','generate'):
            destination=root/('compiled-'+args.variant)/model/stage
            destination.mkdir(parents=True,exist_ok=True)
            command=[str(binary/('icraft-'+stage+'.exe')),'--jr_path',str(destination),'--log_path',str(destination/'logs')]
            if stage=='parse':
                command+=['--net_name',model,'--network',str(source),'--framework','onnx','--target','zhuge',
                          '--inputs','1,80,80,3','--inputs_dtype','FP32','--inputs_layout','NHWC',
                          '--pre_method','nop','--pre_scale','1,1,1','--pre_mean','0,0,0','--channel_swap','0,1,2']
            else:
                command+=['--json',str(source),'--raw',str(source.with_suffix('.raw'))]
                if stage!='generate':command+=['--target','zhuge']
                if stage=='quantize':command+=['--qdtype','fp16','--no_transinput','true','--no_imagemake','true']
                if stage=='generate':command+=['--cores','1','--rows','4','--cols','2']
            print('START',model,stage,flush=True)
            with (destination/'console.log').open('wb') as f:
                p=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,cwd=root,env=env,timeout=300,creationflags=subprocess.CREATE_NO_WINDOW)
            item={'exit_code':p.returncode,'command':command}
            report['stages'][model+'-'+stage]=item
            files=list(destination.glob('*.json'))
            (root/('compile-'+args.variant+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
            if p.returncode or len(files)!=1:
                print('FAILED',model,stage,p.returncode,flush=True)
                print((destination/'console.log').read_text(encoding='utf-8',errors='replace')[-5000:],flush=True)
                return 1
            source=files[0]
            item.update(json=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest())
            print('PASS',model,stage,flush=True)
    report['generated']=True
    (root/('compile-'+args.variant+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0


if __name__=='__main__':raise SystemExit(main())
