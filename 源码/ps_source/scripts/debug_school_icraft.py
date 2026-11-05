"""Identify the faulting DLL in a task-owned compiler process, without system changes."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import struct
import subprocess
import time
import sys

root = Path(__file__).resolve().parent
assert str(root).replace('\\', '/').lower().startswith('d:/yzd/tmp/wcis-face-')
k = C.WinDLL('kernel32', use_last_error=True)
k.GetFinalPathNameByHandleW.argtypes = [W.HANDLE, W.LPWSTR, W.DWORD, W.DWORD]
k.GetFinalPathNameByHandleW.restype = W.DWORD
k.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
k.GetThreadContext.argtypes = [W.HANDLE, C.c_void_p]
k.OpenThread.argtypes = [W.DWORD, W.BOOL, W.DWORD]; k.OpenThread.restype = W.HANDLE
k.ContinueDebugEvent.argtypes = [W.DWORD, W.DWORD, W.DWORD]
k.WaitForDebugEvent.argtypes = [C.c_void_p, W.DWORD]
k.SetErrorMode(0x8003)
bin = root / 'icraft-portable/bin'
env = os.environ.copy()
env['PATH'] = str(bin) + ';' + str(root / 'runtime') + ';D:/yzd/tools/msvc1450;' + env['PATH']
env['TMP'] = env['TEMP'] = str(root / 'scratch')
env.pop('ICRAFT_CUSTOM_DIR', None)
dest = root / 'debug-compiler'; dest.mkdir(exist_ok=True)
cmd = [str(bin / 'icraft-optimize.exe'), '--json', str(root / 'parsed-inputs/yunet/yunet.json'), '--raw', str(root / 'parsed-inputs/yunet/yunet.raw'), '--jr_path', str(dest), '--log_path', str(dest / 'logs'), '--target', 'zhuge']
if '--generate' in sys.argv:
    cmd = [str(bin / 'icraft-generate.exe'), '--json', str(root / 'face-models/mobilefacenet/adapt/mobilefacenet_adapted.json'), '--raw', str(root / 'face-models/mobilefacenet/adapt/mobilefacenet_adapted.raw'), '--jr_path', str(dest), '--log_path', str(dest / 'logs'), '--cores', '1', '--rows', '4', '--cols', '4']
modules = []
faults = []
def path(handle):
    out = C.create_unicode_buffer(32768)
    return out.value if not k.GetFinalPathNameByHandleW(handle, out, len(out), 0) else out.value
def memory(address, length):
    result = C.create_string_buffer(length); got = C.c_size_t()
    if not k.ReadProcessMemory(process, address, result, length, C.byref(got)): return b''
    return result.raw[:got.value]
with (dest / 'console.log').open('wb') as log:
    p = subprocess.Popen(cmd, env=env, cwd=root, stdout=log, stderr=subprocess.STDOUT, creationflags=2)
    end = time.monotonic() + 240
    process = None
    while time.monotonic() < end:
        event = C.create_string_buffer(176)
        if not k.WaitForDebugEvent(event, 1000): continue
        data = event.raw
        code, pid, tid = struct.unpack_from('<III', data)
        if code == 3:
            file, process, thread, base = struct.unpack_from('<QQQQ', data, 16)
            modules.append({'base': base, 'path': path(file)})
        elif code == 6:
            file, base = struct.unpack_from('<QQ', data, 16)
            modules.append({'base': base, 'path': path(file)})
        elif code == 1:
            exc = struct.unpack_from('<I', data, 16)[0]
            address = struct.unpack_from('<Q', data, 32)[0]
            if exc != 0x80000003:
                below = sorted((m for m in modules if m['base'] <= address), key=lambda m: m['base'])
                module = below[-1] if below else {'base': 0, 'path': ''}
                item = {'exception': hex(exc), 'address': hex(address), 'module': module['path'], 'rva': hex(address-module['base']), 'first_chance': struct.unpack_from('<I',data,168)[0]}
                count = struct.unpack_from('<I',data,40)[0]
                item['exception_parameters'] = [hex(v) for v in struct.unpack_from('<'+str(min(count,15))+'Q',data,48)]
                if exc == 0xe06d7363 and count == 4:
                    _, obj, throw, image = struct.unpack_from('<4Q',data,48)
                    info = memory(throw,16)
                    if len(info)==16:
                        array = memory(image+struct.unpack_from('<I',info,12)[0],8)
                        if len(array)==8:
                            caught = memory(image+struct.unpack_from('<I',array,4)[0],28)
                            if len(caught)==28:
                                descriptor = memory(image+struct.unpack_from('<I',caught,4)[0],160)
                                item['cxx_type'] = descriptor[16:].split(b'\0')[0].decode(errors='replace')
                    raw = memory(obj,128)
                    item['object_strings'] = []
                    for at in range(0,len(raw)-7,8):
                        ptr = struct.unpack_from('<Q',raw,at)[0]
                        if ptr>65536 and ptr<0x7fffffffffff:
                            text = memory(ptr,256).split(b'\0')[0]
                            if len(text)>4 and all(32<=b<127 for b in text):item['object_strings'].append(text.decode())
                faults.append(item); print(json.dumps(item), flush=True)
                (dest / 'faults.json').write_text(json.dumps({'faults': faults, 'modules': modules}, indent=2))
                k.ContinueDebugEvent(pid, tid, 0x80010001)
                continue
        k.ContinueDebugEvent(pid, tid, 0x10002)
        if code == 5: break
    if p.poll() is None:
        k.DebugActiveProcessStop(pid)
        p.kill()
    p.wait(timeout=5)
(dest / 'faults.json').write_text(json.dumps({'faults': faults, 'modules': modules, 'exit_code':p.returncode}, indent=2))
