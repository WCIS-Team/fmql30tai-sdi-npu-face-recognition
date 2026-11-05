`timescale 1ns/1ps
module tb_jpeg_network_tx;
 parameter TARGET="SIM";
 parameter USE_PHY_TX_DELAY=0;
 parameter USE_SERDES_TX=0;
 parameter USE_PAYLOAD_PIPE=0;
 // A behavioral sampling delay, NOT a PHY PVT guarantee or a board setting.
 parameter RECEIVER_DELAY_PS=0;
 reg clk=0;always #3.333 clk=~clk;
 reg gtx_clk=0;always #4 gtx_clk=~gtx_clk;
 reg gtx_clk250=0;initial begin #2;forever #2 gtx_clk250=~gtx_clk250;end
 reg gtx_clk90=0;initial begin #2;forever #4 gtx_clk90=~gtx_clk90;end
 reg reset=0,gtx_reset=0;
 reg [47:0] local_mac=48'h025743495302,next_hop_mac=48'h020000000002;
 reg [31:0] local_ip=32'hc0a801f0,destination_ip=32'hc0a80166;
 reg [15:0] source_port=5004,destination_port=5004,s_udp_length=0;
 reg s_hdr_valid=0,s_valid=0,s_last=0;reg [7:0] s_data=0;
 wire s_hdr_ready,s_ready,rgmii_tx_clk,rgmii_tx_ctl,tx_underflow,packet_error,configuration_error;
 wire [3:0] rgmii_txd;
 wire [7:0] network_data;wire network_valid,network_last,network_ready;
 generate if(USE_PAYLOAD_PIPE)begin: piped_input
  wcis_udp_payload_pipe payload_pipe(.clk(clk),.reset(reset),
   .s_data(s_data),.s_valid(s_valid),.s_last(s_last),.s_ready(s_ready),
   .m_data(network_data),.m_valid(network_valid),.m_last(network_last),.m_ready(network_ready));
 end else begin: direct_input
  assign network_data=s_data;assign network_valid=s_valid;assign network_last=s_last;assign s_ready=network_ready;
 end endgenerate
 wcis_jpeg_network_tx #(.TARGET(TARGET),.USE_PHY_TX_DELAY(USE_PHY_TX_DELAY),.USE_SERDES_TX(USE_SERDES_TX)) dut(
  .s_data(network_data),.s_valid(network_valid),.s_last(network_last),.s_ready(network_ready),.*);
 wire receiver_clock;
 assign #(RECEIVER_DELAY_PS/1000.0) receiver_clock=rgmii_tx_clk;
 integer frame_count=0,output_file=0,index;
 integer stalls=0;
 reg [3:0] lower;reg valid_lower;string filename;
 // Check an ideal >=1 ns stable window on both sides of every active sample.
 // Pin propagation/PVT and analog PHY delay are absent from this model.
 realtime last_pin_change=-1000.0,last_receiver_sample=-1000.0;
 reg receiver_active=0;
 always @(rgmii_txd or rgmii_tx_ctl)begin
  if(!reset&&!gtx_reset&&receiver_active&&($realtime-last_receiver_sample<1.0))
   $fatal(1,"Receiver model hold window violated");
  last_pin_change=$realtime;
 end
 always @(posedge reset or posedge gtx_reset)receiver_active=0;
 task check_receiver_window;
  begin
   if(!reset&&!gtx_reset&&(rgmii_tx_ctl||valid_lower))begin
    if($realtime-last_pin_change<1.0)$fatal(1,"Receiver model setup window violated");
    receiver_active=1;last_receiver_sample=$realtime;
   end else receiver_active=0;
  end
 endtask
 always @(posedge clk)begin
  if(s_valid&&!s_ready)stalls<=stalls+1;
  if(!reset && (packet_error||tx_underflow))$fatal(1,"TX error");
 end
 always @(posedge receiver_clock)begin check_receiver_window;lower=rgmii_txd;valid_lower=rgmii_tx_ctl;end
 always @(negedge receiver_clock)begin
  check_receiver_window;
  if(valid_lower)begin
   if(!rgmii_tx_ctl)$fatal(1,"RGMII error");
   if(!output_file)begin
    filename=$sformatf("ethernet_%0d.bin",frame_count);
    output_file=$fopen(filename,"wb");if(!output_file)$fatal(1,"Capture open");
   end
   $fwrite(output_file,"%c",{rgmii_txd,lower});
  end else if(output_file)begin
   $fclose(output_file);output_file=0;frame_count=frame_count+1;
  end
 end
 task send_packet(input integer length,input integer tag);
  integer n;
  begin
   @(negedge clk);s_udp_length=length+8;s_hdr_valid=1;
   @(posedge clk);while(!s_hdr_ready)@(posedge clk);
   @(negedge clk);s_hdr_valid=0;
   for(n=0;n<length;n=n+1)begin
    s_data=(n*7)^tag;s_valid=1;s_last=(n==length-1);
    @(posedge clk);while(!s_ready)@(posedge clk);
    @(negedge clk);
   end
   s_valid=0;s_last=0;
  end
 endtask
 initial begin
  #20;@(negedge clk);reset=1;gtx_reset=1;
  #100;@(negedge clk);reset=0;gtx_reset=0;
  repeat(25)@(negedge clk);
  // Invalid next-hop configurations must not accept a packet header.
  next_hop_mac=0;s_hdr_valid=1;s_udp_length=20;
  repeat(12)begin @(negedge clk);if(s_hdr_ready||!configuration_error)$fatal(1,"Zero MAC accepted");end
  next_hop_mac=48'hffffffffffff;
  repeat(12)begin @(negedge clk);if(s_hdr_ready||!configuration_error)$fatal(1,"Broadcast MAC accepted");end
  s_hdr_valid=0;next_hop_mac=48'h020000000002;
  send_packet(1,1);send_packet(17,2);send_packet(1440,3);send_packet(1472,4);
  // Enough back-to-back traffic to fill the complete-frame FIFO and exercise
  // backpressure at 150 MHz producer / 125 MHz physical output.
  for(index=0;index<12;index=index+1)send_packet(1472,16+index);
  wait(frame_count==16);repeat(50)@(negedge clk);
  // Cancel a partially submitted UDP frame, then prove clean recovery.
  s_udp_length=1008;s_hdr_valid=1;
  @(posedge clk);while(!s_hdr_ready)@(posedge clk);
  @(negedge clk);s_hdr_valid=0;s_valid=1;s_data=8'hff;
  repeat(20)@(negedge clk);
  reset=1;gtx_reset=1;s_valid=0;s_last=0;
  repeat(20)@(negedge clk);
  reset=0;gtx_reset=0;repeat(25)@(negedge clk);
  next_hop_mac=48'h02000000000a;
  send_packet(63,99);wait(frame_count==17);repeat(30)@(negedge clk);
  if(stalls==0)$fatal(1,"Backpressure was not exercised");
  $display("PASS jpeg_network_tx frames=%0d stalls=%0d target=%s phy_delay_owner=%0d receiver_delay_ps=%0d",frame_count,stalls,TARGET,USE_PHY_TX_DELAY,RECEIVER_DELAY_PS);$finish;
 end
 initial begin #1000000;$fatal(1,"TX deadline frames=%0d",frame_count);end
endmodule
