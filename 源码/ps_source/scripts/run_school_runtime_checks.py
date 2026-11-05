from school_connection import school_connection, ROOT
import json
import sys
sys.stdout.reconfigure(errors='replace')

task = json.loads((ROOT / 'outputs/school_cache.json').read_text())['directory']
assert task.startswith('/D:/yzd/tmp/wcis-fpga-20261013-')
with school_connection() as client:
    sftp = client.open_sftp()
    for name in ('python_runtime_probe.py','school_runtime_checks.sh'):
        sftp.put(str(ROOT / 'scripts' / name), task + '/' + name)
    _, out, _ = client.exec_command('D:/yzd/MSYS2/usr/bin/bash.exe --login ' + task.lstrip('/') + '/school_runtime_checks.sh', timeout=240)
    out.channel.set_combine_stderr(True)
    with (ROOT / 'outputs/school_runtime_checks.log').open('w', encoding='utf-8') as log:
        while True:
            chunk = out.channel.recv(8192)
            if not chunk: break
            value = chunk.decode('utf-8', errors='replace')
            log.write(value); log.flush()
    for entry in sftp.listdir(task + '/inventory'):
        if entry.endswith('-runtime.json'):
            sftp.get(task + '/inventory/' + entry, str(ROOT / 'outputs' / entry))
    print('RUNTIME_CHECKS_EXIT=' + str(out.channel.recv_exit_status()))
    sftp.close()
