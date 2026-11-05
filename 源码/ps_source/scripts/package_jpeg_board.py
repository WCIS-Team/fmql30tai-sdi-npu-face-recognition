"""Generate isolated bit/package scripts after timing, CDC and DRC review."""
import hashlib,json,re,subprocess,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TASK=Path('D:/yzd/tmp/pl-jpeg-board-20261016')
def main():
    timing=(TASK/'timing.rpt').read_text()
    header=timing.index('WNS(ns)')
    values=None
    for line in timing[header:].splitlines()[1:8]:
        parts=line.split()
        if len(parts)==12:
            try: values=list(map(float,parts));break
            except ValueError:pass
    if values is None or values[0]<0 or values[1]!=0 or values[4]<0 or values[5]!=0:
        raise RuntimeError('Setup/hold timing gate failed; do not generate/deploy BOOT')
    # The supplied 1 GHz NPU macro already had two -0.409 ns pulse warnings.
    # This prototype does not sign those off or change their clock/constraints.
    if values[8]<-0.4091 or values[10]>2:raise RuntimeError('Pulse violation worsened')
    route=(TASK/'route-status.rpt').read_text()
    if not re.search(r'nets with routing errors\.*\s*:\s*0',route):raise RuntimeError('Routing errors remain')
    drc=(TASK/'drc.rpt').read_text()
    if re.search(r'\|[^\n|]+\|\s*(Error|Critical Warning)\s*\|',drc):raise RuntimeError('DRC gate failed')
    history=(TASK/'case/fpai_demo_vivado.runs/impl_1/runme.log').read_text(errors='replace')
    # Resuming at placement appends another Vivado invocation to runme.log.
    # Keep earlier failed attempts as evidence, but gate the current invocation.
    invocations=re.split(r'(?m)^\*{6} Vivado v',history)
    runlog=invocations[-1]
    if 'Command: route_design' not in runlog and 'Command: phys_opt_design' in runlog:
        if 'phys_opt_design completed successfully' not in runlog:
            raise RuntimeError('Post-route physical optimization incomplete')
        previous=next((x for x in reversed(invocations[:-1])
            if 'Command: route_design' in x and 'route_design completed successfully' in x),'')
        saved_route=(TASK/'postroute-input.log').read_text()
        post_input=json.loads((TASK/'postroute-input.json').read_text())
        routed=TASK/'case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top_routed.dcp'
        # runme appends the next launcher's preamble before its Vivado header.
        # Bind the saved completed invocation and allow only that known suffix.
        suffix=previous[len(saved_route):] if previous.startswith(saved_route) else None
        if (suffix is None or not re.fullmatch(r'\s*(?:\*{3} Running vivado\s+with args [^\n]*\s*)?',suffix) or
            hashlib.sha256(saved_route.encode()).hexdigest()!=post_input['route_log_sha256'] or
            hashlib.sha256(routed.read_bytes()).hexdigest()!=post_input['checkpoint_sha256']):
            raise RuntimeError('Post-route input differs from the completed routing proof')
        if 'route_design completed successfully' not in previous:
            raise RuntimeError('Successful routing proof absent before post-route optimization')
        runlog=saved_route+'\nPOST_ROUTE_PHYSICAL_OPTIMIZATION\n'+runlog
    if 'Command: route_design' not in runlog:
        raise RuntimeError('Current implementation invocation is incomplete')
    if re.search(r'CRITICAL WARNING: \[Route 35-341\]',runlog):
        raise RuntimeError('Fixed routing conflicts with placed pins; do not package')
    placement=runlog
    if 'Command: place_design' not in placement:
        placement=(TASK/'placement-current.log').read_text()
        placement_proof=json.loads((TASK/'placement-proof.json').read_text())
        checkpoint=TASK/'case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top_physopt.dcp'
        if (hashlib.sha256(placement.encode()).hexdigest()!=placement_proof['log_sha256'] or
            hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=placement_proof['checkpoint_sha256']):
            raise RuntimeError('Resumed physical checkpoint differs from its placement proof')
    if 'place_design completed successfully' not in placement or 'phys_opt_design completed successfully' not in placement:
        raise RuntimeError('Successful placement and physical optimization proof absent')
    if re.search(r'CRITICAL WARNING: \[Place 30-1113\]|ERROR: \[Place',placement):
        raise RuntimeError('Calibration/placement gate failed; do not package an unconnected IDELAYCTRL')
    # Explicitly fail on reported skew violations, not on a generic INFO line.
    skew=(TASK/'bus-skew.rpt').read_text()
    if re.search(r'(?i)VIOLATED',skew):raise RuntimeError('Bundled-data bus skew violated')
    audit=(TASK/'mailbox-audit.txt').read_text()
    if audit.count('SLACK=')!=6 or 'JPEG_COUNTER_CLOCK=' not in audit:raise RuntimeError('Routed mailbox/clock audit absent')
    if not re.search(r'CALIBRATION_INPUTS_CONNECTED=[1-9][0-9]* controllers',audit):
        raise RuntimeError('Routed DDR calibration input audit absent')
    out=TASK/'boot-candidate';out.mkdir(exist_ok=True)
    bit_tcl=f'''source {ROOT.as_posix()}/scripts/readonly_tool_guard.tcl
open_project {TASK.as_posix()}/case/fpai_demo_vivado.xpr
set task_status [get_property STATUS [get_runs impl_1]]
if {{![string match {{route_design Complete*}} $task_status] && ![string match {{phys_opt_design (Post-Route) Complete*}} $task_status]}} {{error "Fresh routed run required"}}
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {{![string match {{write_bitstream Complete*}} [get_property STATUS [get_runs impl_1]]]}} {{error "Bitstream failed"}}
close_project
exit
'''
    (TASK/'generate-bit.tcl').write_text(bit_tcl)
    reference=Path('D:/yzd/tmp/face-emmc-store-20261015/boot-candidate/package.tcl').read_text()
    reference=reference.replace('D:/yzd/tmp/face-emmc-store-20261015',TASK.as_posix())
    (out/'package.tcl').write_text(reference)
    (TASK/'timing-gate.json').write_text(json.dumps(dict(setup_wns=values[0],hold_whs=values[4],pulse_wns=values[8],
        inherited_npu_pulse_warning=True,production_timing_signoff=False,case_directory=str(TASK/'case'),
        implementation_log_sha256=hashlib.sha256(runlog.encode()).hexdigest(),
        placement_log_sha256=hashlib.sha256(placement.encode()).hexdigest()),indent=2))
    (TASK/'implementation-current.log').write_text(runlog)
    print('Setup/hold/routing/DRC/skew gates passed; scripts prepared; no board changed.')
if __name__=='__main__':main()
