from school_connection import school_connection, ROOT
import json
import sys
sys.stdout.reconfigure(errors='replace')

task = json.loads((ROOT / 'outputs/school_cache.json').read_text())['directory']
assert task.startswith('/D:/yzd/tmp/wcis-fpga-20261013-') and '/..' not in task
with school_connection() as client:
    sftp = client.open_sftp()
    sftp.put(str(ROOT / 'scripts/school_inventory.sh'), task + '/school_inventory.sh')
    _, out, _ = client.exec_command('D:/yzd/MSYS2/usr/bin/bash.exe --login ' + task.lstrip('/') + '/school_inventory.sh', timeout=180)
    out.channel.set_combine_stderr(True)
    with (ROOT / 'outputs/school_inventory.log').open('w', encoding='utf-8') as log:
        while True:
            value = out.channel.recv(8192)
            if not value: break
            text = value.decode('utf-8', errors='replace')
            log.write(text); log.flush()
    code = out.channel.recv_exit_status()
    for name in ('directories.txt','python-paths.txt','tools.txt'):
        sftp.get(task + '/inventory/' + name, str(ROOT / ('outputs/school-' + name)))
    sftp.close()
    print('INVENTORY_EXIT=' + str(code))
    print('Inventory log saved locally and data files remain under the server task cache.')
