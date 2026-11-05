"""Use installed native primitives, with bounded task-owned simulator processes."""
from pathlib import Path
import os,hashlib,json
import subprocess

def run_native(out, files, source, bench, top, passed, plusargs=(), simulation_timeout=120):
    snapshot=out/'native_tb.sv'
    snapshot.write_text(bench)
    actual=[f for f in files if f!=source]+[snapshot,Path('C:/Xilinx/Vivado/2018.3/data/verilog/src/glbl.v')]
    compiled_inputs={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in actual}
    (out/'compiled-inputs.json').write_text(json.dumps(compiled_inputs,indent=2))
    (out/'compile.prj').write_text(''.join('sv xil_defaultlib "'+f.as_posix()+'"\n' for f in actual))
    tools=Path('C:/Xilinx/Vivado/2018.3/bin')
    commands=[('xvlog',[str(tools/'xvlog.bat'),'--relax','--prj','compile.prj']),
      ('xelab',[str(tools/'xelab.bat'),'--relax','--debug','typical','--mt','2','-L','unisims_ver','-L','secureip',
                'xil_defaultlib.'+top,'xil_defaultlib.glbl','--snapshot','preview_pipeline']),
      ('xsim',[str(tools/'xsim.bat'),'preview_pipeline','--runall',*sum((['--testplusarg',s] for s in plusargs),[])])]
    env=os.environ.copy();temp=out/'native-temp';temp.mkdir(exist_ok=True)
    for key in ('TMP','TEMP','TMPDIR','XDG_CACHE_HOME'):env[key]=str(temp)
    for phase,command in commands:
        timeout=simulation_timeout if phase=='xsim' else 120
        q=subprocess.Popen(command,cwd=out,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:log,_=q.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill','/PID',str(q.pid),'/T','/F'],capture_output=True)
            log,_=q.communicate();(out/(phase+'.log')).write_text(log)
            raise RuntimeError(phase+f' exceeded {timeout} seconds; its own process tree was stopped')
        (out/(phase+'.log')).write_text(log)
        if q.returncode:raise RuntimeError(log[-5000:])
    (out/'simulation.log').write_text(log)
    if passed not in log:raise RuntimeError('Native simulation did not reach its PASS condition: '+log[-4000:])
    if any(hashlib.sha256(Path(f).read_bytes()).hexdigest()!=digest for f,digest in compiled_inputs.items()):
        raise RuntimeError('An HDL input changed during native compilation or simulation')
    return actual
