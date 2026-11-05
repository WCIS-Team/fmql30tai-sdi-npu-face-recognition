"""Bind saved SDI2 evidence to current source; no build, SDK or board access."""
import hashlib
import json
import re
from pathlib import Path
from integrate_case import ROOT, SOURCE

OUT = ROOT / "outputs/sdi-diagnostics-20261014"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((ROOT/"docs/source_manifest.json").read_text(encoding="utf-8-sig"))
    for entry in manifest["patched"]:
        rel = Path(entry["path"])
        if sha(SOURCE/rel) != entry["original_sha256"] or sha(ROOT/"case"/rel) != entry["patched_sha256"]:
            raise RuntimeError(f"Source manifest mismatch: {rel}")
    if sha(ROOT/"rtl/wcis_sdi_monitor.v") != sha(ROOT/"case/rtl/wcis/wcis_sdi_monitor.v"):
        raise RuntimeError("Staged monitor differs")
    suites = json.loads((ROOT/"outputs/sim/summary.json").read_text(encoding="utf-8-sig"))
    expected = {"sdi_monitor", "vtc_pipeline", "vtc_resize_chain", "frame_rate_gate",
                "stream_letterbox", "case_registers", "case_resize"}
    if {item["suite"] for item in suites["suites"] if item["passed"]} != expected:
        raise RuntimeError("Missing RTL suite")
    for name in expected:
        if not re.search(r"(?m)^PASS ", (ROOT/"outputs/sim"/(name+".log")).read_text(encoding="utf-8-sig")):
            raise RuntimeError("Missing simulation PASS")
    elaboration = (ROOT/"outputs/sdi-case-elaboration.log").read_text(errors="replace")
    if not re.search(r"(?m)^WCIS FULL CASE RTL ELABORATION PASSED\s*$", elaboration):
        raise RuntimeError("Missing full-case elaboration")
    report = (OUT/"monitor_timing.rpt").read_text(errors="replace")
    summary = report.split("| Design Timing Summary", 1)[1]
    row = re.search(r"(?m)^\s*(-?\d+\.\d+\s+){2}\d+\s+\d+\s+(-?\d+\.\d+\s+){2}\d+\s+\d+\s+(-?\d+\.\d+\s+){2}\d+\s+\d+\s*$", summary)
    if not row: raise RuntimeError("Missing timing summary")
    values = row.group().split()
    timing = dict(wns_ns=float(values[0]), whs_ns=float(values[4]), wpws_ns=float(values[8]))
    if min(timing.values()) < 0: raise RuntimeError("OOC timing failed")
    cdc = (OUT/"monitor_cdc.rpt").read_text(errors="replace")
    cdc_critical = sum(int(n) for n in re.findall(r"(?m)^CDC-\d+\s+Critical\s+(\d+)\s", cdc))
    if cdc_critical: raise RuntimeError("Unreviewed CDC Critical")
    skew = (OUT/"monitor_bus_skew.rpt").read_text(errors="replace")
    if "Slack (MET)" not in skew or "Slack (VIOLATED)" in skew:
        raise RuntimeError("Bus skew failed")
    if "PASS sdi_diagnostics_reader:" not in (OUT/"reader-test.log").read_text(encoding="utf-8-sig"):
        raise RuntimeError("Missing C++ reader test")
    py = (OUT/"decoder-test.log").read_text(encoding="utf-8-sig")
    if "Ran 4 tests" not in py or not re.search(r"(?m)^OK\s*$", py):
        raise RuntimeError("Missing decoder tests")
    mate = Path("rtl/edif/AI_Mate.edif")
    if sha(SOURCE/mate) != sha(ROOT/"case"/mate):
        raise RuntimeError("AI_Mate differs from vendor original")
    fingerprints = {entry["path"]: entry["patched_sha256"] for entry in manifest["patched"]}
    fingerprints.update({entry["path"]: entry["sha256"] for entry in manifest["new_rtl"]})
    result = dict(source_sha256=fingerprints, original_sources_unchanged=True,
                  ai_mate_preserved=True, pins_changed=False, simulation_suites=sorted(expected),
                  cxx_reader_mock_test_passed=True, python_decoder_tests=4,
                  full_case_elaboration_passed=True, monitor_ooc_timing=timing,
                  monitor_cdc_critical=cdc_critical, monitor_cdc_warnings_require_full_design_review=True,
                  full_board_synthesis_and_route_passed=False,
                  bitstream_generated=False, boot_generated=False, boot_deployed=False,
                  hardware_diagnostics_verified=False, root_cause_confirmed=False,
                  board_health=json.loads((OUT/"board-health.json").read_text()),
                  blockers=["reference clock annotation/IP configuration needs vendor verification",
                            "GT clock path compatibility and old full-design pulse width violations unresolved",
                            "new SDI2 full-board physical implementation has not been validated"])
    (OUT/"verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("simulation_suites", "monitor_ooc_timing", "ai_mate_preserved", "boot_deployed", "root_cause_confirmed")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
