"""Compile in a unique temporary board directory; no app run or device writes."""
from ssh_transport import board_connection, ROOT
import tarfile
import json
import shlex

archive = ROOT / 'outputs/ps_app_source.tar.gz'
with tarfile.open(archive, 'w:gz') as tar:
    tar.add(ROOT / 'ps_app', arcname='ps_app')
with board_connection() as client:
    _, out, _ = client.exec_command('mktemp -d /tmp/wcis-build-20261013-XXXXXX')
    remote = out.read().decode().strip()
    if not remote.startswith('/tmp/wcis-build-20261013-') or '/' in remote[len('/tmp/'):]:
        raise RuntimeError('Unexpected temporary build directory')
    (ROOT / 'outputs/ps_build_remote.json').write_text(json.dumps({'directory':remote}), encoding='utf-8')
    sftp = client.open_sftp()
    sftp.put(str(archive), remote + '/source.tar.gz')
    q = shlex.quote(remote)
    cmd = (f'cd {q} && tar -xzf source.tar.gz && '
           'nice -n 10 cmake -S ps_app -B build -DCMAKE_BUILD_TYPE=Release && '
           'nice -n 10 cmake --build build -j1')
    _, out, err = client.exec_command(cmd, timeout=1200)
    out.channel.set_combine_stderr(True)
    with (ROOT / 'outputs/ps_app_build.log').open('w', encoding='utf-8') as log:
        while True:
            chunk = out.channel.recv(4096)
            if not chunk:
                break
            value = chunk.decode(errors='replace')
            log.write(value); log.flush()
            print(value, end='', flush=True)
    code = out.channel.recv_exit_status()
    print('BUILD_EXIT=' + str(code))
    if code == 0:
        dest = ROOT / 'outputs/ps_app'
        dest.mkdir(exist_ok=True)
        sftp.get(remote + '/build/wcis_sdi_reference', str(dest / 'wcis_sdi_reference'))
        # --help exits before opening a device or loading any model.
        _, out, err = client.exec_command(shlex.quote(remote + '/build/wcis_sdi_reference') + ' --help')
        print(out.read().decode(errors='replace') + err.read().decode(errors='replace'))
        print('HELP_EXIT=' + str(out.channel.recv_exit_status()))
    sftp.close()
    raise SystemExit(code)
