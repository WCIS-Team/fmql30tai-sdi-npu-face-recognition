"""Collect saved verification evidence; never launch tools or access a board."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/rtl-rewrite-20261013"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timing(path):
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    summary = text.split("| Design Timing Summary", 1)[1]
    match = re.search(r"(?m)^\s*(-?\d+\.\d+\s+){2}\d+\s+\d+\s+(-?\d+\.\d+\s+){2}\d+\s+\d+\s+(-?\d+\.\d+\s+){2}\d+\s+\d+\s*$", summary)
    if not match:
        raise RuntimeError(f"No timing summary in {path}")
    values = match.group().split()
    return dict(wns_ns=float(values[0]), tns_ns=float(values[1]),
                setup_failing_endpoints=int(values[2]), whs_ns=float(values[4]),
                hold_failing_endpoints=int(values[6]), wpws_ns=float(values[8]),
                pulse_failing_endpoints=int(values[10]))


def main():
    spec = importlib.util.spec_from_file_location("integration", ROOT / "scripts/integrate_case.py")
    integration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(integration)
    manifest_path = ROOT / "docs/source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if "sdi_diagnostics" in manifest:
        raise RuntimeError("SDI2 source changed: old 20261013 timing evidence cannot validate this design. Use the SDI2 verification record.")
    # Original reference sources must still match the recorded hashes.
    for entry in manifest["patched"]:
        rel = Path(entry["path"])
        if sha(integration.SOURCE / rel) != entry["original_sha256"]:
            raise RuntimeError(f"Vendor original changed: {rel}")
        entry["patched_sha256"] = sha(integration.CASE / rel)
    if (ROOT / "rtl/wcis_vtc.v").read_bytes() != (integration.CASE / "rtl/display/vtc.v").read_bytes():
        raise RuntimeError("VTC delivery and actual case copy differ")
    for entry in manifest["new_rtl"]:
        entry["sha256"] = sha(ROOT / entry["path"])
    original = integration.read_vendor(integration.SOURCE / "rtl/display/vtc.v")
    oracle = (ROOT / "sim/vtc_vendor_reference.v").read_text(encoding="utf-8-sig")
    def logic(text):
        return "".join(re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", "", text).split())
    if logic(original.replace("module vtc(", "module vtc_vendor_reference(")) != logic(oracle):
        raise RuntimeError("Oracle is not the unchanged vendor VTC logic")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    # Refresh the review patch after comment-only documentation changes.
    import difflib
    patch = "".join("".join(difflib.unified_diff(
        integration.read_vendor(integration.SOURCE / Path(entry["path"])).splitlines(keepends=True),
        (integration.CASE / Path(entry["path"])).read_text(encoding="utf-8").splitlines(keepends=True),
        fromfile="original/"+Path(entry["path"]).as_posix(),
        tofile="case/"+Path(entry["path"]).as_posix())) for entry in manifest["patched"])
    (ROOT / "docs/case_changes.patch").write_text(patch, encoding="utf-8")
    suites = json.loads((ROOT / "outputs/sim/summary.json").read_text(encoding="utf-8-sig"))
    expected = {"vtc_pipeline", "vtc_resize_chain", "frame_rate_gate", "stream_letterbox", "case_registers", "case_resize"}
    if {s["suite"] for s in suites["suites"] if s["passed"]} != expected:
        raise RuntimeError("Missing passing simulation suite")
    for suite in expected:
        if "PASS " not in (ROOT / "outputs/sim" / (suite+".log")).read_text(encoding="utf-8-sig", errors="replace"):
            raise RuntimeError(f"Missing PASS evidence: {suite}")
    initial = timing(OUT / "timing.rpt")
    refined = OUT / "refined_timing.rpt"
    cleaned = OUT / "cleaned_timing.rpt"
    full = timing(cleaned) if cleaned.exists() else timing(refined) if refined.exists() else initial
    route_path = OUT / ("cleaned_route_status.rpt" if cleaned.exists() else "refined_route_status.rpt" if refined.exists() else "route_status.rpt")
    route_text = route_path.read_text(encoding="utf-8-sig", errors="replace")
    route_match = re.search(r"# of nets with routing errors\.+\s*:\s*(\d+)", route_text)
    if not route_match:
        raise RuntimeError("No routing-error count in route report")
    routing_errors = int(route_match.group(1))
    drc_errors = []
    bus_skew = None
    if cleaned.exists():
        drc_text = (OUT / "cleaned_drc.rpt").read_text(encoding="utf-8-sig", errors="replace")
        drc_errors = re.findall(r"\|\s*(\S+)\s*\|\s*Error\s*\|", drc_text)
        skew_text = (OUT / "cleaned_bus_skew.rpt").read_text(encoding="utf-8-sig", errors="replace")
        skew_values = re.findall(r"Slack \((MET|VIOLATED)\)\s*:\s*(-?\d+\.\d+)ns", skew_text)
        if not skew_values:
            raise RuntimeError("No bus skew paths reported")
        bus_skew = dict(constraints_reported=len(skew_values),
                        failing_constraints=sum(status == "VIOLATED" for status, _ in skew_values),
                        worst_slack_ns=min(float(slack) for _, slack in skew_values))
    record = dict(before=timing(OUT / "before_ai7030_edif_top_timing_summary_routed.rpt"),
                  isolated_vtc=timing(ROOT / "outputs/vtc-rewrite/timing.rpt"),
                  after=full, initial_rewritten_route=initial,
                  post_route_refinement_finished=refined.exists(),
                  targeted_route_cleanup_finished=cleaned.exists(),
                  simulation_suites=sorted(expected),
                  rtl_sha256=sha(ROOT / "rtl/wcis_vtc.v"),
                  vendor_original_unchanged=True, vendor_oracle_logic_unchanged=True,
                  routing_error_nets=routing_errors,
                  standalone_drc_error_rules=drc_errors, bus_skew=bus_skew,
                  full_timing_passed=(full["wns_ns"] >= 0 and full["whs_ns"] >= 0 and full["wpws_ns"] >= 0),
                  release_accepted=False,
                  new_bitstream_generated=False, board_accessed=False, new_face_models_integrated=False)
    (OUT / "verification.json").write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
