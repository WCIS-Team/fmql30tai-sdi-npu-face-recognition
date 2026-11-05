"""FP16 candidates from validated optimized IR, using measured 4x2 geometry."""
from pathlib import Path
import ctypes,json,os,subprocess
root=Path(__file__).resolve().parent
assert str(root).replace('\\','/').lower().startswith('d:/yzd/tmp/wcis-face-')
ctypes.windll.kernel32.SetErrorMode(0x8003)
env=os.environ.copy();env['PATH']=str(root/'icraft-portable/bin')+';D:/yzd/tools/msvc1450;'+env['PATH']
env['TEMP']=env['TMP']=str(root/'scratch');env['XDG_CACHE_HOME']=str(root/'cache')
sources={'yunet':'face-models-logits/yunet/optimize/yunet_optimized.json','mobilefacenet':'face-models-relu/mobilefacenet/optimize/mobilefacenet_optimized.json'}
report={'precision':'fp16','rows':4,'cols':2,'cores':1,'models':{}}
for role,name in sources.items():
 source=root/name
 for stage in ['quantize','adapt','generate']:
  dest=root/'face-models-fp16'/role/stage;dest.mkdir(parents=True,exist_ok=True)
  cmd=[str(root/'icraft-portable/bin'/('icraft-'+stage+'.exe')),'--json',str(source),'--raw',str(source.with_suffix('.raw')),'--jr_path',str(dest),'--log_path',str(dest/'logs')]
  if stage!='generate':cmd+=['--target','zhuge']
  if stage=='quantize':cmd+=['--qdtype','fp16','--no_transinput','true','--no_imagemake','true']
  if stage=='generate':cmd+=['--cores','1','--rows','4','--cols','2']
  print(role,stage,'FP16 started',flush=True)
  with (dest/'console.log').open('wb') as log:r=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
  report['models'][role+'-'+stage]={'exit':r.returncode,'args':cmd}
  (root/'face-fp16-status.json').write_text(json.dumps(report,indent=2));print(role,stage,'exit',r.returncode,flush=True)
  outputs=list(dest.glob('*.json'))
  if r.returncode or len(outputs)!=1:
   print((dest/'console.log').read_text(encoding='utf-8',errors='replace')[-1400:],flush=True);raise SystemExit(1)
  source=outputs[0]
report['generated']=True;(root/'face-fp16-status.json').write_text(json.dumps(report,indent=2))
