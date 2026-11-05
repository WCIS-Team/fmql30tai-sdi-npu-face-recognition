"""Build only the device-independent JPEG publisher in a new scratch folder."""
from school_connection import school_connection, ROOT
from datetime import datetime
import json
import uuid

out = ROOT / "outputs/lan-stream"
out.mkdir(exist_ok=True)
remote = "/D:/yzd/tmp/wcis-lan-20261013-" + uuid.uuid4().hex[:8]
result = dict(remote_directory=remote, built=False, board_accessed=False)
try:
    with school_connection() as client:
        sftp = client.open_sftp()
        sftp.mkdir(remote)
        for folder in ("include", "src"):
            sftp.mkdir(remote + "/" + folder)
        for filename in ("CMakeLists.txt", "include/wcis_jpeg_publisher.hpp", "include/wcis_raw_publisher.hpp",
                         "src/stream_demo.cpp", "src/raw_demo.cpp", "build-school.sh"):
            sftp.put(str(ROOT / "lan_stream" / filename), remote + "/" + filename)
        _, stdout, stderr = client.exec_command("D:/yzd/MSYS2/usr/bin/bash.exe --login " + remote.lstrip("/") + "/build-school.sh", timeout=120)
        stdout.channel.set_combine_stderr(True)
        with (out / "school-build.log").open("w", encoding="utf-8") as log:
            while True:
                chunk = stdout.channel.recv(8192)
                if not chunk:
                    break
                value = chunk.decode(errors="replace")
                log.write(value); log.flush(); print(value, end="", flush=True)
        code = stdout.channel.recv_exit_status()
        result["exit_code"] = code
        if code == 0:
            for filename in ("wcis_stream_demo", "elf-header.txt", "elf-dynamic.txt", "elf-versions.txt"):
                sftp.get(remote + "/build/" + filename, str(out / filename))
            result["built"] = True
        sftp.close()
except Exception as error:
    # Never print authentication contents or try alternative credentials.
    result["error_type"] = type(error).__name__
(out / "cross-build.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))
