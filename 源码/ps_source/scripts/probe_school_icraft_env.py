"""Bounded compiler-only probes; files stay under the school face task."""
import ctypes
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
assert str(root).replace('\\', '/').lower().startswith('d:/yzd/tmp/wcis-face-')
ctypes.windll.kernel32.SetErrorMode(0x8003)
bin = root / 'icraft-portable/bin'
env = os.environ.copy()
env['PATH'] = str(bin) + ';' + str(root / 'runtime') + ';D:/yzd/tools/msvc1450;' + env['PATH']
env['TEMP'] = env['TMP'] = str(root / 'scratch')
env.pop('ICRAFT_CUSTOM_DIR', None)
with (root / 'archive-full-list.txt').open('wb') as log:
    subprocess.run([str(root / '7zip/7z.exe'), 'l', '-ba', str(root / 'Icraft_Setup_v3.39.0.complete.exe')], stdout=log, stderr=subprocess.STDOUT, timeout=60)
results = []
for name, cwd, custom in [('bin-default', bin, None), ('root-default', root, None), ('bin-custom', bin, bin)]:
    dest = root / 'env-probe' / name
    dest.mkdir(parents=True, exist_ok=True)
    runenv = env.copy()
    if custom: runenv['ICRAFT_CUSTOM_DIR'] = str(custom)
    cmd = [str(bin / 'icraft-optimize.exe'), '--json', str(root / 'parsed-inputs/yunet/yunet.json'), '--raw', str(root / 'parsed-inputs/yunet/yunet.raw'), '--jr_path', str(dest), '--log_path', str(dest / 'logs'), '--target', 'zhuge']
    with (dest / 'console.log').open('wb') as log:
        done = subprocess.run(cmd, cwd=cwd, env=runenv, stdout=log, stderr=subprocess.STDOUT, timeout=60)
    results.append({'name': name, 'exit_code': done.returncode, 'log': (dest / 'console.log').read_text(encoding='utf-8', errors='replace')[-2500:]})
    print(json.dumps(results[-1]), flush=True)
(root / 'env-probe.json').write_text(json.dumps(results, indent=2))
