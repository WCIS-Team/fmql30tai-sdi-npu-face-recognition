`timescale 1ns/1ps
// A single ModelBackend command -> one RGB888 canvas; no camera/mode policy.
// All ports use clk. PS/AXI-Lite CDC and buffer ownership are external contracts.
module wcis_face_preprocess (
    input wire clk, reset,
    input wire cmd_valid, output wire cmd_ready,
    input wire [31:0] cmd_frame_id, cmd_base_addr, cmd_pitch_bytes,
    input wire cmd_rgb565,
    input wire [15:0] cmd_src_w, cmd_src_h, cmd_content_w, cmd_content_h,
    input wire [15:0] cmd_canvas_w, cmd_canvas_h,
    input wire signed [31:0] cmd_m00,cmd_m01,cmd_m02,cmd_m10,cmd_m11,cmd_m12,
    input wire cmd_replicate, input wire [23:0] cmd_border,
    output wire busy, done, output wire [1:0] error,
    output wire [31:0] frame_id,
    output wire m_valid, input wire m_ready, output wire [23:0] m_rgb,
    output wire m_sof,m_eol,m_eof,
    output wire [31:0] m_axi_araddr,
    output wire [7:0] m_axi_arlen, output wire [2:0] m_axi_arsize,
    output wire [1:0] m_axi_arburst,
    output wire m_axi_arvalid, input wire m_axi_arready,
    input wire [63:0] m_axi_rdata, input wire [1:0] m_axi_rresp,
    input wire m_axi_rlast,m_axi_rvalid, output wire m_axi_rready
);
    reg [31:0] base_addr,pitch_bytes;
    reg rgb565;
    wire accept = cmd_valid && cmd_ready;
    wire rd_valid,rd_ready,rsp_valid,rsp_ready,rsp_error;
    wire [15:0] rd_x,rd_y;
    wire [23:0] rsp_rgb;
    wire [63:0] allocation_end = {32'd0,cmd_base_addr} +
        {32'd0,cmd_pitch_bytes} * {48'd0,cmd_src_h};
    wire storage_valid = cmd_base_addr[2:0] == 0 && cmd_pitch_bytes[2:0] == 0 &&
        {32'd0,cmd_pitch_bytes} >= ({48'd0,cmd_src_w} << (cmd_rgb565 ? 1 : 2)) &&
        allocation_end <= 64'h100000000;
    always @(posedge clk) begin
        if (reset) begin base_addr<=0; pitch_bytes<=0; rgb565<=0; end
        else if (accept) begin base_addr<=cmd_base_addr; pitch_bytes<=cmd_pitch_bytes; rgb565<=cmd_rgb565; end
    end
    wcis_affine_sampler sampler (
        .clk(clk),.reset(reset),.cmd_valid(cmd_valid),.cmd_ready(cmd_ready),
        .cmd_frame_id(cmd_frame_id),.cmd_src_w(storage_valid ? cmd_src_w : 16'd0),.cmd_src_h(cmd_src_h),
        .cmd_content_w(cmd_content_w),.cmd_content_h(cmd_content_h),
        .cmd_canvas_w(cmd_canvas_w),.cmd_canvas_h(cmd_canvas_h),
        .cmd_m00(cmd_m00),.cmd_m01(cmd_m01),.cmd_m02(cmd_m02),
        .cmd_m10(cmd_m10),.cmd_m11(cmd_m11),.cmd_m12(cmd_m12),
        .cmd_replicate(cmd_replicate),.cmd_border(cmd_border),
        .busy(busy),.done(done),.error(error),.frame_id(frame_id),
        .rd_valid(rd_valid),.rd_ready(rd_ready),.rd_x(rd_x),.rd_y(rd_y),
        .rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_rgb(rsp_rgb),.rsp_error(rsp_error),
        .m_valid(m_valid),.m_ready(m_ready),.m_rgb(m_rgb),.m_sof(m_sof),.m_eol(m_eol),.m_eof(m_eof));
    wcis_pixel_read_axi reader (
        .clk(clk),.reset(reset),.clear_cache(accept),
        .base_addr(base_addr),.pitch_bytes(pitch_bytes),.format_rgb565(rgb565),
        .s_valid(rd_valid),.s_ready(rd_ready),.s_x(rd_x),.s_y(rd_y),
        .m_valid(rsp_valid),.m_ready(rsp_ready),.m_rgb(rsp_rgb),.m_error(rsp_error),
        .m_axi_araddr(m_axi_araddr),.m_axi_arlen(m_axi_arlen),.m_axi_arsize(m_axi_arsize),
        .m_axi_arburst(m_axi_arburst),.m_axi_arvalid(m_axi_arvalid),.m_axi_arready(m_axi_arready),
        .m_axi_rdata(m_axi_rdata),.m_axi_rresp(m_axi_rresp),.m_axi_rlast(m_axi_rlast),
        .m_axi_rvalid(m_axi_rvalid),.m_axi_rready(m_axi_rready));
endmodule
