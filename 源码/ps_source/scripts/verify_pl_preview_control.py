"""Bounded preview control regression, with clock/datapath stubs documented in TB."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / 'tmp'
    temporary.mkdir(exist_ok=True)
    environment = os.environ.copy()
    environment.update(TMP=str(temporary), TEMP=str(temporary), TMPDIR=str(temporary))
    compiler, runtime = shutil.which('iverilog'), shutil.which('vvp')
    if not compiler or not runtime:
        raise RuntimeError('Icarus and vvp are required for this RTL control test')
    sources = [ROOT / 'sim/tb_pl_preview_control.sv'] + [ROOT / ('rtl/' + name + '.v') for name in (
        'wcis_pl_jpeg_preview', 'wcis_cdc_mailbox', 'wcis_preview_csr_router',
        'wcis_preview_registers', 'wcis_mdio_clause22', 'wcis_jpeg_udp_packetizer','wcis_udp_payload_pipe','wcis_status_sync')]
    sources += [ROOT/'rtl/vendor/verilog_ethernet/axis/rtl/axis_fifo.v']
    sources += [ROOT/'rtl/vendor/verilog_ethernet/axis/rtl/sync_reset.v']
    image = output / 'control.vvp'
    result = subprocess.run([compiler, '-g2012', '-s', 'tb_pl_preview_control', '-o', str(image),
        *map(str, sources)], env=environment, capture_output=True, text=True, timeout=30)
    (output / 'compile.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('Control compilation failed; see compile.log')
    result = subprocess.run([runtime, str(image)], env=environment, capture_output=True, text=True, timeout=30)
    console = result.stdout + result.stderr
    (output / 'simulation.log').write_text(console)
    passed = result.returncode == 0 and 'PASS preview control: 12 phase offsets' in console
    report = dict(passed=passed, phase_offsets=12, scope='CSR/mailbox/top control; PLL/stream/PHY are stubs',
        source_sha256={path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        board_verified=False)
    (output / 'summary.json').write_text(json.dumps(report, indent=2))
    print(console, end='')
    if not passed:
        raise RuntimeError('Control regression failed; see simulation.log')


if __name__ == '__main__':
    main()
