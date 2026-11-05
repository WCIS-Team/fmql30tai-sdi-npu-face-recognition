"""After authentication, create/upload only inside the user's server cache."""
from school_connection import school_connection, ROOT
from pathlib import PurePosixPath
import secrets
import json
import tarfile
import stat
import sys
sys.stdout.reconfigure(errors='replace')

CACHE = '/D:/yzd/tmp'
TASK = CACHE + '/wcis-fpga-20261013-' + secrets.token_hex(4)
archive = ROOT / 'outputs/ps_app_source.tar.gz'
with tarfile.open(archive, 'w:gz') as tar:
    # Credentials and SSH archive are intentionally excluded.
    tar.add(ROOT / 'ps_app', arcname='ps_app')

def guarded(path):
    normalized = path.replace('\\', '/').lstrip('/').casefold().rstrip('/')
    if not (normalized == 'd:/yzd/tmp' or normalized.startswith('d:/yzd/tmp/')):
        raise RuntimeError('Refusing write outside D:/yzd/tmp: ' + path)
    return path

with school_connection() as client:
    sftp = client.open_sftp()
    try:
        sftp.stat(CACHE)
    except FileNotFoundError:
        sftp.mkdir(guarded(CACHE))
    guarded(sftp.normalize(CACHE))
    sftp.mkdir(guarded(TASK))
    guarded(sftp.normalize(TASK))
    sftp.put(str(ROOT / 'scripts/school_probe.sh'), guarded(TASK + '/school_probe.sh'))
    sftp.put(str(archive), guarded(TASK + '/ps_app_source.tar.gz'))
    (ROOT / 'outputs/school_cache.json').write_text(json.dumps({'directory':TASK}, indent=2), encoding='utf-8')
    # A single script invocation works under the Windows SSH default shell.
    cmd = 'D:/yzd/MSYS2/usr/bin/bash.exe --login ' + TASK.lstrip('/') + '/school_probe.sh'
    _, out, err = client.exec_command(cmd, timeout=45)
    out.channel.set_combine_stderr(True)
    value = out.read().decode(errors='replace')
    code = out.channel.recv_exit_status()
    (ROOT / 'outputs/school_probe.txt').write_text(value, encoding='utf-8')
    print(value)
    print('PROBE_EXIT=' + str(code))
    sftp.close()
