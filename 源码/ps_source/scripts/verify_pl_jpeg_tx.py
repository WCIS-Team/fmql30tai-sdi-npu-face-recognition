"""Verify actual TX pin output, including saturation/backpressure and reset."""
from pathlib import Path
import argparse,hashlib,json,os,struct,subprocess,zlib
from verify_pl_jpeg_network import checksum
R=Path(__file__).resolve().parents[1]
def native_simulation(out,files,phy_delay,serdes,receiver_delay,payload_pipe=False):
 # OSERDESE2 delegates to secureip B_OSERDESE2 in Vivado 2018.3.
 # Use the installed simulator/library, never replace it with a local stub.
 source=R/'sim/tb_jpeg_network_tx.sv';bench=source.read_text()
 for before,after in [('parameter TARGET="SIM";','parameter TARGET="XILINX";'),
  ('parameter USE_PHY_TX_DELAY=0;','parameter USE_PHY_TX_DELAY='+str(int(phy_delay))+';'),
  ('parameter USE_SERDES_TX=0;','parameter USE_SERDES_TX='+str(int(serdes))+';'),
  ('parameter USE_PAYLOAD_PIPE=0;','parameter USE_PAYLOAD_PIPE='+str(int(payload_pipe))+';'),
  ('parameter RECEIVER_DELAY_PS=0;','parameter RECEIVER_DELAY_PS='+str(receiver_delay)+';')]:
  assert bench.count(before)==1;bench=bench.replace(before,after)
 snapshot=out/'native_tb.sv';snapshot.write_text(bench)
 actual=[f for f in files if f!=source]+[snapshot,Path('C:/Xilinx/Vivado/2018.3/data/verilog/src/glbl.v')]
 (out/'compile.prj').write_text(''.join('sv xil_defaultlib "'+f.as_posix()+'"\n' for f in actual))
 tools=Path('C:/Xilinx/Vivado/2018.3/bin')
 commands=[('xvlog',[str(tools/'xvlog.bat'),'--relax','--prj','compile.prj']),
  ('xelab',[str(tools/'xelab.bat'),'--relax','--debug','typical','--mt','2','-L','unisims_ver','-L','secureip',
            'xil_defaultlib.tb_jpeg_network_tx','xil_defaultlib.glbl','--snapshot','jpeg_network_tx']),
  ('xsim',[str(tools/'xsim.bat'),'jpeg_network_tx','--runall'])]
 env=os.environ.copy();temp=out/'native-temp';temp.mkdir(exist_ok=True)
 for key in ('TMP','TEMP','TMPDIR','XDG_CACHE_HOME'):env[key]=str(temp)
 for phase,command in commands:
  q=subprocess.Popen(command,cwd=out,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  try:log,_=q.communicate(timeout=60)
  except subprocess.TimeoutExpired:
   subprocess.run(['taskkill','/PID',str(q.pid),'/T','/F'],capture_output=True)
   log,_=q.communicate();(out/(phase+'.log')).write_text(log)
   raise RuntimeError(phase+' exceeded 60 seconds; its own process tree was stopped')
  (out/(phase+'.log')).write_text(log)
  assert q.returncode==0,log[-5000:]
 assert 'PASS jpeg_network_tx' in log,log[-4000:]
 (out/'simulation.log').write_text(log)
 return actual
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
 p.add_argument('--xilinx',action='store_true')
 p.add_argument('--phy-tx-delay',action='store_true',help='Offline same-clock candidate; does not admit board timing')
 p.add_argument('--serdes-tx',action='store_true',help='Offline shared-clock serializer candidate; requires --xilinx')
 p.add_argument('--payload-pipe',action='store_true',help='Exercise the registered packetizer/checksum boundary')
 p.add_argument('--receiver-delay-ps',type=int,help='Behavioral receiver delay only; default 1950 for PHY candidate, otherwise 0')
 a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True)
 if a.serdes_tx and (a.phy_tx_delay or not a.xilinx):p.error('--serdes-tx requires --xilinx and zero PHY-delay ownership')
 receiver_delay=a.receiver_delay_ps if a.receiver_delay_ps is not None else (1950 if a.phy_tx_delay else 0)
 if not 0<=receiver_delay<8000:p.error('behavioral receiver delay must be in [0,8000) ps')
 vendor=R/'rtl/vendor/verilog_ethernet';manifest=json.loads((vendor/'sources.json').read_text())
 for f in manifest['files']:assert hashlib.sha256((vendor/f['path']).read_bytes()).hexdigest()==f['sha256']
 files=[vendor/f['path'] for f in manifest['files'] if f['path'].endswith('.v')]
 files+=[R/'rtl/wcis_jpeg_network_tx.v',R/'rtl/wcis_rgmii_tx_serdes.v',R/'rtl/wcis_udp_payload_pipe.v',R/'sim/tb_jpeg_network_tx.sv']
 extra=['-Ptb_jpeg_network_tx.USE_PHY_TX_DELAY='+str(int(a.phy_tx_delay)),
        '-Ptb_jpeg_network_tx.RECEIVER_DELAY_PS='+str(receiver_delay),
        '-Ptb_jpeg_network_tx.USE_SERDES_TX='+str(int(a.serdes_tx)),
        '-Ptb_jpeg_network_tx.USE_PAYLOAD_PIPE='+str(int(a.payload_pipe))]
 if a.xilinx and not a.serdes_tx:
  models=Path('C:/Xilinx/Vivado/2018.3/data/verilog/src')
  files+=[models/'unisims/ODDR.v',models/'glbl.v'];extra+=['-s','glbl','-Ptb_jpeg_network_tx.TARGET="XILINX"']
 if a.serdes_tx:
  files+=native_simulation(a.out,files,a.phy_tx_delay,True,receiver_delay,a.payload_pipe)
 else:
  command=['iverilog','-g2012','-Wall','-s','tb_jpeg_network_tx',*extra,'-o',str(a.out/'sim.vvp'),*map(str,files)]
  q=subprocess.run(command,capture_output=True,text=True);(a.out/'compile.log').write_text(q.stdout+q.stderr);assert q.returncode==0,q.stderr
  q=subprocess.run(['vvp',str(a.out/'sim.vvp')],cwd=a.out,capture_output=True,text=True,timeout=90)
  (a.out/'simulation.log').write_text(q.stdout+q.stderr);assert q.returncode==0 and 'PASS jpeg_network_tx' in q.stdout,q.stdout+q.stderr
 cases=[(1,1),(17,2),(1440,3),(1472,4)]+[(1472,16+n) for n in range(12)]+[(63,99)]
 outputs=sorted(a.out.glob('ethernet_*.bin'),key=lambda f:int(f.stem.split('_')[-1]));assert len(outputs)==len(cases)
 for index,((length,tag),path) in enumerate(zip(cases,outputs)):
  eth=path.read_bytes();assert eth[:8]==b'\x55'*7+b'\xd5';eth=eth[8:]
  assert zlib.crc32(eth[:-4])==int.from_bytes(eth[-4:],'little');eth=eth[:-4]
  assert eth[:14]==bytes.fromhex('02000000000a' if index==16 else '020000000002')+bytes.fromhex('0257434953020800')
  ip=eth[14:34];assert ip[0]==0x45 and ip[9]==17 and checksum(ip)==0
  assert ip[12:20]==bytes([192,168,1,240,192,168,1,102])
  total=int.from_bytes(ip[2:4],'big');udp=eth[34:14+total]
  assert len(udp)==length+8 and struct.unpack('!HHH',udp[:6])==(5004,5004,length+8)
  assert udp[6:8]!=b'\0\0' and checksum(ip[12:20]+b'\0\x11'+len(udp).to_bytes(2,'big')+udp)==0
  assert udp[8:]==bytes(((n*7)^tag)&255 for n in range(length))
 report=dict(passed=True,frames=len(cases),target='XILINX' if a.xilinx else 'SIM',
  payload_pipe=a.payload_pipe,
  simulator='Vivado 2018.3 xsim native unisims_ver/secureip' if a.serdes_tx else 'iverilog/vvp',
  cases=['invalid next-hop blocked','odd/even and MTU payload','Ethernet FCS','IP and nonzero UDP checksum','exact payload',
         '150-to-125 MHz backpressure','partial UDP reset and new MAC recovery','ideal receiver setup/hold monitor'],
  clock_mode='SHARED_CLOCK_SERDES_CANDIDATE' if a.serdes_tx else ('PHY_DELAY_CANDIDATE' if a.phy_tx_delay else 'MAC_90_DEFAULT'),
  receiver_delay_ps=receiver_delay,nominal_phy_model_only=True,physical_timing_verified=False,board_verified=False,
  verification_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
  source_sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
 (a.out/'summary.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:report[k] for k in ('passed','frames','target')}))
if __name__=='__main__':main()
