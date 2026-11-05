"""Resume the face task inside its existing, isolated school directory."""
from pathlib import Path
import sys
from school_connection import school_connection, ROOT

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
remote = '/D:/yzd/tmp/wcis-face-32b2a267'
old = Path('D:/renlianshibie_old_20261012/outputs/npu_preflight')
sources = {
    'yunet': old / 'opencv-zoo-icraft-3.36.1/yunet640/yunet640_parsed.json',
    'mobilefacenet': old / 'icraft-3.36.1/mobilefacenet112/mobilefacenet112_parsed.json',
}
with school_connection() as client:
    sftp = client.open_sftp()
    def mkdir(path):
        try: sftp.stat(path)
        except FileNotFoundError: sftp.mkdir(path)
    mkdir(remote + '/parsed-inputs')
    for name, source in sources.items():
        mkdir(remote + '/parsed-inputs/' + name)
        for extension in ('.json', '.raw'):
            sftp.put(str(source.with_suffix(extension)), remote + '/parsed-inputs/' + name + '/' + name + extension)
    sftp.put(str(ROOT / 'scripts/compile_face_models_school.py'), remote + '/compile_models.py')
    _, stdout, _ = client.exec_command('D:/yzd/asr/python/python.exe D:/yzd/tmp/wcis-face-32b2a267/compile_models.py --parsed-inputs', timeout=1800)
    stdout.channel.set_combine_stderr(True)
    with (ROOT / 'outputs/photo-board-20261014/school-model-build-from-ir.log').open('w', encoding='utf-8') as log:
        while True:
            chunk = stdout.channel.recv(8192)
            if not chunk: break
            value = chunk.decode('utf-8', errors='replace')
            print(value, end='', flush=True); log.write(value); log.flush()
    print('exit:', stdout.channel.recv_exit_status(), flush=True)
    sftp.get(remote + '/model-build-status.json', str(ROOT / 'outputs/photo-board-20261014/school-model-build-from-ir-status.json'))
