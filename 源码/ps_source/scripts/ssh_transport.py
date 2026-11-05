"""Project SSH connection. Host key is pinned; credential stays out of logs."""
from pathlib import Path
from contextlib import contextmanager
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tools/python'))
import paramiko
from school_connection import jump_password

@contextmanager
def board_jump_connection():
    """Reach the board through its LAN gateway 102; keep the pinned identity."""
    client = paramiko.SSHClient()
    client.load_host_keys(str(ROOT / 'outputs/school_known_hosts'))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect('192.168.1.102', username='user', password=jump_password(),
                       look_for_keys=False, allow_agent=False, timeout=15,
                       banner_timeout=20, auth_timeout=20)
        yield client
    finally:
        client.close()

@contextmanager
def board_connection():
    doc = Path(r'C:\Users\anxianji\AppData\Local\Temp\wcis-device-review-2e2a2014089c484a86dd1caa56de008e\md\技术文档\板卡镜像实测取证.md')
    match = re.search(r'用户名\s*`root`[^\n]*口令\s*`([^`]+)`', doc.read_text(encoding='utf-8'))
    if not match:
        raise RuntimeError('Documented credential missing')
    client = paramiko.SSHClient()
    client.load_host_keys(str(ROOT / 'outputs/board_known_hosts'))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        with board_jump_connection() as jump:
            channel = jump.get_transport().open_channel(
                'direct-tcpip', ('192.168.1.113', 22), ('127.0.0.1', 0), timeout=20)
            client.connect('192.168.1.113', username='root', password=match.group(1),
                           sock=channel, look_for_keys=False, allow_agent=False, timeout=30,
                           banner_timeout=45, auth_timeout=30)
            yield client
    finally:
        client.close()
