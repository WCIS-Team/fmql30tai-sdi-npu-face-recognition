"""Compile isolated YuNet/MobileFaceNet NPU candidates; never opens the board."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OLD = Path("D:/renlianshibie_old_20261012/outputs/npu_preflight")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="outputs/face-npu-20261014")
    parser.add_argument("--only", choices=("yunet", "mobilefacenet"))
    args = parser.parse_args()
    out = (ROOT / args.out).resolve()
    if not out.is_relative_to((ROOT / "outputs").resolve()):
        raise SystemExit("Output must stay in task outputs")
    out.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["ICRAFT_CUSTOM_DIR"] = "C:/Icraft/CustomOp_v3.36.1"
    env["PATH"] = "C:/Icraft/CLI v3.36.1/bin;" + env["PATH"]
    report = {"date_utc": datetime.now(timezone.utc).isoformat(), "tool_version": "3.36.1",
              "precision": "bf16", "board_accessed": False, "models": {}}
    sources = [("yunet", OLD / "opencv-zoo-icraft-3.36.1/yunet640/yunet640_parsed.json"),
               ("mobilefacenet", OLD / "icraft-3.36.1/mobilefacenet112/mobilefacenet112_parsed.json")]
    for name, source in sources:
        if args.only and name != args.only:
            continue
        record = {"source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "stages": []}
        report["models"][name] = record
        for stage in ("optimize", "quantize", "adapt", "generate"):
            dest = out / name / ("optimized-flow-" + stage)
            dest.mkdir(parents=True, exist_ok=True)
            cmd = ["C:/Icraft/CLI v3.36.1/bin/icraft.exe", stage, "--json", str(source),
                   "--raw", str(source.with_suffix(".raw")), "--jr_path", str(dest), "--log_path", str(dest / "logs")]
            if stage in ("optimize", "adapt", "quantize"):
                cmd += ["--target", "zhuge"]
            if stage == "quantize":
                cmd += ["--qdtype", "bf16", "--no_transinput", "true", "--no_imagemake", "true"]
            with (dest / "console.log").open("w", encoding="utf-8") as log:
                done = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
            files = list(dest.glob("*.json"))
            item = {"stage": stage, "args": cmd, "exit_code": done.returncode}
            record["stages"].append(item)
            (out / "build-status.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(name, stage, "exit", done.returncode, flush=True)
            if done.returncode or len(files) != 1:
                print((dest / "console.log").read_text(encoding="utf-8", errors="replace")[-1600:], flush=True)
                raise SystemExit(1)
            source = files[0]
            item["json"] = str(source)
            item["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        record["generated"] = True
    report["generated"] = True
    (out / "build-status.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
