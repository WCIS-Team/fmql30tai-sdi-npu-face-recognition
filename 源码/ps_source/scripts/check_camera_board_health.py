"""Read Linux files only. No SDK, MMIO, capture, reset, boot mount or writes."""
import json
import socket
from datetime import datetime, timezone
from ssh_transport import ROOT, board_connection

out = ROOT / "outputs/sdi-diagnostics-20261014/board-health.json"
result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
          "sdk_opened": False, "capture_requested": False, "boot_modified": False}
try:
    with socket.create_connection(("192.168.1.113", 22), timeout=2):
        pass
    with board_connection() as client:
        with client.open_sftp() as sftp:
            for key, path in (("boot_id", "/proc/sys/kernel/random/boot_id"),
                              ("uptime", "/proc/uptime"),
                              ("load", "/proc/loadavg"),
                              ("capture_review", "/root/wcis-camera-preview/capture-review-required.json")):
                with sftp.open(path, "r") as file:
                    value = file.read(2048).decode().strip()
                    result[key] = json.loads(value) if key == "capture_review" else value
            with sftp.open("/proc/meminfo", "r") as file:
                lines = file.read(8192).decode().splitlines()
                result["memory"] = [line for line in lines if line.startswith(("MemAvailable:", "SwapFree:"))]
        result["connected"] = True
except Exception as error:
    result.update(connected=False, error_type=type(error).__name__)
out.parent.mkdir(exist_ok=True, parents=True)
out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
