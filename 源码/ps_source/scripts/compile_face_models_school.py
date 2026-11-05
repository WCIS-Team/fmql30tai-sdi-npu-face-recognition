"""School-side native iCraft build. No system install, GPU, or board access."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import ctypes
import sys
import argparse

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parsed-inputs', action='store_true', help='Use audited 3.36 parsed IR, then run every remaining stage with 3.39')
    parser.add_argument('--relu-inputs', action='store_true', help='Use independently checked equivalent PReLU decomposition')
    parser.add_argument('--only', choices=('yunet', 'mobilefacenet'))
    parser.add_argument('--logits-inputs', action='store_true')
    parser.add_argument('--dense-inputs', action='store_true')
    parser.add_argument('--no-neg-inputs', action='store_true')
    parser.add_argument('--conv-slope-inputs', action='store_true')
    parser.add_argument('--precision', choices=('bf16','fp16'), default='fp16')
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    assert str(ROOT).replace("\\", "/").lower().startswith("d:/yzd/tmp/wcis-face-")
    bins = list((ROOT / "icraft-portable").rglob("icraft.exe"))
    if len(bins) != 1:
        raise RuntimeError("Expected one native iCraft executable")
    binary = bins[0]
    # The old system CRT is searched before PATH. Use task-local copies beside
    # the executable, without installing or replacing any server system DLL.
    for runtime in Path('D:/yzd/tools/msvc1450').glob('*.dll'):
        target = binary.parent / runtime.name
        if not target.exists():
            target.write_bytes(runtime.read_bytes())
    vcomp = ROOT / 'runtime/vcomp140.dll'
    if vcomp.exists() and not (binary.parent / vcomp.name).exists():
        (binary.parent / vcomp.name).write_bytes(vcomp.read_bytes())
    env = os.environ.copy()
    env["PATH"] = str(binary.parent) + ";" + str(ROOT / "runtime") + ";D:/yzd/tools/msvc1450;" + str(ROOT / "7zip") + ";" + env["PATH"]
    # Headless SSH builds must return loader errors instead of showing a modal dialog.
    ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    empty = ROOT / "no-custom-ops"
    empty.mkdir(exist_ok=True)
    env["ICRAFT_CUSTOM_DIR"] = str(empty)
    for key in ("TMP", "TEMP", "TMPDIR"):
        env[key] = str(ROOT / "scratch")
    env["XDG_CACHE_HOME"] = str(ROOT / "cache")
    status = {"server_directory": str(ROOT), "board_accessed": False, "stages": {}, "precision": args.precision, 'rows':4, 'cols':2,
              "parser_version": "3.36.1" if args.parsed_inputs else "3.39.0", "compiler_version": "3.39.0"}
    for name, size in (("yunet", 640), ("mobilefacenet", 112)):
        if args.only and args.only != name:
            continue
        source = ROOT / 'parsed-inputs' / name / (name + '.json') if args.parsed_inputs else ROOT / (name + ".onnx")
        if args.relu_inputs and name == 'mobilefacenet':
            source = ROOT / 'mobilefacenet-relu.onnx'
        if args.no_neg_inputs and name == 'mobilefacenet':
            source = ROOT / 'mobilefacenet-no-neg.onnx'
        if args.conv_slope_inputs and name == 'mobilefacenet':
            source = ROOT / 'mobilefacenet-conv-slope.onnx'
        if args.logits_inputs and name == 'yunet':
            source = ROOT / 'yunet-logits.onnx'
        if args.dense_inputs and name == 'yunet':
            source = ROOT / 'yunet-dense-heads.onnx'
        stages = ("optimize", "quantize", "adapt", "generate") if args.parsed_inputs else ("parse", "optimize", "quantize", "adapt", "generate")
        for stage in stages:
            folder = 'face-models-conv-slope' if args.conv_slope_inputs else 'face-models-no-neg' if args.no_neg_inputs else 'face-models-dense' if args.dense_inputs else 'face-models-logits' if args.logits_inputs else 'face-models-relu' if args.relu_inputs else "face-models-from-ir" if args.parsed_inputs else "face-models"
            destination = ROOT / folder / name / stage
            destination.mkdir(parents=True, exist_ok=True)
            cmd = [str(binary.parent / ("icraft-" + stage + ".exe")), "--jr_path", str(destination), "--log_path", str(destination / "logs")]
            if stage == "parse":
                cmd += ["--net_name", name, "--network", str(source), "--framework", "onnx", "--target", "zhuge",
                        "--inputs", f"1,{size},{size},3", "--inputs_dtype", "FP32", "--inputs_layout", "NHWC",
                        "--pre_method", "nop", "--pre_scale", "1,1,1", "--pre_mean", "0,0,0", "--channel_swap", "0,1,2"]
            else:
                cmd += ["--json", str(source), "--raw", str(source.with_suffix(".raw"))]
                if stage != "generate":
                    cmd += ["--target", "zhuge"]
                if stage == "quantize":
                    cmd += ["--qdtype", args.precision, "--no_transinput", "true", "--no_imagemake", "true"]
                if stage == "generate":
                    cmd += ["--cores", "1", "--rows", "4", "--cols", "2"]
            print(name, stage, "started", flush=True)
            with (destination / "console.log").open("wb") as log:
                done = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            item = {"exit_code": done.returncode, "args": cmd}
            status["stages"][name + "-" + stage] = item
            print(name, stage, "exit", done.returncode, flush=True)
            (ROOT / "model-build-status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
            outputs = list(destination.glob("*.json"))
            if done.returncode or len(outputs) != 1:
                print((destination / "console.log").read_text(encoding="utf-8", errors="replace")[-2500:], flush=True)
                raise SystemExit(1)
            source = outputs[0]
            item["json"] = str(source)
            item["json_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    status["generated"] = True
    (ROOT / "model-build-status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
