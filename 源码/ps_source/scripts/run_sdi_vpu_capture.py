"""Board-side, exclusive launcher for the SDI/VPU worker; no automatic retries."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", choices=("camera", "vtc"), required=True)
    parser.add_argument("--frames", type=int, default=0)
    parser.add_argument("--warm-handoff", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.frames <= 3600:
        raise ValueError("Invalid finite frame limit")
    if args.warm_handoff and (args.source != 'camera' or args.frames):
        raise ValueError('Warm handoff requires a continuous camera worker')
    root = args.root.resolve()
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    proof = json.loads((root / "boot-proof.json").read_text())
    assert proof["boot_id"] == boot
    assert proof["boot_files"]["BOOT.bin"] in (
        "0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca",
        "f48397d08b1ccb1c950adafcebe5e36678154e73fa1d19792150aa5ddccd8ad1",
        # Full-board CLK1 repair: camera, FAC1 and dual-host LAN acceptance.
        "f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297",
    )
    assert not Path("/download.bit").exists() and Path("/root/live.disabled").exists()
    receipt = json.loads((root / "build-receipt.json").read_text())
    executable = root / "wcis_sdi_vpu_live"
    assert hashlib.sha256(executable.read_bytes()).hexdigest() == receipt["binary_sha256"]
    marker = Path("/root/wcis-face/hardware-review-required.json")
    assert not marker.exists() or json.loads(marker.read_text()).get("boot_id") != boot
    # The CPU-resident photo workers close the SDK after each inference. Their
    # service being active is not hardware ownership; the shared npu.lock below
    # covers each complete PL/NPU request and prevents simultaneous SDK opens.
    cfg = json.loads(Path("/root/wcis-face/video-stream-current.json").read_text())
    with (Path(cfg["release"]) / "npu.lock").open("a") as lock, Path("/root/wcis-camera-preview/camera.lock").open("a") as camera:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(camera, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for process in Path("/proc").iterdir():
            if not process.name.isdigit():
                continue
            for fd in (process / "fd").glob("*"):
                try:
                    target = os.readlink(fd)
                except OSError:
                    continue
                if target == "/dev/video0":
                    raise RuntimeError("VPU is owned by PID " + process.name)
        session = uuid.uuid4().hex
        directory = Path("/dev/shm") / ("wcis-vpu-" + args.source + "-" + session)
        directory.mkdir()
        env = os.environ.copy()
        env.pop("WCIS_VERIFIED_FACTORY_BOOT", None)
        if proof["boot_files"]["BOOT.bin"] == "0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca":
            env["WCIS_VERIFIED_FACTORY_BOOT"] = proof["boot_files"]["BOOT.bin"]
        env["WCIS_NPU_LOCK_FD"] = str(lock.fileno())
        env["WCIS_CAMERA_LOCK_FD"] = str(camera.fileno())
        command = [str(executable), args.source, boot, str(directory), str(args.frames)]
        if args.warm_handoff:command.append('warm')
        process = subprocess.Popen(command, env=env, pass_fds=(lock.fileno(), camera.fileno()))
        control = dict(source=args.source, session=session, boot_id=boot, pid=process.pid, directory=str(directory))
        if args.warm_handoff:control['handoff'] = 'warm_process'
        temporary = root / "current.tmp"
        temporary.write_text(json.dumps(control))
        temporary.replace(root / "current.json")
        def stop(signum, _):
            if process.poll() is None:
                process.send_signal(signum)
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        code = process.wait()
        report = dict(control, exit_code=code)
        (root / (session + "-result.json")).write_text(json.dumps(report, indent=2))
        if code:
            marker.write_text(json.dumps(dict(boot_id=boot, reason="SDI/VPU capture failed; review or full reboot before SDK reuse", source=args.source)))
        raise SystemExit(code)


if __name__ == "__main__":
    main()
