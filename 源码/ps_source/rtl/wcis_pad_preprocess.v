`timescale 1ns/1ps
// MiniFASNet crop-local resize adapter; no liveness/identity decision logic.
// ROI is an inclusive upstream CropImage box expressed as x,y,width,height.
// Original B,G,R,X frame remains immutable until done; frame_id is echoed.
// Reuses the verified Q5 bilinear sampler. This is not bit-exact cv2.resize;
// quantify input and model-output differences before accepting a deployment.
module wcis_pad_preprocess (
    input wire clk, reset,
    input wire cmd_valid, output wire cmd_ready,
    input wire [31:0] cmd_frame_id, cmd_base_addr, cmd_pitch_bytes,
    input wire [15:0] cmd_src_w, cmd_src_h,
    input wire [15:0] cmd_roi_x, cmd_roi_y, cmd_roi_w, cmd_roi_h,
    output wire busy, done, output wire [1:0] error,
    output wire [31:0] frame_id,
    output wire m_valid, input wire m_ready, output wire [23:0] m_rgb,
    output wire m_sof, m_eol, m_eof,
    output wire [31:0] m_axi_araddr,
    output wire [7:0] m_axi_arlen, output wire [2:0] m_axi_arsize,
    output wire [1:0] m_axi_arburst,
    output wire m_axi_arvalid, input wire m_axi_arready,
    input wire [63:0] m_axi_rdata, input wire [1:0] m_axi_rresp,
    input wire m_axi_rlast, m_axi_rvalid, output wire m_axi_rready
);
    reg [31:0] base_addr, pitch_bytes;
    reg [15:0] roi_x, roi_y;
    wire accept = cmd_valid && cmd_ready;
    wire [63:0] allocation_end = {32'd0,cmd_base_addr} +
        {32'd0,cmd_pitch_bytes} * {48'd0,cmd_src_h};
    wire valid_storage = cmd_base_addr[2:0] == 0 && cmd_pitch_bytes[2:0] == 0 &&
        {32'd0,cmd_pitch_bytes} >= ({48'd0,cmd_src_w} << 2) &&
        allocation_end <= 64'h100000000;
    wire valid_roi = cmd_src_w > 0 && cmd_src_h > 0 &&
        cmd_src_w <= 8192 && cmd_src_h <= 8192 &&
        cmd_roi_w > 0 && cmd_roi_h > 0 &&
        ({1'b0,cmd_roi_x}+{1'b0,cmd_roi_w} <= {1'b0,cmd_src_w}) &&
        ({1'b0,cmd_roi_y}+{1'b0,cmd_roi_h} <= {1'b0,cmd_src_h});
    // Round local half-pixel inverse resize coefficients to signed Q16.16.
    // Constant denominators synthesize without a variable divider.
    wire signed [31:0] scale_x = ({cmd_roi_w,16'd0}+32'd40)/32'd80;
    wire signed [31:0] scale_y = ({cmd_roi_h,16'd0}+32'd40)/32'd80;
    wire signed [31:0] offset_x = $signed(({cmd_roi_w,16'd0}+32'd80)/32'd160)-32'sd32768;
    wire signed [31:0] offset_y = $signed(({cmd_roi_h,16'd0}+32'd80)/32'd160)-32'sd32768;
    wire rd_valid, rd_ready, rsp_valid, rsp_ready, rsp_error;
    wire [15:0] rd_x, rd_y;
    wire [23:0] rsp_rgb;
    always @(posedge clk) begin
        if (reset) begin base_addr<=0; pitch_bytes<=0; roi_x<=0; roi_y<=0; end
        else if (accept) begin
            base_addr<=cmd_base_addr; pitch_bytes<=cmd_pitch_bytes;
            roi_x<=cmd_roi_x; roi_y<=cmd_roi_y;
        end
    end
    // Clip to ROI-local dimensions BEFORE translating to full-frame addresses.
    // Merely offsetting an affine transform would sample beyond a small ROI.
    wcis_affine_sampler sampler (
        .clk(clk),.reset(reset),.cmd_valid(cmd_valid),.cmd_ready(cmd_ready),
        .cmd_frame_id(cmd_frame_id),
        .cmd_src_w(valid_storage && valid_roi ? cmd_roi_w : 16'd0),.cmd_src_h(cmd_roi_h),
        .cmd_content_w(16'd80),.cmd_content_h(16'd80),.cmd_canvas_w(16'd80),.cmd_canvas_h(16'd80),
        .cmd_m00(scale_x),.cmd_m01(32'sd0),.cmd_m02(offset_x),
        .cmd_m10(32'sd0),.cmd_m11(scale_y),.cmd_m12(offset_y),
        .cmd_replicate(1'b1),.cmd_border(24'd0),
        .busy(busy),.done(done),.error(error),.frame_id(frame_id),
        .rd_valid(rd_valid),.rd_ready(rd_ready),.rd_x(rd_x),.rd_y(rd_y),
        .rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.rsp_rgb(rsp_rgb),.rsp_error(rsp_error),
        .m_valid(m_valid),.m_ready(m_ready),.m_rgb(m_rgb),.m_sof(m_sof),.m_eol(m_eol),.m_eof(m_eof));
    wcis_pixel_read_axi reader (
        .clk(clk),.reset(reset),.clear_cache(accept),
        .base_addr(base_addr),.pitch_bytes(pitch_bytes),.format_rgb565(1'b0),
        .s_valid(rd_valid),.s_ready(rd_ready),.s_x(rd_x+roi_x),.s_y(rd_y+roi_y),
        .m_valid(rsp_valid),.m_ready(rsp_ready),.m_rgb(rsp_rgb),.m_error(rsp_error),
        .m_axi_araddr(m_axi_araddr),.m_axi_arlen(m_axi_arlen),.m_axi_arsize(m_axi_arsize),
        .m_axi_arburst(m_axi_arburst),.m_axi_arvalid(m_axi_arvalid),.m_axi_arready(m_axi_arready),
        .m_axi_rdata(m_axi_rdata),.m_axi_rresp(m_axi_rresp),.m_axi_rlast(m_axi_rlast),
        .m_axi_rvalid(m_axi_rvalid),.m_axi_rready(m_axi_rready));
endmodule
