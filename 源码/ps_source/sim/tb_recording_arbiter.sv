`timescale 1ns/1ps
// Client stubs in recording_arbiter_clients.sv saturate this real wrapper.
// Pixel/JPEG datapaths are independently covered by the real-core regression.
module tb_recording_arbiter;
 parameter FAIR=1;
 reg clk=0,ra_clk=0;always #2.5 clk=~clk;always #5 ra_clk=~ra_clk;
 reg rst_n=0,ra_rst_n=0;
 reg [31:0] itf_ra_awaddr=0,itf_ra_awdata=0,itf_ra_araddr=0;
 reg itf_ra_awvalid=0,itf_ra_arvalid=0,itf_ra_rready=1;
 wire itf_ra_awready,itf_ra_arready,itf_ra_rvalid;
 wire [31:0] itf_ra_rdata,itf_awaddr,itf_araddr,itf_arinfo;
 wire [511:0] itf_awdata;wire [71:0] itf_awinfo;
 wire itf_awvalid,itf_arvalid,itf_rready;
 reg itf_awready=0,itf_arready=0,itf_rvalid=0;
 reg [511:0] itf_rdata=0;reg [31:0] itf_rinfo=1;
 reg face_enable=1,jpeg_enable=1,f_resp_ready=1,j_resp_ready=1;
`ifdef ORIGINAL_PRIORITY
 wcis_recording_customop dut(.*);
`else
 wcis_recording_customop #(.FAIR_ARBITRATION(FAIR)) dut(.*);
`endif
 reg [31:0] random_state=32'h30efc118;
 reg pending=0,held_rd=0,held_wr=0;reg [31:0] pending_address=0;
 reg [63:0] held_ar;reg [615:0] held_aw;
 integer delay_count=0,cycles=0,rd_count[0:1],wr_count[0:1];
 integer last_rd=0,last_wr=0,owner,first_face_writes;
 always @(negedge clk) begin
  random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
  itf_awready=(cycles%83>17)&&(random_state[0]||random_state[3]);
  itf_arready=(cycles%97>21)&&(random_state[2]||random_state[5]);
  f_resp_ready=random_state[7]||random_state[11];j_resp_ready=random_state[8]||random_state[13];
 end
 always @(posedge clk) begin
  if(!rst_n) begin pending<=0;itf_rvalid<=0;held_rd<=0;held_wr<=0;end
  else begin
   cycles=cycles+1;if(cycles>40000)$fatal(1,"arbiter watchdog");
   if(held_rd&&(!itf_arvalid||{itf_araddr,itf_arinfo}!==held_ar))$fatal(1,"read grant changed under stall");
   if(held_wr&&(!itf_awvalid||{itf_awaddr,itf_awdata,itf_awinfo}!==held_aw))$fatal(1,"write grant changed under stall");
   held_rd<=itf_arvalid&&!itf_arready;held_ar<={itf_araddr,itf_arinfo};
   held_wr<=itf_awvalid&&!itf_awready;held_aw<={itf_awaddr,itf_awdata,itf_awinfo};
   if(itf_awvalid&&itf_awready)begin
    owner=itf_awaddr[28];
    if(FAIR&&dut.f_awvalid&&dut.j_awvalid&&owner==last_wr)$fatal(1,"write contention did not rotate");
    if((owner&&dut.f_awready)||(!owner&&dut.j_awready))$fatal(1,"write ack sent to wrong owner");
    wr_count[owner]=wr_count[owner]+1;last_wr=owner;
   end
   if(itf_arvalid&&itf_arready)begin
    if(pending||itf_rvalid)$fatal(1,"multiple native reads in flight");
    owner=itf_araddr[28];
    if(FAIR&&dut.f_arvalid&&dut.j_arvalid&&owner==last_rd)$fatal(1,"read contention did not rotate");
    if((owner&&dut.f_arready)||(!owner&&dut.j_arready))$fatal(1,"read ack sent to wrong owner");
    rd_count[owner]=rd_count[owner]+1;last_rd=owner;pending<=1;pending_address<=itf_araddr;delay_count<=1+random_state[17:14];
   end
   if(pending&&!itf_rvalid)begin
    if(delay_count>0)delay_count<=delay_count-1;
    else begin itf_rdata<={16{pending_address}};itf_rvalid<=1;pending<=0;end
   end
   if(itf_rvalid&&itf_rready)itf_rvalid<=0;
  end
 end
 task phase(input bit f,input bit j);
  begin
   @(negedge clk);
   while(dut.wr_hold||dut.rd_hold)@(negedge clk);
   face_enable=f;jpeg_enable=j;
   repeat(3000)@(negedge clk);
  end
 endtask
 initial begin
  rd_count[0]=0;rd_count[1]=0;wr_count[0]=0;wr_count[1]=0;
  repeat(5)@(negedge clk);rst_n=1;ra_rst_n=1;
  repeat(3000)@(negedge clk);
  first_face_writes=wr_count[0];
  if(FAIR&&(first_face_writes<100||wr_count[1]<100||rd_count[0]<20||rd_count[1]<20))$fatal(1,"a saturated client starved");
  if(!FAIR&&first_face_writes!=0)$fatal(1,"legacy control did not reproduce JPEG priority");
  phase(1,0);phase(0,1);phase(1,1);
  if(rd_count[0]==0||rd_count[1]==0||wr_count[0]==0||wr_count[1]==0)$fatal(1,"single-client progress failed");
  $display("PASS recording_arbiter FAIR=%0d reads=%0d,%0d writes=%0d,%0d saturated_face_writes=%0d",FAIR,rd_count[0],rd_count[1],wr_count[0],wr_count[1],first_face_writes);
  $finish;
 end
endmodule
