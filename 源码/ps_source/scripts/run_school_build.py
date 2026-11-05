from school_connection import school_connection, ROOT
import json
import sys
import tarfile
sys.stdout.reconfigure(errors='replace')

task = json.loads((ROOT / 'outputs/school_cache.json').read_text())['directory']
assert task.startswith('/D:/yzd/tmp/wcis-fpga-20261013-') and '/..' not in task
archive = ROOT / 'outputs/ps_app_source.tar.gz'
with tarfile.open(archive, 'w:gz') as tar:
    tar.add(ROOT / 'ps_app', arcname='ps_app')
with school_connection() as client:
    sftp = client.open_sftp()
    sftp.put(str(ROOT / 'scripts/school_build.sh'), task + '/school_build.sh')
    sftp.put(str(archive), task + '/ps_app_source.tar.gz')
    _, out, err = client.exec_command('D:/yzd/MSYS2/usr/bin/bash.exe --login ' + task.lstrip('/') + '/school_build.sh', timeout=1800)
    out.channel.set_combine_stderr(True)
    with (ROOT / 'outputs/school_build.log').open('w', encoding='utf-8') as log:
        while True:
            value = out.channel.recv(8192)
            if not value: break
            text = value.decode('utf-8', errors='replace')
            log.write(text); log.flush(); print(text, end='', flush=True)
    code = out.channel.recv_exit_status()
    print('SERVER_BUILD_EXIT=' + str(code))
    if code == 0:
        dest = ROOT / 'outputs/ps_app'
        dest.mkdir(exist_ok=True)
        sftp.get(task + '/build/wcis_sdi_reference', str(dest / 'wcis_sdi_reference'))
        for filename in ('elf-header.txt','elf-dynamic.txt','elf-versions.txt','binary.sha256'):
            sftp.get(task + '/logs/' + filename, str(dest / filename))
    sftp.close()
    raise SystemExit(code)
