"""Prepare a PL preview bit/BOOT candidate only after routed review gates.

This never uploads, replaces a boot partition, or restarts the board.
"""
import argparse,hashlib,json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REFERENCE=Path('D:/yzd/tmp/sdi-refclk-fix-20261020')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def timing_values(path):
    report=path.read_text(errors='replace')
    for line in report[report.index('WNS(ns)'):].splitlines()[1:8]:
        fields=line.split()
        if len(fields)==12:
            try:return list(map(float,fields))
            except ValueError:pass
    raise RuntimeError('Timing summary is missing')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',type=Path,default=Path('D:/yzd/tmp/pl-jpeg-bram-chunk-20261025'))
    args=parser.parse_args();task=args.task.resolve()
    inputs=json.loads((task/'preview-implementation-inputs.json').read_text())
    for name,expected in inputs['inputs'].items():
        if sha(Path(name))!=expected:raise RuntimeError(f'Implementation input changed after launch: {name}')
    staged=json.loads((task/'preview-staging.json').read_text())
    tx_only=staged.get('network_mode')=='TX_ONLY_SERDES_1G_FULL_DUPLEX'
    admin_receipt='school-manager/receipt.json' if tx_only else 'net-admin-build-receipt.json'
    admin_binary='school-manager/wcis_pl_net_config' if tx_only else 'net-admin-wcis_pl_net_config'
    admin=json.loads((task/admin_receipt).read_text())
    if tx_only:
        if (not admin.get('built') or admin.get('exit_code')!=0 or staged.get('phy_extra_tx_delay_ps')!=0
                or sha(ROOT/'npu_photo/src/pl_net_config.cpp')!=admin['manager_source_sha256']):
            raise RuntimeError('Matching NTP2 TX-only manager build required')
    else:
        if admin.get('exit_code')!=0 or admin.get('phy_rx_delay_ps')!=1200:
            raise RuntimeError('Matching PHY configuration build required')
        for name,expected in admin['source_files'].items():
            if sha(ROOT/name)!=expected:raise RuntimeError('PHY configuration source changed after build')
    if sha(task/admin_binary)!=admin['binary_sha256']:
        raise RuntimeError('PHY configuration binary differs from build receipt')
    values=timing_values(task/'preview-timing.rpt')
    baseline=timing_values(REFERENCE/'timing.rpt')
    if values[0]<0 or values[1]!=0 or values[2]!=0 or values[4]<0 or values[5]!=0 or values[6]!=0:
        raise RuntimeError('Setup/hold timing failed; do not generate a candidate')
    if values[8]<baseline[8]-.0001 or values[9]<baseline[9]-.0001 or values[10]>baseline[10]:
        raise RuntimeError('Inherited pulse-period violations worsened')
    route=(task/'preview-route-status.rpt').read_text()
    if not re.search(r'nets with routing errors\.*\s*:\s*0',route):raise RuntimeError('Routing errors remain')
    drc=(task/'preview-drc-audited.rpt').read_text()
    if re.search(r'\|[^\n|]+\|\s*(Error|Critical Warning)\s*\|',drc):raise RuntimeError('DRC failed')
    if re.search(r'(?i)VIOLATED',(task/'preview-bus-skew.rpt').read_text()):raise RuntimeError('Mailbox/Gray-pointer skew failed')
    audit=task/'preview-routed-audit.txt';text=audit.read_text()
    if ('ROUTED_STRUCTURAL_AUDIT_PASS' not in text or text.count('MAILBOX=')!=9
            or 'NPU_PLL_CONFIG_AND_LOC_UNCHANGED=' not in text
            or 'EXISTING_PORT_PIN_STANDARDS_UNCHANGED=' not in text
            or 'DDR_CALIBRATION_CONNECTED=' not in text or 'JPEG_COUNTER_PERIOD=10' not in text
            or (tx_only and (text.count('TX_OUTPUT=')!=10 or text.count('PREVIEW_PATH=')!=4
                             or 'GENERATED_CLOCK_SOURCE_CONNECTED' not in text))
            or (not tx_only and text.count('RX_INPUT=')!=10)):
        raise RuntimeError('Complete routed structural audit required')
    checkpoint=task/'preview-routed.dcp'
    if audit.stat().st_mtime<checkpoint.stat().st_mtime:raise RuntimeError('Routed audit is stale')
    history=(task/'case/fpai_demo_vivado.runs/impl_1/runme.log').read_text(errors='replace')
    runlog=re.split(r'(?m)^\*{6} Vivado v',history)[-1]
    for operation in ('place_design','phys_opt_design','route_design'):
        if f'{operation} completed successfully' not in runlog:raise RuntimeError(f'Incomplete {operation}')
    if re.search(r'ERROR:|CRITICAL WARNING: \[Route 35-341\]|CRITICAL WARNING: \[Place 30-1113\]',runlog):
        raise RuntimeError('Current implementation contains errors or physical conflicts')
    bound={}
    for name,expected in staged['source_sha256'].items():
        source=Path(name);copy=task/'case/rtl/wcis'/source.name
        if sha(source)!=expected or sha(copy)!=expected:raise RuntimeError(f'RTL differs from staging: {source.name}')
        bound[str(source)]=expected
    vendor=ROOT/'rtl/vendor/verilog_ethernet'
    for item in json.loads((vendor/'sources.json').read_text())['files']:
        source=vendor/item['path'];copy=task/'case/rtl/wcis/vendor/verilog_ethernet'/item['path']
        if sha(source)!=item['sha256'] or sha(copy)!=item['sha256']:raise RuntimeError('Pinned Ethernet source changed')
        bound[str(source)]=item['sha256']
    for source in (ROOT/'rtl/vendor/mjpegzero/rtl').glob('*.v'):
        copy=task/'case/rtl/wcis/jpeg_vendor'/source.name
        if sha(source)!=sha(copy):raise RuntimeError('JPEG source changed')
        bound[str(source)]=sha(source)
    xdc='constraints/fmql30tai_pl_ethernet_tx.xdc' if tx_only else 'constraints/fmql30tai_pl_ethernet.xdc'
    for name in (xdc,'constraints/pl_jpeg_preview_cdc.tcl','scripts/assert_pl_udp_payload_cut.tcl',
                 'scripts/release_pl_preview_routes.tcl','scripts/assert_pl_preview_constraints.tcl'):
        bound[str(ROOT/name)]=sha(ROOT/name)
    proofs=['preview-routed.dcp','preview-timing.rpt','preview-route-status.rpt','preview-drc-audited.rpt',
            'preview-bus-skew.rpt','preview-routed-audit.txt','preview-staging.json',
            'case/rtl/ai7030_edif_top.v','case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top_routed.dcp',
            'preview-implementation-inputs.json',admin_receipt,admin_binary]
    gate=dict(passed=True,setup_wns=values[0],hold_whs=values[4],pulse_wns=values[8],
              inherited_npu_pulse_warning=values[10]>0,production_timing_signoff=False,
              files={name:sha(task/name) for name in proofs},rtl_sha256=bound,
              implementation_log_sha256=hashlib.sha256(runlog.encode()).hexdigest(),board_verified=False)
    (task/'preview-timing-gate.json').write_text(json.dumps(gate,indent=2))
    candidate=task/'boot-candidate';candidate.mkdir(exist_ok=True)
    bit=f'''source {ROOT.as_posix()}/scripts/readonly_tool_guard.tcl
open_project {task.as_posix()}/case/fpai_demo_vivado.xpr
if {{![string match {{route_design Complete*}} [get_property STATUS [get_runs impl_1]]]}} {{error "Fresh reviewed routed run required"}}
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {{![string match {{write_bitstream Complete*}} [get_property STATUS [get_runs impl_1]]]}} {{error "Bitstream failed"}}
file copy -force {task.as_posix()}/case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top.bit {task.as_posix()}/preview.bit
close_project
exit
'''
    (task/'generate-preview-bit.tcl').write_text(bit)
    package=(REFERENCE/'package_candidate.tcl').read_text().replace(REFERENCE.as_posix(),task.as_posix())
    package=package.replace('refclk.bit','preview.bit').replace('refclk-disable-icap.bit','preview-disable-icap.bit')
    (candidate/'package.tcl').write_text(package)
    print('Routed gates passed. Candidate scripts prepared; no bit/BOOT generation or board mutation performed.')


if __name__=='__main__':main()
