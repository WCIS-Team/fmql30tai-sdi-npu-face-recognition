`timescale 1ns/1ps
module tb_native_write_commit;
 reg clk=0;always #5 clk=~clk;
 reg reset=1;
 reg [31:0] c_awaddr=0,c_araddr=0,c_arinfo=1;
 reg [511:0] c_awdata=0;
 reg [71:0] c_awinfo=0;
 reg c_awvalid=0,c_arvalid=0,c_rready=0,c_requires_verify=1;
 wire c_awready,c_arready,c_rvalid;
 wire [511:0] c_rdata;wire [31:0] c_rinfo;
 wire [31:0] m_awaddr,m_araddr,m_arinfo;
 wire [511:0] m_awdata;wire [71:0] m_awinfo;
 wire m_awvalid,m_arvalid,m_rready;
 reg m_awready=1,m_arready=1,m_rvalid=0;
 reg [511:0] m_rdata=0;reg [31:0] m_rinfo=1;
 wire fault;wire [31:0] writes_visible,retry_reads,last_address;
 wcis_native_write_commit #(.MAX_READS(32),.MAX_CYCLES(1000)) dut(.*);
 reg [511:0] memory[0:7];
 reg [511:0] posted_data;
 reg [63:0] posted_mask;
 integer posted_addr=0,remaining=0,write_delay=40;
 integer i,k,accepted=0,acks=0,cycles=0;
 reg never_commit=0;
 reg [607:0] held_write;
 reg [63:0] held_read;
 reg write_stall=0,read_stall=0;
 always @(posedge clk) begin
  cycles=cycles+1;if(cycles>10000)$fatal(1,"watchdog");
  if(!reset) begin
   if(write_stall && (!m_awvalid || {m_awaddr,m_awdata,m_awinfo[70:7]}!==held_write))$fatal(1,"AW payload changed under backpressure");
   if(read_stall && (!m_arvalid || {m_araddr,m_arinfo}!==held_read))$fatal(1,"AR payload changed under backpressure");
   write_stall=m_awvalid&&!m_awready;held_write={m_awaddr,m_awdata,m_awinfo[70:7]};
   read_stall=m_arvalid&&!m_arready;held_read={m_araddr,m_arinfo};
   if(remaining>0)begin
    remaining=remaining-1;
    if(remaining==0 && !never_commit)for(k=0;k<64;k=k+1)if(posted_mask[k])memory[posted_addr][k*8 +:8]=posted_data[k*8 +:8];
   end
   if(m_awvalid&&m_awready)begin
    accepted=accepted+1;posted_addr=m_awaddr/64;posted_data=m_awdata;posted_mask=m_awinfo[70:7];remaining=write_delay;
   end
   if(c_awvalid&&c_awready)begin
    acks=acks+1;
    for(k=0;k<64;k=k+1)if(c_requires_verify&&c_awinfo[7+k]&&memory[c_awaddr/64][k*8 +:8]!==c_awdata[k*8 +:8])$fatal(1,"client ACK before enabled bytes visible");
   end
  end else begin remaining=0;write_stall=0;read_stall=0;end
 end
 // One response slot, random latency/backpressure is also exercised by tasks.
 reg response_pending=0;reg [31:0] response_addr=0;
 always @(posedge clk)begin
  if(reset)begin m_rvalid<=0;response_pending<=0;end
  else begin
   if(m_rvalid&&m_rready)m_rvalid<=0;
   if(response_pending&&!m_rvalid)begin m_rdata<=memory[response_addr/64];m_rvalid<=1;response_pending<=0;end
   if(m_arvalid&&m_arready)begin response_pending<=1;response_addr<=m_araddr;end
  end
 end
 task write_word(input [31:0] addr,input [511:0] data,input [63:0] mask_bits);
  begin
   @(negedge clk);c_awaddr=addr;c_awdata=data;c_awinfo={1'b0,mask_bits,6'd0,1'b1};c_awvalid=1;
   do @(posedge clk);while(!c_awready&&!fault);
   @(negedge clk);c_awvalid=0;
  end
 endtask
 task client_read(input [31:0] addr);
  begin
   @(negedge clk);c_araddr=addr;c_arvalid=1;c_rready=0;
   do @(posedge clk);while(!c_arready);
   @(negedge clk);c_arvalid=0;
   wait(c_rvalid);repeat(3)@(posedge clk);
   if(c_rdata!==memory[addr/64])$fatal(1,"ordinary read misrouted");
   @(negedge clk);c_rready=1;@(posedge clk);@(negedge clk);c_rready=0;
  end
 endtask
 initial begin
  for(i=0;i<8;i=i+1)memory[i]={64{8'ha5}};
  repeat(3)@(negedge clk);reset=0;
  // Native acceptance deliberately precedes data visibility by 40 cycles.
  fork
   write_word(0,{64{8'h3c}},64'hffffffffffffffff);
   client_read(128);
  join
  if(fault||writes_visible!=1||retry_reads==0||accepted!=1||acks!=1)$fatal(1,"deferred commit/ordinary read test failed fault=%0d visible=%0d retries=%0d accepted=%0d acks=%0d",fault,writes_visible,retry_reads,accepted,acks);
  write_delay=3;write_word(64,{64{8'h11}},64'h0000000000000007);
  if(memory[1][23:0]!==24'h111111||memory[1][31:24]!==8'ha5||writes_visible!=2)$fatal(1,"byte mask verification failed");
  // Stall native AW then AR. Neither request may change while stalled.
  fork
   begin m_awready=0;repeat(4)@(negedge clk);m_awready=1;end
   write_word(192,{64{8'h27}},64'hffffffffffffffff);
  join
  fork
   begin m_arready=0;repeat(6)@(negedge clk);m_arready=1;end
   write_word(256,{64{8'h28}},64'hffffffffffffffff);
  join
  never_commit=1;write_word(320,{64{8'h77}},64'hffffffffffffffff);
  if(!fault||c_awready||writes_visible!=4)$fatal(1,"uncommitted write did not fail closed");
  @(negedge clk);reset=1;repeat(3)@(negedge clk);reset=0;never_commit=0;
  write_word(384,{64{8'h88}},64'hffffffffffffffff);
  if(fault||writes_visible!=1)$fatal(1,"shared reset did not clear verifier state");
  // A timeout while AR is backpressured must retain VALID/payload, then drain
  // a late response without acknowledging the failed client write.
  fork
   begin m_arready=0;repeat(1100)@(negedge clk);
    if(!fault||!m_arvalid||c_awready)$fatal(1,"timeout retracted a stalled AR or acknowledged failure");
    m_arready=1;repeat(12)@(negedge clk);
    if(m_rvalid||c_awready)$fatal(1,"late response was not drained after timeout");
   end
   write_word(448,{64{8'h99}},64'hffffffffffffffff);
  join
  // Legacy adder keeps its original acceptance contract, without a verify AR.
  @(negedge clk);reset=1;repeat(3)@(negedge clk);reset=0;c_requires_verify=0;m_arready=0;
  write_word(64,{64{8'hab}},64'hffffffffffffffff);
  if(fault||writes_visible!=0||m_arvalid||remaining==0)$fatal(1,"legacy passthrough was verified or stalled");
  repeat(50)@(negedge clk);m_arready=1;
  $display("PASS native_write_commit deferred visibility, masks, read arbitration, stalls, fault, reset");$finish;
 end
endmodule
