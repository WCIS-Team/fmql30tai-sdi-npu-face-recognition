"""Verify a clean delivery tree, then optionally archive it outside the tree."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".Xil", "CMakeFiles", "node_modules", ".git"}
TEMP_SUFFIXES = {".pyc", ".pyo", ".o", ".obj", ".vvp", ".vcd", ".wdb", ".jou", ".pb", ".tmp", ".bak"}
SOURCE_ROOTS = ("fpga_source/", "ps_source/")


def verify(root):
    files = []
    errors = []
    for item in sorted(root.rglob("*")):
        rel = item.relative_to(root).as_posix()
        if item.is_symlink():
            errors.append("Symbolic link: " + rel)
            continue
        if any(part in CACHE_DIRS or part.endswith((".runs", ".cache", ".sim")) for part in item.relative_to(root).parts):
            errors.append("Cache/build directory: " + rel)
        if not item.is_file():
            continue
        files.append(item)
        if item.suffix.lower() in TEMP_SUFFIXES or ".backup." in item.name or item.name == "boot-image-dump.txt":
            errors.append("Intermediate file: " + rel)
        if rel.startswith(SOURCE_ROOTS):
            if any(part in {"outputs", "build", "build-restored", "Testing"} for part in item.relative_to(root).parts):
                errors.append("Output inside source: " + rel)
        if rel.startswith(("fpga_source/rtl/ip/", "fpga_source/rtl/sdi/ip/")) and item.suffix.lower() in {".xml", ".xdc", ".vh"}:
            errors.append("Regenerable IP output: " + rel)
    obsolete_web = ["index.html", "camera_panel.html", "camera_panel.js", "site_app.js", "recording_embed.js", "recording_panel.html", "recording_panel.js", "recording_service.py", "recording_library.py", "recording_compression.py"]
    for name in obsolete_web:
        if (root / "board_runtime/reference_release/app" / name).exists():
            errors.append("Unused website copy: app/" + name)
    manifests = [root / "filelist.json", *sorted(f for f in files if f.name == "filelist.json" and f.parent != root)]
    checked = 0
    for manifest_path in manifests:
        if not manifest_path.is_file():
            errors.append("Missing manifest: " + str(manifest_path))
            continue
        base = manifest_path.parent
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = set()
        for row in manifest["files"]:
            name = row["path"]
            path = (base / name).resolve()
            if not path.is_relative_to(base) or name in expected:
                errors.append("Invalid/duplicate manifest path: " + name)
                continue
            expected.add(name)
            if not path.is_file():
                errors.append("Missing file: " + name)
                continue
            data = path.read_bytes()
            if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
                errors.append("Checksum mismatch: " + str(path.relative_to(root)))
            checked += 1
        actual = {f.relative_to(base).as_posix() for f in files if f.is_relative_to(base)} - {"filelist.json", "filelist.txt"}
        if actual != expected:
            errors.append("Manifest file set mismatch: " + str(base.relative_to(root)))
        text_list = base / "filelist.txt"
        if not text_list.is_file() or text_list.read_text(encoding="utf-8").splitlines() != sorted(expected):
            errors.append("Text file list mismatch: " + str(base.relative_to(root)))
    if errors:
        raise ValueError("Delivery check failed:\n" + "\n".join(errors[:30]))
    return files, {"passed": True, "files": len(files), "bytes": sum(f.stat().st_size for f in files), "manifest_entries_checked": checked}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify without creating a ZIP")
    parser.add_argument("--out", type=Path, help="New ZIP path outside this delivery directory")
    args = parser.parse_args()
    if not args.check and args.out is None:
        parser.error("Choose --check or --out")
    out = args.out.resolve() if args.out else None
    if out is not None and (out.is_relative_to(ROOT) or out.exists()):
        raise ValueError("Choose a new ZIP outside the delivery directory")
    files, result = verify(ROOT)
    if out is not None:
        with zipfile.ZipFile(out, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9, strict_timestamps=False) as archive:
            for item in files:
                archive.write(item, item.relative_to(ROOT).as_posix())
        result["archive"] = str(out)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
