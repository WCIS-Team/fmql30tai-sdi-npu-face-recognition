"""Load/help check only. Never open a device, load a model or replace firmware."""
from ssh_transport import board_connection, ROOT
from pathlib import Path
import json
import hashlib
import shlex
import secrets

binary = ROOT / 'outputs/ps_app/wcis_sdi_reference'
local_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
with board_connection() as client:
    _, out, _ = client.exec_command('mktemp -d /tmp/wcis-loader-20261013-XXXXXX')
    remote = out.read().decode().strip()
    assert remote.startswith('/tmp/wcis-loader-20261013-') and '/' not in remote[len('/tmp/'):]
    sftp = client.open_sftp()
    path = remote + '/wcis_sdi_reference'
    sftp.put(str(binary), path)
    sftp.chmod(path, 0o700)
    results = {'binary_sha256':local_sha, 'remote_test_directory':remote,
               'mode':'loader and help only; no device open, inference or firmware replacement'}
    for name, cmd in {
        'board_abi':"dpkg-query -W -f='${Package} ${Version}\\n' libc6 libstdc++6 icraft customop; uname -m",
        'sha256':'sha256sum ' + shlex.quote(path),
        'dependencies':'ldd ' + shlex.quote(path),
        'help':shlex.quote(path) + ' --help',
    }.items():
        _, out, err = client.exec_command(cmd, timeout=30)
        text = out.read().decode(errors='replace') + err.read().decode(errors='replace')
        code = out.channel.recv_exit_status()
        results[name] = {'output':text,'exit_code':code}
        print(name + ':\n' + text)
    results['help_passed'] = results['help']['exit_code'] == 0
    results['dependencies_resolved'] = 'not found' not in results['dependencies']['output'] and results['dependencies']['exit_code'] == 0
    results['transfer_sha_matches'] = local_sha in results['sha256']['output']
    (ROOT / 'outputs/ps_app/board_loader_check.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    sftp.close()
    if not all(results[k] for k in ('help_passed','dependencies_resolved','transfer_sha_matches')):
        raise SystemExit('Board loader check failed; see saved report. No inference run attempted.')
    print('PASS board loader/dependency/help check; camera/NPU pipeline not exercised.')
