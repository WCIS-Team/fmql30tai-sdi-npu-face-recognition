"""Check real-wrapper fairness, stall retention and response ownership."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve()
    if not out.is_relative_to(Path('D:/yzd/tmp').resolve()):raise ValueError('Use private task output')
    if a.baseline.resolve()==(ROOT/'rtl/wcis_recording_customop.v').resolve():raise ValueError('Baseline must be immutable copy')
    out.mkdir(parents=True,exist_ok=True);records=[]
    for name,source,fair,original in [('old_priority',a.baseline,0,True),('round_robin',ROOT/'rtl/wcis_recording_customop.v',1,False),('compat_priority',ROOT/'rtl/wcis_recording_customop.v',0,False)]:
        binary=out/(name+'.vvp')
        command=['C:/msys64/ucrt64/bin/iverilog.exe','-g2012','-Wall','-s','tb_recording_arbiter','-Ptb_recording_arbiter.FAIR='+str(fair),'-o',str(binary)]
        if original:command+=['-DORIGINAL_PRIORITY']
        command+=[str(source),str(ROOT/'sim/recording_arbiter_clients.sv'),str(ROOT/'sim/tb_recording_arbiter.sv')]
        done=subprocess.run(command,capture_output=True,text=True);(out/(name+'-compile.log')).write_text(done.stdout+done.stderr)
        if done.returncode:raise RuntimeError(done.stderr)
        done=subprocess.run(['C:/msys64/ucrt64/bin/vvp.exe',str(binary)],capture_output=True,text=True,timeout=30)
        (out/(name+'-simulation.log')).write_text(done.stdout+done.stderr)
        if done.returncode or 'PASS recording_arbiter' not in done.stdout:raise RuntimeError(done.stdout+done.stderr)
        records.append(dict(name=name,passed=True,output=done.stdout.strip(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
        print(name,done.stdout.strip(),flush=True)
    (out/'verification.json').write_text(json.dumps(dict(passed=True,scope='Actual wrapper with test-only saturated clients; no board deployment',cases=records),indent=2))


if __name__=='__main__':main()
