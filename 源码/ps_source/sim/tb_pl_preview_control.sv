`timescale 1ns/1ps
module tb_pl_preview_control;
 reg hp_clk=0,gp_clk=0,reset=1;
 always #2.5 hp_clk=~hp_clk;
 always #5 gp_clk=~gp_clk;
 reg [31:0] awaddr=0,awdata=0;reg awvalid=0;
 reg [31:0] araddr=0;reg arvalid=0;wire arready,rvalid;wire [31:0] rdata;
 wire awready,phy_reset_n;
 wcis_pl_jpeg_preview dut(
  .hp_clk(hp_clk),.gp_clk(gp_clk),.reset(reset),.cam_clk(hp_clk),.cam_locked(1'b1),
  .cam_vsync(1'b0),.cam_de(1'b0),.cam_rgb(24'd0),
  .awaddr(awaddr),.awdata(awdata),.awvalid(awvalid),.awready(awready),
  .araddr(araddr),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rvalid(rvalid),.rready(1'b1),
  .legacy_awvalid(),.legacy_arvalid(),.legacy_rready(),.legacy_awready(1'b1),
  .legacy_arready(1'b1),.legacy_rvalid(1'b0),.legacy_rdata(32'd0),
  .phy_tx_clk(),.phy_tx_ctl(),.phy_txd(),
  .phy_reset_n(phy_reset_n),.phy_mdc(),.phy_mdio_out(),.phy_mdio_tristate(),.phy_mdio_in(1'b1));
 task write_reg(input [7:0] address,input [31:0] value);
  begin
   @(negedge gp_clk);awaddr=32'h2200|address;awdata=value;awvalid=1;
   @(posedge gp_clk);if(!awready)$fatal(1,"CSR write stalled");
   @(negedge gp_clk);awvalid=0;
  end
 endtask
 task expect_reg(input [7:0] address,input [31:0] expected);
  begin
   @(negedge gp_clk);araddr=32'h2200|address;arvalid=1;
   @(posedge gp_clk);if(!arready)$fatal(1,"CSR read stalled");
   @(negedge gp_clk);arvalid=0;
   if(!rvalid||rdata!==expected)$fatal(1,"CSR identity/readback mismatch %x: got %x expected %x",address,rdata,expected);
   @(posedge gp_clk);
  end
 endtask
 task configure(input [31:0] session);
  begin
   write_reg('h0c,session);write_reg('h10,32'h43495301);write_reg('h14,32'h0257);
   write_reg('h18,32'hc0a801f0);write_reg('h1c,32'hc0a80166);
   write_reg('h20,32'hc0a80101);write_reg('h24,32'hffffff00);write_reg('h28,32'h13881388);
   write_reg('h38,1);
   write_reg('h60,session);write_reg('h64,32'h0200);
  end
 endtask
 task active(input [31:0] session);
  begin
   wait(dut.network_enabled===1'b1);repeat(5)@(posedge dut.net_clk);#1;
   if(dut.common_reset||dut.net_session!==session||dut.net_mac!==48'h025743495301||
      dut.net_local_ip!==32'hc0a801f0||dut.net_destination_ip!==32'hc0a80166||
      dut.net_source_port!==5000||dut.net_destination_port!==5000||dut.net_next_hop_mac!=={16'h0200,session})
    $fatal(1,"Atomic configuration/enable mismatch for session %0d",session);
  end
 endtask
 task pulse_reset(input integer phase);
  begin
   #(0.137*phase+1.111);reset=1;#0.01;
   if(!dut.common_reset)$fatal(1,"Reset did not immediately isolate stream");
   repeat(4)@(negedge gp_clk);#1.173;reset=0;
   repeat(18)@(posedge dut.net_clk);#1;
   if(dut.network_enabled!==0||dut.enabled!==0||phy_reset_n!==0||!dut.common_reset)
    $fatal(1,"Reset retained previous software/network state");
  end
 endtask
 integer i;
 initial begin
  repeat(5)@(negedge gp_clk);#1.117;reset=0;
  repeat(20)@(posedge gp_clk);
  if(phy_reset_n!==0||dut.network_enabled!==0)$fatal(1,"Unsafe initial state");
  expect_reg(0,32'h4e545032);expect_reg('h5c,7);expect_reg('h54,1920);expect_reg('h58,1080);
  write_reg(4,1);repeat(10)@(posedge dut.net_clk);
  if(dut.enabled!==0)$fatal(1,"Incomplete configuration admitted");
  configure(42);write_reg('h60,0);write_reg('h64,0);write_reg(4,1);
  repeat(10)@(posedge dut.net_clk);
  if(dut.enabled!==0)$fatal(1,"Zero next-hop MAC admitted");
  write_reg('h64,32'h0300);write_reg(4,1);repeat(10)@(posedge dut.net_clk);
  if(dut.enabled!==0)$fatal(1,"Multicast next-hop MAC admitted");
  for(i=1;i<=12;i=i+1)begin
   configure(i);write_reg(4,1);active(i);
   write_reg('h60,32'hdeadbeef);repeat(4)@(posedge dut.net_clk);
   if(dut.net_next_hop_mac!=={16'h0200,32'(i)}||dut.next_hop_mac!=={16'h0200,32'(i)})
    $fatal(1,"Active next-hop was not frozen");
   expect_reg('h60,i);
   write_reg(4,0);#0.01;if(!dut.common_reset)$fatal(1,"Disable did not isolate stream");
   // Reconfigure immediately, while the prior mailbox acknowledgement may
   // still be crossing. No old session may become active after re-enable.
   configure(i+100);write_reg(4,1);active(i+100);
   pulse_reset(i);
   configure(i+200);write_reg(4,1);
   // Cancel a newly sent configuration before its mailbox round trip ends.
   #0.317;reset=1;repeat(4)@(negedge gp_clk);#1.019;reset=0;
   repeat(20)@(posedge dut.net_clk);#1;
   if(dut.network_enabled!==0||!dut.common_reset)$fatal(1,"Cancelled configuration revived");
  end
  $display("PASS preview control: 12 phase offsets, default disabled, atomic config, disable/re-enable, active and in-flight reset");
  $finish;
 end
 initial begin #100000;$fatal(1,"Control deadline");end
endmodule

// Clock-only and datapath-only stubs. This test covers the real top-level
// control, CSR, mailbox and packetizer; it does not validate a PLL or PHY.
module BUFG(input I,output O);assign O=I;endmodule
module PLLE2_BASE #(parameter BANDWIDTH="OPTIMIZED",CLKIN1_PERIOD=5.0,DIVCLK_DIVIDE=2,
 CLKFBOUT_MULT=15,CLKOUT0_DIVIDE=10,CLKOUT1_DIVIDE=12,CLKOUT2_DIVIDE=12,CLKOUT2_PHASE=90.0)(
 input CLKIN1,RST,PWRDWN,CLKFBIN,output CLKFBOUT,output reg CLKOUT0=0,CLKOUT1=0,CLKOUT2=0,LOCKED=0);
 integer lock_count=0;
 assign CLKFBOUT=CLKIN1;
 always #3.333 CLKOUT0=~CLKOUT0;
 always #4 CLKOUT1=~CLKOUT1;
 initial begin #2;forever #4 CLKOUT2=~CLKOUT2;end
 always @(posedge CLKIN1 or posedge RST)
  if(RST)begin LOCKED<=0;lock_count<=0;end
  else if(lock_count<8)lock_count<=lock_count+1;else LOCKED<=1;
endmodule
module wcis_sdi_jpeg_stream #(parameter LOGIC_HZ=150000000)(
 input cam_clk,clk,reset,enable,cam_locked,cam_vsync,cam_de,input [23:0] cam_rgb,
 output [7:0] m_data,output m_valid,m_sof,m_last,input m_ready,downstream_idle,
 output [31:0] m_frame_id,output abort_frame,output [31:0] frames_encoded,frames_rejected);
 assign {m_data,m_valid,m_sof,m_last,m_frame_id,abort_frame,frames_encoded,frames_rejected}=0;
endmodule
module wcis_jpeg_network_tx #(parameter TARGET="XILINX",USE_SERDES_TX=1)(
 input clk,reset,gtx_clk,gtx_clk90,gtx_clk250,gtx_reset,input [47:0] local_mac,next_hop_mac,
 input [31:0] local_ip,destination_ip,input [15:0] source_port,destination_port,
 input s_hdr_valid,output s_hdr_ready,input [15:0] s_udp_length,input [7:0] s_data,
 input s_valid,output s_ready,input s_last,
 output rgmii_tx_clk,output [3:0] rgmii_txd,output rgmii_tx_ctl,
 output configuration_error,tx_underflow,packet_error);
 assign {rgmii_tx_clk,rgmii_txd,rgmii_tx_ctl,configuration_error,tx_underflow,packet_error}=0;
 assign s_hdr_ready=1;assign s_ready=1;
endmodule
