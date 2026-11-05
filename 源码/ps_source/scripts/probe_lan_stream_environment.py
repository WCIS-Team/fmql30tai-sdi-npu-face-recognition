"""Read-only board inventory for LAN streaming; never opens a video device."""
from ssh_transport import board_connection, ROOT
import json

commands = {
    "network": "hostname -I; ip -4 route",
    "resources": "uptime; free -m",
    "video_nodes": "ls -l /dev/video* 2>/dev/null; for f in /sys/class/video4linux/video*/name; do [ ! -f \"$f\" ] || cat \"$f\"; done",
    "tools": r"command -v curl; command -v ffmpeg; command -v v4l2-ctl; command -v python3; ldconfig -p | awk '/opencv|libjpeg|libstdc\+\+/{print}'",
}
result = {}
with board_connection() as client:
    for key, command in commands.items():
        _, out, err = client.exec_command(command, timeout=10)
        result[key] = dict(stdout=out.read().decode(errors="replace"), stderr=err.read().decode(errors="replace"), exit_code=out.channel.recv_exit_status())
dest = ROOT / "outputs/lan-stream"
dest.mkdir(exist_ok=True)
(dest / "board_environment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
for key in ("network", "resources", "video_nodes"):
    print(key + ": " + result[key]["stdout"])
