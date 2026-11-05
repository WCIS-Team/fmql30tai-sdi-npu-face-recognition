"""Read PE import names only; do not execute or alter shared runtimes."""
import json
from pathlib import Path
import struct
import mmap

ROOT = Path(__file__).resolve().parent


def mapped_imports(data):
    if data[:2] != b"MZ":
        return []
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    if data[pe:pe + 4] != b"PE\x00\x00":
        return []
    sections, optional_size = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    directories = optional + (112 if magic == 0x20b else 96)
    import_rva = struct.unpack_from("<I", data, directories + 8)[0]
    if not import_rva:
        return []
    mappings = []
    for i in range(sections):
        position = optional + optional_size + i * 40
        virtual_size, address, raw_size, raw_offset = struct.unpack_from("<4I", data, position + 8)
        mappings.append((address, max(virtual_size, raw_size), raw_offset))

    def offset(rva):
        for address, size, raw in mappings:
            if address <= rva < address + size:
                return raw + rva - address
        raise ValueError("RVA outside PE sections")

    names, position = [], offset(import_rva)
    for _ in range(512):
        descriptor = struct.unpack_from("<5I", data, position)
        if not any(descriptor):
            break
        start = offset(descriptor[3])
        end = data.find(b"\x00", start, start + 256)
        if end < 0:
            raise ValueError("Invalid import name")
        names.append(data[start:end].decode("ascii"))
        position += 20
    return names


def imports(path):
    with path.open("rb") as stream:
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            return mapped_imports(data)


def main():
    bin_dir = ROOT / "icraft-portable/bin"
    folders = [bin_dir, ROOT / "runtime", Path("D:/yzd/tools/msvc1450"), Path("C:/Windows/System32")]
    pending = list(bin_dir.glob("*.dll")) + list(bin_dir.glob("*.exe"))
    seen, missing, checks = set(), set(), []
    while pending:
        path = pending.pop()
        if path.name.lower() in seen:
            continue
        seen.add(path.name.lower())
        for name in imports(path):
            if name.lower().startswith(("api-ms-", "ext-ms-")):
                continue
            match = next((folder / name for folder in folders if (folder / name).is_file()), None)
            if match is None:
                missing.add(name)
            elif match.parent == bin_dir:
                pending.append(match)
        checks.append(str(path))
    report = {"missing_non_system_imports": sorted(missing), "checked_module_count": len(checks), "checked_modules": checks}
    (ROOT / "native-dependencies.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("missing_non_system_imports", "checked_module_count")}), flush=True)


if __name__ == "__main__":
    main()
