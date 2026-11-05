"""Isolated AArch64 build only. Never connects to or executes on the board."""
from school_connection import school_connection, ROOT
import hashlib
import json
import tarfile
import uuid
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--out-dir', default='outputs/camera-preview')
args = parser.parse_args()
out = (ROOT / args.out_dir).resolve()
if not out.is_relative_to((ROOT/'outputs').resolve()):
    raise SystemExit('Build output must stay in project outputs')
out.mkdir(parents=True, exist_ok=True)
task = '/D:/yzd/tmp/wcis-camera-preview-' + uuid.uuid4().hex[:8]
result = dict(remote_directory=task, built=False, board_accessed=False)
archive = out / 'source.tar.gz'
with tarfile.open(archive, 'w:gz') as tar:
    tar.add(ROOT / 'ps_app', arcname='ps_app')
    tar.add(ROOT / 'lan_stream/include', arcname='lan_stream/include')
    tar.add(ROOT / 'lan_stream/src/capture_wait_test.cpp', arcname='lan_stream/src/capture_wait_test.cpp')
try:
    with school_connection() as client:
        sftp = client.open_sftp()
        sftp.mkdir(task)
        sftp.put(str(archive), task+'/source.tar.gz')
        sftp.put(str(ROOT/'scripts/build_camera_preview_school.sh'), task+'/build.sh')
        _, stdout, _ = client.exec_command('D:/yzd/MSYS2/usr/bin/bash.exe --login '+task.lstrip('/')+'/build.sh', timeout=120)
        stdout.channel.set_combine_stderr(True)
        with (out/'build.log').open('w', encoding='utf-8') as log:
            while True:
                chunk = stdout.channel.recv(8192)
                if not chunk:
                    break
                value = chunk.decode(errors='replace'); log.write(value); log.flush(); print(value, end='', flush=True)
        result['exit_code'] = stdout.channel.recv_exit_status()
        if result['exit_code'] == 0:
            for name in ('wcis_camera_preview', 'wcis_capture_wait_test', 'elf-header.txt', 'elf-dynamic.txt', 'elf-versions.txt'):
                sftp.get(task+'/build/'+name, str(out/name))
            result['built'] = True
            result['sha256'] = hashlib.sha256((out/'wcis_camera_preview').read_bytes()).hexdigest()
        sftp.close()
except Exception as error:
    result['error_type'] = type(error).__name__
(out/'cross-build.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
raise SystemExit(0 if result['built'] else 1)
