"""Stop only our isolated native compiler; preserve all other board jobs."""
from ssh_transport import board_connection, ROOT
import json
import shlex

remote = json.loads((ROOT / 'outputs/ps_build_remote.json').read_text())['directory']
if not remote.startswith('/tmp/wcis-build-20261013-'):
    raise RuntimeError('Unexpected build path')
with board_connection() as client:
    _, out, _ = client.exec_command('ps -eo pid,args')
    victims = []
    for row in out.read().decode().splitlines():
        parts = row.strip().split(None, 1)
        if len(parts) == 2 and '/cc1plus ' in parts[1] and remote + '/' in parts[1]:
            victims.append(int(parts[0]))
    for pid in victims:
        _, out, _ = client.exec_command('kill -TERM ' + str(pid))
        print('Stopped our native compiler PID ' + str(pid) + ': ' + str(out.channel.recv_exit_status()))
    if not victims:
        print('Our native compiler has already exited.')
