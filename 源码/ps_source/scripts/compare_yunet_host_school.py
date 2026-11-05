"""Check parser/optimizer/quantizer numerics on the school CPU, no board access."""
import ctypes,json,os,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
assert str(root).replace('\\','/').lower().startswith('d:/yzd/tmp/wcis-face-')
ctypes.windll.kernel32.SetErrorMode(0x8003)
env=os.environ.copy();env['PATH']=str(root/'icraft-portable/bin')+';D:/yzd/tools/msvc1450;'+env['PATH']
env['OMP_NUM_THREADS']='2'
env['TEMP']=env['TMP']=str(root/'scratch')
report={}
for stage,suffix in [('parse','parsed'),('optimize','optimized'),('quantize','quantized')]:
 source=root/'face-models-logits/yunet'/stage/('yunet_'+suffix+'.json')
 out=root/'host-yunet-compare'/stage;out.mkdir(parents=True,exist_ok=True)
 cmd=[str(root/'icraft-portable/bin/icraft-run.exe'),'--json',str(source),'--raw',str(source.with_suffix('.raw')),'--input',str(root/'input-SFB.bin'),'--backends','Host','--dump_format','SFB','--dump_output','--log_path',str(out)]
 print(stage,'Host run',flush=True)
 with (out/'console.log').open('wb') as log:r=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=60)
 report[stage]={'exit':r.returncode,'args':cmd};print(stage,r.returncode,(out/'console.log').read_text(encoding='utf-8',errors='replace')[-1000:],flush=True)
(root/'host-yunet-compare/status.json').write_text(json.dumps(report,indent=2))
