`timescale 1ns/1ps
// Port-level invariants for coordinate-tag cache hits and the checked miss path.
module tb_pixel_reader_fast;
 reg clk=0;always #5 clk=~clk;
 reg reset=1,clear_cache=0,s_valid=0,m_ready=0;
 reg [31:0] base_addr=32'h1000,pitch_bytes=64;
 reg format_rgb565=0;reg [15:0] s_x=0,s_y=0;
 wire s_ready,m_valid,m_error,m_axi_arvalid,m_axi_rready;
 wire [23:0] m_rgb;wire [31:0] m_axi_araddr;
 wire [7:0] m_axi_arlen;wire [2:0] m_axi_arsize;wire [1:0] m_axi_arburst;
 reg m_axi_arready=0,m_axi_rvalid=0,m_axi_rlast=1;
 reg [63:0] m_axi_rdata=0;reg [1:0] m_axi_rresp=0;
 wcis_pixel_read_axi dut(.*);
 integer ticks=0,reads=0,delay_left=0,version=0,checks=0;
 reg pending=0,inject_error=0,inject_multibeat=0;
 reg [31:0] pending_address=0,held_address=0,random_state=32'h64512893;
 reg ar_stalled=0,out_stalled=0;reg [24:0] held_output;
 function automatic [63:0] word_at(input [31:0] address);
  integer i;reg [31:0] seed;
  begin
   seed=address^(address>>8)^(address>>16)^version;
   for(i=0;i<8;i=i+1)word_at[i*8+:8]=(seed*13+i*37+19)&255;
  end
 endfunction
 function automatic [23:0] pixel_at(input [31:0] address,input bit fmt);
  reg [63:0] shifted;reg [15:0] p;
  begin
   shifted=word_at({address[31:3],3'd0})>>(address[2:0]*8);p=shifted[15:0];
   pixel_at=fmt?{p[15:11],p[15:13],p[10:5],p[10:9],p[4:0],p[4:2]}:shifted[23:0];
  end
 endfunction
 always @(negedge clk)begin
  random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
  m_axi_arready=!pending&&!m_axi_rvalid&&(random_state[2]||random_state[6]);
 end
 always @(posedge clk)begin
  ticks=ticks+1;if(ticks>20000)$fatal(1,"reader watchdog");
  if(reset)begin pending<=0;m_axi_rvalid<=0;ar_stalled<=0;out_stalled<=0;end
  else begin
   if(ar_stalled&&(!m_axi_arvalid||m_axi_araddr!==held_address))$fatal(1,"AR changed under stall");
   ar_stalled<=m_axi_arvalid&&!m_axi_arready;held_address<=m_axi_araddr;
   if(out_stalled&&(!m_valid||{m_error,m_rgb}!==held_output))$fatal(1,"pixel response changed under stall");
   out_stalled<=m_valid&&!m_ready;held_output<={m_error,m_rgb};
   if(m_axi_arvalid&&m_axi_arready)begin
    if(pending||m_axi_rvalid||m_axi_araddr[2:0]||m_axi_arlen!==0||m_axi_arsize!==3||m_axi_arburst!==1)$fatal(1,"invalid/overlapping AXI request");
    pending<=1;pending_address<=m_axi_araddr;delay_left<=2+random_state[10:8];reads=reads+1;
   end
   if(pending&&!m_axi_rvalid)begin
    if(delay_left>0)delay_left<=delay_left-1;
    else begin pending<=0;m_axi_rvalid<=1;m_axi_rdata<=word_at(pending_address);m_axi_rresp<=inject_error?2:0;m_axi_rlast<=!inject_multibeat;end
   end
   if(m_axi_rvalid&&m_axi_rready)begin
    if(!m_axi_rlast)begin m_axi_rlast<=1;m_axi_rresp<=0;m_axi_rdata<=64'h1234;end
    else m_axi_rvalid<=0;
   end
  end
 end
 task request(input [31:0] b,p,input bit fmt,input [15:0] x,y,input bit error_expected,input bit fast_expected);
  integer accepted,before_reads;reg [63:0] address;reg [23:0] expected;
  begin
   @(negedge clk);base_addr=b;pitch_bytes=p;format_rgb565=fmt;s_x=x;s_y=y;s_valid=1;m_ready=0;
   address={32'd0,b}+{32'd0,p}*y+(x<<(fmt?1:2));expected=pixel_at(address[31:0],fmt);before_reads=reads;
   do @(posedge clk);while(!s_ready);accepted=ticks;
   @(negedge clk);s_valid=0;base_addr=32'hdeadbeef;pitch_bytes=0;s_x=16'hffff;s_y=16'hffff;format_rgb565=!fmt;
   while(!m_valid)@(negedge clk);
   if(m_error!==error_expected)$fatal(1,"wrong error flag x=%0d y=%0d",x,y);
   if(!error_expected&&m_rgb!==expected)$fatal(1,"wrong pixel b=%h p=%d fmt=%b x=%d y=%d actual=%h expected=%h",b,p,fmt,x,y,m_rgb,expected);
   if(fast_expected&&(reads!=before_reads||ticks-accepted>1))$fatal(1,"cached coordinate did not take the one-cycle path");
   repeat(3)@(negedge clk);m_ready=1;@(negedge clk);m_ready=0;checks=checks+1;
  end
 endtask
 task invalidate;
  begin @(negedge clk);clear_cache=1;@(negedge clk);clear_cache=0;end
 endtask
 integer i,before_reads;
 initial begin
  repeat(3)@(negedge clk);reset=0;
  request('h1000,64,0,0,2,0,0);request('h1000,64,0,1,2,0,1);
  request('h1000,128,0,1,2,0,0); // pitch changes must not alias a logical hit
  request('h1040,64,0,1,1,0,0);request('h1040,64,0,0,1,0,1);
  request('h1040,64,1,3,1,0,0);request('h1040,64,1,0,1,0,1);
  request('h1040,64,1,1,1,0,1);request('h1040,64,1,2,1,0,1);
  // Non-8-aligned but otherwise legal standalone layouts use the old checks.
  request('h1004,12,0,0,1,0,0);request('h1004,12,0,1,1,0,0);
  request('h1002,10,1,0,1,0,0);request('h1002,10,1,1,1,0,0);
  version=1;invalidate();request('h1040,64,1,1,1,0,0);request('h1040,64,1,2,1,0,1);
  inject_error=1;request('h1000,64,0,20,4,1,0);inject_error=0;request('h1000,64,0,20,4,0,0);
  inject_multibeat=1;request('h1000,64,0,22,4,1,0);inject_multibeat=0;request('h1000,64,0,22,4,0,0);
  before_reads=reads;request('hfffffff8,8,0,0,1,1,0);request('h1001,64,0,0,0,1,0);request('h1000,0,0,0,0,1,0);
  if(reads!=before_reads)$fatal(1,"invalid address issued an AXI read");
  request('hfffffff8,8,0,0,0,0,0);request('hfffffff8,8,0,1,0,0,1);
  for(i=0;i<80;i=i+1)request('h2000,128,i%2,(i*7)%29,(i*3)%11,0,0);
  @(negedge clk);reset=1;repeat(3)@(negedge clk);reset=0;version=2;
  request('hfffffff8,8,0,1,0,0,0);
  $display("PASS pixel_reader_fast checks=%0d reads=%0d tags, formats, strides, errors, drains, reset, backpressure",checks,reads);$finish;
 end
endmodule
