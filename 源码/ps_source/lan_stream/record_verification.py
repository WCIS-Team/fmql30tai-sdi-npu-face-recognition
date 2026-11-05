"""Combine existing test/build evidence; never contact a board or server."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/lan-stream"
record = json.loads((OUT / "verification.json").read_text(encoding="utf-8"))
record["cross_build"] = json.loads((OUT / "cross-build.json").read_text(encoding="utf-8"))
record["arm_binary_sha256"] = hashlib.sha256((OUT / "wcis_stream_demo").read_bytes()).hexdigest()
record["browser_verified"] = dict(demo_source_label=True, decoded_width=640, decoded_height=360,
                                  reconnect=True, old_frame_hidden_on_disconnect=True,
                                  screenshots=["browser-demo.jpg", "browser-offline.jpg"])
record["windows_launcher_verified"] = True
record["board_connection"] = dict(address="192.168.1.113", result="TCP timeout", camera_ready=False)
record["real_camera_actor_integrated"] = False
record["other_lan_devices_verified"] = False
record["receiver_running_after_verification"] = False
(OUT / "delivery.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(record, ensure_ascii=False))
