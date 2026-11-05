"""Disable optional code-generation optimizations for an isolated candidate."""
import ctypes
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
assert str(root).replace('\\', '/').lower().startswith('d:/yzd/tmp/wcis-face-')
ctypes.windll.kernel32.SetErrorMode(0x8003)
dest = root / 'face-models/mobilefacenet/generate-lowopt'
dest.mkdir(parents=True, exist_ok=True)
source = root / 'face-models/mobilefacenet/adapt/mobilefacenet_adapted.json'
env = os.environ.copy()
env['PATH'] = str(root / 'icraft-portable/bin') + ';D:/yzd/tools/msvc1450;' + env['PATH']
env['TEMP'] = env['TMP'] = str(root / 'scratch')
env['OMP_NUM_THREADS'] = '1'
cmd = [str(root / 'icraft-portable/bin/icraft-generate.exe'), '--json', str(source), '--raw', str(source.with_suffix('.raw')), '--jr_path', str(dest), '--log_path', str(dest / 'logs'), '--cores', '1', '--rows', '4', '--cols', '4', '--xlmopt', '0', '--klmopt', '0', '--icropt', '0']
print('mobile generation, optional optimizations disabled', flush=True)
with (dest / 'console.log').open('wb') as log:
    result = subprocess.run(cmd, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
status = {'args':cmd, 'exit_code':result.returncode, 'outputs':[p.name for p in dest.glob('*.json')]}
(dest / 'status.json').write_text(json.dumps(status, indent=2))
print(json.dumps(status), flush=True)
print((dest / 'console.log').read_text(encoding='utf-8', errors='replace')[-1800:], flush=True)
