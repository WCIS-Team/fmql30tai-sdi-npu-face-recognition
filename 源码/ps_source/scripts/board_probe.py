"""Read-only SSH probe using one documented credential, never echoing it."""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tools/python'))
import paramiko

DOC = Path(r'C:\Users\anxianji\AppData\Local\Temp\wcis-device-review-2e2a2014089c484a86dd1caa56de008e\md\技术文档\板卡镜像实测取证.md')
text = DOC.read_text(encoding='utf-8')
match = re.search(r'用户名\s*`root`[^\n]*口令\s*`([^`]+)`', text)
if not match:
    raise SystemExit('Documented credential not found; no authentication attempted.')
client = paramiko.SSHClient()
client.load_host_keys(str(ROOT / 'outputs/board_known_hosts'))
client.set_missing_host_key_policy(paramiko.RejectPolicy())
try:
    client.connect('192.168.1.113', username='root', password=match.group(1),
                   look_for_keys=False, allow_agent=False, timeout=8, auth_timeout=8)
    if '--sdk' in sys.argv:
        sftp = client.open_sftp()
        dest = ROOT / '.tools/board-sdk'
        dest.mkdir(parents=True, exist_ok=True)
        for filename in ('Icraft_3.39.0_onchip.deb', 'CustomOp_3.39.0_onchip.deb', 'IcraftMdzThirdParty.deb'):
            sftp.get('/root/pkg39/' + filename, str(dest / filename))
            print('Downloaded SDK package: ' + filename)
        sftp.close()
    commands = {
        'platform': 'uname -m; uname -r; cat /etc/os-release',
        'packages': "dpkg-query -W -f='${Package} ${Version}\\n' '*craft*' '*ustom*p*' '*ThirdParty*' 2>/dev/null",
        'sdk_files': 'ls -lh /root/pkg39 /usr/local /opt 2>/dev/null',
        'processes': 'ps -eo pid,comm,args | head -60',
        'compiler': 'command -v g++; command -v cmake; g++ --version | head -1; df -h / /tmp; free -m',
        'sdk_paths': "dpkg -L icraft | head -35; dpkg -L icraftmdzthirdparty | head -25; find /root -maxdepth 3 -name CMakeLists.txt -o -name '*toolchain*' 2>/dev/null | head -30",
    }
    results = {}
    for name, cmd in commands.items():
        _, stdout, stderr = client.exec_command(cmd, timeout=15)
        results[name] = {'stdout': stdout.read().decode(errors='replace'),
                         'stderr': stderr.read().decode(errors='replace'),
                         'exit_code': stdout.channel.recv_exit_status()}
    (ROOT / 'outputs/board_probe.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    for name in ('platform', 'packages', 'sdk_files', 'compiler'):
        print(name + ':\n' + results[name]['stdout'])
except paramiko.AuthenticationException:
    raise SystemExit('Authentication failed for the single documented credential. No further credentials attempted.')
finally:
    client.close()
