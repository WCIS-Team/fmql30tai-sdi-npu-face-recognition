from school_connection import school_connection, ROOT
import sys
sys.stdout.reconfigure(errors='replace')

with school_connection() as client:
    sftp = client.open_sftp()
    files = {
        'toolchain': '/D:/yzd/WCIS/crosswin/cmake/crosswin-toolchain.cmake',
        'project': '/D:/yzd/WCIS/crosswin/proj/CMakeLists.txt',
        'utils': '/D:/yzd/WCIS/crosswin/kit/cmake/icraft-utils-targets-aarch64.cmake',
    }
    for name, path in files.items():
        text = sftp.open(path, 'r').read().decode('utf-8', errors='replace')
        (ROOT / ('outputs/school_' + name + '.txt')).write_text(text, encoding='utf-8')
        if name != 'utils':
            print(name + ':\n' + text)
    sftp.close()
