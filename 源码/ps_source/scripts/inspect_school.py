from school_connection import school_connection, ROOT

with school_connection() as client:
    sftp = client.open_sftp()
    print('SFTP home:', sftp.normalize('.'))
    results = []
    for cmd in ('whoami', 'cmd /c ver', 'tasklist /FI "IMAGENAME eq python.exe"',
                'D:/yzd/MSYS2/usr/bin/bash.exe --login -c "ls -ld /d/yzd/WCIS/crosswin/kit /d/yzd/WCIS/crosswin/cmake; cat /d/yzd/WCIS/crosswin/build.sh"'):
        _, out, err = client.exec_command(cmd, timeout=30)
        value = out.read().decode(errors='replace') + err.read().decode(errors='replace')
        results.append(cmd + '\n' + value)
        print(value)
    (ROOT / 'outputs/school_probe.txt').write_text('\n'.join(results), encoding='utf-8')
    sftp.close()
