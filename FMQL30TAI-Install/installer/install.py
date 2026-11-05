"""Shared installer engine, compatible with CPython 3.8 on Linux/Windows."""
import argparse
import base64
from datetime import datetime
import getpass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import uuid
import webbrowser

import paramiko

ROOT = Path(__file__).resolve().parents[1]
BINARIES = {
    'wcis_camera_owner': 'app/wcis_camera_owner',
    'wcis_face_cached': 'app/wcis_face_cached',
    'wcis_face_pl_retained': 'app/wcis_face_pl_retained',
    'wcis_face_pad': 'pad/wcis_face_pad',
    'wcis_face_npu': 'identity/wcis_face_npu',
}
PROBE = ('set -eu; command -v cmake >/dev/null; '
         'test -x /usr/bin/aarch64-linux-gnu-g++; '
         'test -f /usr/cmake/icraft-zg330backend-config.cmake; '
         "grep -q '3.39.0' /usr/cmake/icraft-zg330backend-config-version.cmake; "
         'test -d /ModelzooDeps/aarch64/Static; '
         'test -f /usr/lib/aarch64-linux-gnu/libz.so; '
         '/usr/bin/aarch64-linux-gnu-g++ -dumpmachine')


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()


def verify_package(root):
    manifest = json.loads((root/'MANIFEST.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        p = (root/row['path']).resolve()
        if root.resolve() not in p.parents or not p.is_file() or p.stat().st_size != row['bytes'] or sha(p) != row['sha256']:
            raise RuntimeError('安装包文件缺失或被修改：'+row['path'])
    return len(manifest['files'])


def check_elf(path):
    h = path.read_bytes()[:20]
    if len(h) < 20 or h[:7] != b'\x7fELF\x02\x01\x01' or h[18:20] != b'\xb7\x00' or h[16:18] not in (b'\x02\x00', b'\x03\x00'):
        raise RuntimeError('编译输出不是 AArch64 ELF：'+str(path))


def capture(args, timeout=25):
    try:
        return subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=timeout, creationflags=0x08000000 if os.name == 'nt' else 0)
    except (OSError, subprocess.TimeoutExpired): return None


def find_compiler(config):
    candidates = []
    for engine in ([config['container_engine']] if config.get('container_engine') else ['podman', 'docker']):
        exe = shutil.which(engine)
        if not exe: continue
        info = capture([exe, 'info'])
        if info is None or info.returncode: continue
        if config.get('container_image'):
            images = [config['container_image']]
        else:
            listing = capture([exe, 'images', '--format', '{{.Repository}}:{{.Tag}}'])
            images = [] if not listing or listing.returncode else sorted(set(listing.stdout.splitlines()))
            images = [x for x in images if re.search('icraft|fpai', x, re.I) and '<none>' not in x]
        for image in images:
            # Only inspect local images; no pull and no modification of the shared image.
            inspected = capture([exe, 'image', 'inspect', image])
            if not inspected or inspected.returncode: continue
            meta = json.loads(inspected.stdout)[0]
            image_id = meta.get('Id') or meta.get('ID')
            if not image_id: continue
            probe = capture([exe, 'run', '--rm', '--network=none', '--entrypoint', '/bin/sh', image_id, '-c', PROBE], timeout=45)
            if probe and probe.returncode == 0 and 'aarch64' in probe.stdout:
                candidates.append((exe, image_id, image))
    if not candidates:
        raise RuntimeError('未找到可用 iCraft Linux 编译容器。请启动 Podman/Docker，导入带 AArch64 GCC、CMake、iCraft 3.39、ModelzooDeps 和 ARM64 zlib 开发库的 fpai-ub2004 环境后重试。仅安装 iCraft 图形程序不等于具备这个编译环境；本脚本尚未修改板卡。')
    if len(candidates) == 1: return candidates[0]
    print('发现多个编译环境：')
    for i, (_, image_id, name) in enumerate(candidates, 1): print('  {}. {} ({})'.format(i, name, image_id[:19]))
    n = input('选择编号 [1]：').strip() or '1'
    if not n.isdigit() or not 1 <= int(n) <= len(candidates): raise RuntimeError('编号无效')
    return candidates[int(n)-1]


def stream_command(args, log, timeout=3600):
    # File redirection avoids deadlock when compilers produce no newline for a while.
    with log.open('wb') as sink:
        p = subprocess.Popen(args, stdout=sink, stderr=subprocess.STDOUT,
                             creationflags=0x08000000 if os.name == 'nt' else 0)
        start = time.monotonic(); pos = 0
        try:
            while p.poll() is None:
                if time.monotonic()-start > timeout:
                    p.terminate(); p.wait(timeout=15)
                    raise RuntimeError('编译超时，请查看 '+str(log))
                time.sleep(.5)
                with log.open('rb') as reader:
                    reader.seek(pos); data = reader.read(); pos = reader.tell()
                if data: print(data.decode('utf-8', errors='replace'), end='', flush=True)
        except BaseException:
            if p.poll() is None: p.terminate()
            raise
    with log.open('rb') as reader:
        reader.seek(pos); print(reader.read().decode('utf-8', errors='replace'), end='')
    if p.returncode: raise RuntimeError('编译失败，退出码 {}；查看 {}'.format(p.returncode, log))


def compile_ps(root, work, compiler):
    exe, image_id, image = compiler
    build = work/'compile'; build.mkdir()
    container = 'wcis-build-'+uuid.uuid4().hex
    identity = ['--user', '0'] if os.name == 'nt' else ['--user', '{}:{}'.format(os.getuid(), os.getgid())]
    if os.name != 'nt' and 'podman' in Path(exe).name:
        identity += ['--userns=keep-id']
    args = [exe, 'run', '--rm', '--name', container, '--network=none'] + identity + ['--entrypoint', '/bin/sh',
            '-v', (root/'source').as_posix()+':/source:ro',
            '-v', (root/'installer').as_posix()+':/scripts:ro', '-v', build.as_posix()+':/work',
            image_id, '/scripts/build_ps.sh']
    try:
        stream_command(args, work/'compile.log')
    except BaseException:
        capture([exe, 'stop', '--time', '10', container], timeout=20)
        raise
    for name in BINARIES: check_elf(build/'bin'/name)
    (work/'build-receipt.json').write_text(json.dumps(dict(image=image, image_id=image_id,
        binaries={n:sha(build/'bin'/n) for n in BINARIES}), indent=2), encoding='utf-8')
    return build/'bin'


class PinFirstHost(paramiko.MissingHostKeyPolicy):
    def __init__(self, path): self.path = path
    def missing_host_key(self, client, hostname, key):
        fp = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
        print('首次连接板卡，记录 SSH 指纹 SHA256:'+fp)
        client.get_host_keys().add(hostname, key.get_name(), key)
        client.save_host_keys(str(self.path))


def connect(host, password, known):
    c = paramiko.SSHClient()
    if known.exists(): c.load_host_keys(str(known))
    c.set_missing_host_key_policy(PinFirstHost(known))
    try:
        c.connect(host, port=22, username='root', password=password,
                  look_for_keys=False, allow_agent=False, timeout=10,
                  banner_timeout=15, auth_timeout=15)
        return c
    except BaseException:
        c.close(); raise


def remote(c, cmd, log=None, source=None, timeout=2400):
    chan = c.get_transport().open_session(timeout=20)
    chan.set_combine_stderr(True); chan.exec_command(cmd)
    if source is not None: chan.sendall(source.encode('utf-8'))
    chan.shutdown_write(); result = bytearray(); start = time.monotonic()
    sink = log.open('ab') if log else None
    try:
        while True:
            if chan.recv_ready():
                data = chan.recv(8192); result.extend(data)
                if sink: sink.write(data); sink.flush()
                if log: print(data.decode('utf-8', errors='replace'), end='', flush=True)
            elif chan.exit_status_ready(): break
            else:
                if time.monotonic()-start > timeout: raise RuntimeError('板端步骤超时；请检查板端状态，不要重复启动硬件')
                time.sleep(.1)
        code = chan.recv_exit_status()
    finally:
        chan.close()
        if sink: sink.close()
    output = result.decode('utf-8', errors='replace')
    if code: raise RuntimeError('板端步骤失败 ({})：{}'.format(code, output[-1800:]))
    rows = [x[len('WCIS_RESULT '):] for x in output.splitlines() if x.startswith('WCIS_RESULT ')]
    return json.loads(rows[-1]) if rows else output


def make_payload(root, work, binaries):
    payload = work/'payload'
    shutil.copytree(root/'payload/runtime', payload/'runtime')
    for name, rel in BINARIES.items():
        shutil.copy2(binaries/name, payload/'runtime/reference_release'/rel)
    shutil.copy2(root/'installer/board_install.py', payload/'board_install.py')
    rows = {p.relative_to(payload).as_posix():sha(p) for p in payload.rglob('*') if p.is_file()}
    (payload/'payload-hashes.json').write_text(json.dumps({'files':rows}, indent=2), encoding='utf-8')
    archive = work/'payload.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for p in sorted(payload.rglob('*')):
            if p.is_symlink(): raise RuntimeError('安装包中不允许符号链接')
            if p.is_file():
                info = tar.gettarinfo(str(p), arcname='payload/'+p.relative_to(payload).as_posix())
                info.uid=info.gid=0;info.uname=info.gname='root';info.mode=0o644
                with p.open('rb') as f: tar.addfile(info, f)
    return archive


def reconnect(host, password, known, previous_boot):
    print('等待板卡重启并恢复网络，最多 20 分钟；请保持供电。')
    deadline = time.monotonic()+1200; last_notice = 0
    while time.monotonic() < deadline:
        try:
            c = connect(host, password, known)
            current = remote(c, 'cat /proc/sys/kernel/random/boot_id', timeout=15).strip()
            if current != previous_boot: return c
            c.close()
        except (paramiko.BadHostKeyException, paramiko.AuthenticationException): raise
        except (OSError, EOFError, paramiko.SSHException, RuntimeError): pass
        if time.monotonic()-last_notice > 30:
            print('仍在等待网络恢复……', flush=True); last_notice=time.monotonic()
        time.sleep(5)
    raise RuntimeError('等待重连超时。可能 DHCP 地址变化；确认新 IP 后重新运行。不要反复断电。')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--check', action='store_true', help='仅检查本机包完整性')
    p.add_argument('--preflight', action='store_true', help='只读检查编译环境和板卡，不上传或安装')
    a = p.parse_args()
    print('FMQL30TAI 一键编译安装\n使用随包 BOOT；只编译五个 PS 程序。')
    count = verify_package(ROOT)
    print('安装包完整性通过：{} 个文件。'.format(count))
    if a.check: return
    host = str(ipaddress.IPv4Address(input('请输入板卡 IP 地址：').strip()))
    config = json.loads((ROOT/'settings.json').read_text(encoding='utf-8'))
    if set(config) - {'container_engine', 'container_image'} or any(not isinstance(v, str) for v in config.values()):
        raise RuntimeError('settings.json 只允许字符串字段 container_engine 和 container_image')
    print('正在检查已有的 iCraft 编译环境……')
    compiler = find_compiler(config)
    if os.name == 'nt':
        state = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local')))/'FMQL30TAI-Installer'
    else:
        state = Path(os.environ.get('XDG_STATE_HOME', str(Path.home()/'.local/state')))/'fmql30tai-installer'
    state.mkdir(parents=True, exist_ok=True)
    # No credential is saved or placed in a command argument/environment variable.
    password = getpass.getpass('请输入板卡 root 密码（输入不显示）：')
    if not password: raise RuntimeError('密码不能为空')
    known = state/'known_hosts'
    c = connect(host, password, known)
    agent = (ROOT/'installer/board_install.py').read_text(encoding='utf-8')
    try:
        board = remote(c, 'python3 -B - inspect', source=agent, timeout=40)
        print('已连接：{}；启动分区 {}。'.format(board['model'],board['sd']['device']))
        if board['current_boot_quarantined']:
            raise RuntimeError('当前启动有硬件保护标记，脚本不会删除；请先检查故障并按说明正常重启。')
        if board['free_bytes'] < 800*1024*1024: raise RuntimeError('板端根分区可用空间不足 800 MiB')
        if a.preflight:
            print(json.dumps(board, ensure_ascii=False, indent=2)); print('只读检查完成，未安装。'); return
        if board['existing_install']:
            print('板上已有安装。本次将停止视觉服务、备份并更新程序；人员库和录像保留。')
            if input('确认更新此板，请输入 UPDATE：').strip() != 'UPDATE':
                print('已取消。'); return
    finally: c.close()
    run_id = datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    work = state/'runs'/run_id;work.mkdir(parents=True)
    (work/'board-before.json').write_text(json.dumps(board,ensure_ascii=False,indent=2),encoding='utf-8')
    print('开始编译。日志目录：'+str(work))
    binaries = compile_ps(ROOT, work, compiler)
    archive = make_payload(ROOT, work, binaries)
    remote_root = '/root/wcis-install-runs/'+run_id
    c = connect(host, password, known)
    try:
        remote(c, 'mkdir -p '+shlex.quote(remote_root))
        with c.open_sftp() as sftp:
            print('上传安装文件……');sftp.put(str(archive),remote_root+'/payload.tar.gz')
        actual = remote(c,'sha256sum '+shlex.quote(remote_root+'/payload.tar.gz')).split()[0]
        if actual != sha(archive): raise RuntimeError('上传文件校验失败，未安装')
        remote(c,'tar --no-same-owner -xzf '+shlex.quote(remote_root+'/payload.tar.gz')+' -C '+shlex.quote(remote_root))
        prefix = 'python3 -B '+shlex.quote(remote_root+'/payload/board_install.py')
        suffix = ' --bundle '+shlex.quote(remote_root+'/payload')
        print('核对启动文件；需要更新时会备份、写入并重启板卡。')
        boot = remote(c,prefix+' boot'+suffix,work/'board-install.log')
        if boot['reboot_required']:
            remote(c,'sync && systemd-run --unit=wcis-install-reboot-'+run_id+' --on-active=3s /bin/systemctl reboot',timeout=30)
            c.close();c=reconnect(host,password,known,boot['boot_id'])
            verified = remote(c,prefix+' boot'+suffix,work/'board-install.log')
            if verified['reboot_required']: raise RuntimeError('重启后启动文件仍不匹配，停止安装')
        print('安装 SDK、程序和服务，随后检查相机帧号。')
        result = remote(c,prefix+' install'+suffix,work/'board-install.log',timeout=3600)
        (work/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('\n安装完成，服务就绪且相机帧号持续增加。')
        print('主站：http://{}:8091/\n预览：http://{}:8092/\n录像：http://{}:8093/'.format(host,host,host))
        print('请在页面完成人脸登记/识别、录像和回放验收。\n板端备份：'+remote_root+'/backup')
        webbrowser.open('http://{}:8091/'.format(host))
    finally:
        c.close();password=None


def cli():
    try: main()
    except KeyboardInterrupt:
        print('\n操作已中断。若板端步骤已开始，请先核对日志和板端状态再重试。');sys.exit(130)
    except paramiko.BadHostKeyException:
        print('\n停止：板卡 SSH 身份发生变化。请确认设备后由管理员核对 known_hosts；脚本不会忽略校验。');sys.exit(1)
    except paramiko.AuthenticationException:
        print('\n登录失败：请核对 root 密码及 SSH 密码登录设置。');sys.exit(1)
    except Exception as e:
        print('\n未完成：'+str(e));sys.exit(1)


if __name__ == '__main__': cli()
