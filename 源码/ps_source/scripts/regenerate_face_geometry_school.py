"""Match code generation to the board's measured four-by-two MPE geometry."""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import subprocess

root=Path(__file__).resolve().parent
assert str(root).replace('\\','/').lower().startswith('d:/yzd/tmp/wcis-face-')
ctypes.windll.kernel32.SetErrorMode(0x8003)
env=os.environ.copy();env['PATH']=str(root/'icraft-portable/bin')+';D:/yzd/tools/msvc1450;'+env['PATH']
for key in ['TEMP','TMP','TMPDIR']:env[key]=str(root/'scratch')
env['XDG_CACHE_HOME']=str(root/'cache')
sources={'yunet':'face-models-logits/yunet/adapt/yunet_adapted.json','mobilefacenet':'face-models-relu/mobilefacenet/adapt/mobilefacenet_adapted.json'}
report={'compiler_version':'3.39.0','cores':1,'rows':4,'cols':2,'board_measurement':'ZG330Device::getRowsCols returned 4,2','models':{}}
for role,name in sources.items():
 source=root/name;dest=root/'face-models-4x2'/role/'generate';dest.mkdir(parents=True,exist_ok=True)
 cmd=[str(root/'icraft-portable/bin/icraft-generate.exe'),'--json',str(source),'--raw',str(source.with_suffix('.raw')),'--jr_path',str(dest),'--log_path',str(dest/'logs'),'--cores','1','--rows','4','--cols','2']
 print(role,'4x2 generation started',flush=True)
 with (dest/'console.log').open('wb') as log:
  done=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
 report['models'][role]={'exit':done.returncode,'args':cmd}
 (root/'face-4x2-status.json').write_text(json.dumps(report,indent=2))
 print(role,'exit',done.returncode,flush=True)
 if done.returncode:raise SystemExit(1)
report['generated']=True
(root/'face-4x2-status.json').write_text(json.dumps(report,indent=2))
