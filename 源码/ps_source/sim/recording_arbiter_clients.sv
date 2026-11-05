`timescale 1ns/1ps
// Test-only traffic generators, never synthesis sources.
module wcis_face_customop(
    input wire [31:0] itf_ra_awaddr,itf_ra_awdata,
    input wire itf_ra_awvalid,output wire itf_ra_awready,
    input wire [31:0] itf_ra_araddr,input wire itf_ra_arvalid,
    output wire itf_ra_arready,output wire [31:0] itf_ra_rdata,
    output wire itf_ra_rvalid,input wire itf_ra_rready,
    output wire [31:0] itf_awaddr,output wire [511:0] itf_awdata,
    output wire [71:0] itf_awinfo,output wire itf_awvalid,input wire itf_awready,
    output wire [31:0] itf_araddr,output wire [31:0] itf_arinfo,
    output wire itf_arvalid,input wire itf_arready,
    input wire [511:0] itf_rdata,input wire [31:0] itf_rinfo,
    input wire itf_rvalid,output wire itf_rready,
    input wire clk,ra_clk,rst_n,ra_rst_n,
    output wire native_write_is_face
);

 assign native_write_is_face=1;
 localparam OWNER=0;
 reg [15:0] rd_sequence=0,wr_sequence=0;
 reg outstanding=0;reg [31:0] expected_address=0;
 wire enable_client=OWNER ? tb_recording_arbiter.jpeg_enable : tb_recording_arbiter.face_enable;
 assign itf_ra_awready=1;assign itf_ra_arready=1;assign itf_ra_rvalid=itf_ra_arvalid;assign itf_ra_rdata=0;
 assign itf_awvalid=rst_n&&enable_client;
 assign itf_awaddr=(OWNER?32'h10000000:0)+{10'd0,wr_sequence,6'd0};
 assign itf_awdata={16{itf_awaddr}};assign itf_awinfo=72'hffffffffffffffff81;
 assign itf_arvalid=rst_n&&enable_client&&!outstanding;
 assign itf_araddr=(OWNER?32'h10000000:0)+{10'd0,rd_sequence,6'd0};assign itf_arinfo=1;
 assign itf_rready=OWNER?tb_recording_arbiter.j_resp_ready:tb_recording_arbiter.f_resp_ready;
 always @(posedge clk)begin
  if(!rst_n)begin rd_sequence<=0;wr_sequence<=0;outstanding<=0;end
  else begin
   if(itf_awvalid&&itf_awready)wr_sequence<=wr_sequence+1;
   if(itf_arvalid&&itf_arready)begin
    if(outstanding)$fatal(1,"client duplicate read");
    outstanding<=1;expected_address<=itf_araddr;rd_sequence<=rd_sequence+1;
   end
   if(itf_rvalid&&itf_rready)begin
    if(!outstanding||itf_rdata!=={16{expected_address}})$fatal(1,"read response misrouted");
    outstanding<=0;
   end
  end
 end
endmodule
module wcis_jpeg_customop #(parameter IMG_WIDTH=64,IMG_HEIGHT=16,QUALITY=75)(
    input wire [31:0] itf_ra_awaddr,itf_ra_awdata,
    input wire itf_ra_awvalid,output wire itf_ra_awready,
    input wire [31:0] itf_ra_araddr,input wire itf_ra_arvalid,
    output wire itf_ra_arready,output wire [31:0] itf_ra_rdata,
    output wire itf_ra_rvalid,input wire itf_ra_rready,
    output wire [31:0] itf_awaddr,output wire [511:0] itf_awdata,
    output wire [71:0] itf_awinfo,output wire itf_awvalid,input wire itf_awready,
    output wire [31:0] itf_araddr,output wire [31:0] itf_arinfo,
    output wire itf_arvalid,input wire itf_arready,
    input wire [511:0] itf_rdata,input wire [31:0] itf_rinfo,
    input wire itf_rvalid,output wire itf_rready,
    input wire clk,ra_clk,rst_n,ra_rst_n
);

 localparam OWNER=1;
 reg [15:0] rd_sequence=0,wr_sequence=0;
 reg outstanding=0;reg [31:0] expected_address=0;
 wire enable_client=OWNER ? tb_recording_arbiter.jpeg_enable : tb_recording_arbiter.face_enable;
 assign itf_ra_awready=1;assign itf_ra_arready=1;assign itf_ra_rvalid=itf_ra_arvalid;assign itf_ra_rdata=0;
 assign itf_awvalid=rst_n&&enable_client;
 assign itf_awaddr=(OWNER?32'h10000000:0)+{10'd0,wr_sequence,6'd0};
 assign itf_awdata={16{itf_awaddr}};assign itf_awinfo=72'hffffffffffffffff81;
 assign itf_arvalid=rst_n&&enable_client&&!outstanding;
 assign itf_araddr=(OWNER?32'h10000000:0)+{10'd0,rd_sequence,6'd0};assign itf_arinfo=1;
 assign itf_rready=OWNER?tb_recording_arbiter.j_resp_ready:tb_recording_arbiter.f_resp_ready;
 always @(posedge clk)begin
  if(!rst_n)begin rd_sequence<=0;wr_sequence<=0;outstanding<=0;end
  else begin
   if(itf_awvalid&&itf_awready)wr_sequence<=wr_sequence+1;
   if(itf_arvalid&&itf_arready)begin
    if(outstanding)$fatal(1,"client duplicate read");
    outstanding<=1;expected_address<=itf_araddr;rd_sequence<=rd_sequence+1;
   end
   if(itf_rvalid&&itf_rready)begin
    if(!outstanding||itf_rdata!=={16{expected_address}})$fatal(1,"read response misrouted");
    outstanding<=0;
   end
  end
 end
endmodule
