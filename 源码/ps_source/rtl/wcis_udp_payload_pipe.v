`timescale 1ns/1ps
// Cut the packetizer RAM/address mux -> UDP checksum accumulator path.
// Pinned upstream AXI FIFO: registered read, byte/last travel together,
// backpressure when full, no frame dropping or bypass path.
module wcis_udp_payload_pipe(
 input wire clk,reset,
 input wire [7:0] s_data,input wire s_valid,s_last,output wire s_ready,
 output wire [7:0] m_data,output wire m_valid,m_last,input wire m_ready
);
 axis_fifo #(.DEPTH(16),.DATA_WIDTH(8),.KEEP_ENABLE(0),.KEEP_WIDTH(1),
  .LAST_ENABLE(1),.ID_ENABLE(0),.DEST_ENABLE(0),.USER_ENABLE(0),
  .RAM_PIPELINE(1),.OUTPUT_FIFO_ENABLE(0),.FRAME_FIFO(0),
  .DROP_OVERSIZE_FRAME(0),.DROP_BAD_FRAME(0),.DROP_WHEN_FULL(0),.MARK_WHEN_FULL(0)) storage(
  .clk(clk),.rst(reset),.s_axis_tdata(s_data),.s_axis_tkeep(1'b1),
  .s_axis_tvalid(s_valid),.s_axis_tready(s_ready),.s_axis_tlast(s_last),
  .s_axis_tid(8'd0),.s_axis_tdest(8'd0),.s_axis_tuser(1'b0),
  .m_axis_tdata(m_data),.m_axis_tkeep(),.m_axis_tvalid(m_valid),
  .m_axis_tready(m_ready),.m_axis_tlast(m_last),.m_axis_tid(),.m_axis_tdest(),.m_axis_tuser(),
  .pause_req(1'b0),.pause_ack(),.status_depth(),.status_depth_commit(),
  .status_overflow(),.status_bad_frame(),.status_good_frame());
endmodule
