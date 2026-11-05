"""Run the actual camera/JPEG/packetizer/TX-only pipeline at bounded size."""
from pathlib import Path
import argparse,hashlib,json,subprocess
from verify_pl_preview_pipeline import check_capture
from native_xilinx_sim import run_native
R=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
 p.add_argument('--width',type=int,default=256);p.add_argument('--height',type=int,default=64)
 p.add_argument('--frames',type=int,default=3,help='Camera frames to generate; one frame checks geometry, multiple frames also exercise overlap')
 p.add_argument('--noise',action='store_true');p.add_argument('--check-only',action='store_true')
 p.add_argument('--simulation-timeout',type=int,default=120,help='Bounded native simulation wall time in seconds')
 p.add_argument('--xsim-functional',action='store_true',help='Use compiled Xsim with the existing behavioral DDR output model; not native SERDES verification')
 p.add_argument('--serdes-tx',action='store_true',help='Use native Xilinx serializer primitives');a=p.parse_args()
 a.out=a.out.resolve()
 a.out.mkdir(parents=True,exist_ok=True)
 if a.frames<1 or a.simulation_timeout<=0:raise ValueError('Frames and simulation timeout must be positive')
 if a.serdes_tx and a.xsim_functional:raise ValueError('Choose native SERDES or functional PHY mode')
 v=R/'rtl/vendor/verilog_ethernet';manifest=json.loads((v/'sources.json').read_text())
 files=[v/f['path'] for f in manifest['files'] if f['path'].endswith('.v')]
 files+=list((R/'rtl/vendor/mjpegzero/rtl').glob('*.v'))
 files+=[R/f'rtl/{n}.v' for n in ('wcis_cdc_mailbox','wcis_jpeg_compressor','wcis_sdi_jpeg_stream','wcis_jpeg_udp_packetizer','wcis_jpeg_network_tx','wcis_rgmii_tx_serdes','wcis_udp_payload_pipe')]
 files+=[R/'sim/tb_pl_preview_pipeline_tx.sv']
 if not a.check_only:
  (a.out/'simulation-config.json').write_text(json.dumps(dict(width=a.width,height=a.height,frames=a.frames,native_serdes=a.serdes_tx,simulator='xsim' if a.serdes_tx or a.xsim_functional else 'iverilog',phy_model='native_serdes' if a.serdes_tx else 'behavioral_ddr',simulation_timeout_seconds=a.simulation_timeout),indent=2))
  if a.serdes_tx or a.xsim_functional:
   source=R/'sim/tb_pl_preview_pipeline_tx.sv';bench=source.read_text()
   if a.serdes_tx:bench=bench.replace('parameter TARGET="SIM",USE_SERDES_TX=0;','parameter TARGET="XILINX",USE_SERDES_TX=1;')
   bench=bench.replace('parameter integer W=64,H=16,',f'parameter integer W={a.width},H={a.height},')
   bench=bench.replace('FRAMES=3;',f'FRAMES={a.frames};')
   if a.xsim_functional:
    bench=bench.replace('endmodule','''initial begin
        forever begin
            #5000000000.0;
            $fflush(capture);
            $display("PROGRESS simulated_ps=%0t JPEG=%0d rejected=%0d UDP=%0d",$time,jpeg_frames,rejected_frames,udp_packets);
            $fflush();
        end
    end
endmodule''')
   files=run_native(a.out,files,source,bench,'tb_pl_preview_pipeline_tx','PASS pipeline',['NOISE'] if a.noise else [],simulation_timeout=a.simulation_timeout)
  else:
   (a.out/'source-hashes.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},indent=2))
   cmd=['iverilog','-g2012','-s','tb_pl_preview_pipeline_tx',f'-Ptb_pl_preview_pipeline_tx.W={a.width}',f'-Ptb_pl_preview_pipeline_tx.H={a.height}',f'-Ptb_pl_preview_pipeline_tx.FRAMES={a.frames}',
        '-o',str(a.out/'sim.vvp'),*map(str,files)]
   (a.out/'compile-command.json').write_text(json.dumps(cmd,indent=2))
   q=subprocess.run(cmd,capture_output=True,text=True,timeout=30);(a.out/'compile.log').write_text(q.stdout+q.stderr);assert q.returncode==0,q.stderr
   q=subprocess.run(['vvp',str(a.out/'sim.vvp')]+(['+NOISE'] if a.noise else []),cwd=a.out,capture_output=True,text=True,timeout=a.simulation_timeout)
   (a.out/'simulation.log').write_text(q.stdout+q.stderr);assert q.returncode==0 and 'PASS pipeline' in q.stdout,q.stdout+q.stderr
  (a.out/'source-hashes.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},indent=2))
 result=check_capture(a.out,a.width,a.height,tx_only=True)
 print(json.dumps({k:result[k] for k in ('passed','geometry','udp_packets','arp_packets')}))
if __name__=='__main__':main()
