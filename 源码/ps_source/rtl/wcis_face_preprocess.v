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
    localparam [1:0] CMD_IDLE=0, CMD_CHECK=1, CMD_SEND=2;
    reg [1:0] command_stage;
    reg [344:0] geometry_hold;
    reg [31:0] base_addr,pitch_bytes;
    reg rgb565,storage_valid_q;
    wire [31:0] held_frame_id;
    wire [15:0] held_src_w,held_src_h,held_content_w,held_content_h,held_canvas_w,held_canvas_h;
    wire signed [31:0] held_m00,held_m01,held_m02,held_m10,held_m11,held_m12;
    wire held_replicate;
    wire [23:0] held_border;
    assign {held_frame_id,held_src_w,held_src_h,held_content_w,held_content_h,
        held_canvas_w,held_canvas_h,held_m00,held_m01,held_m02,held_m10,held_m11,held_m12,
        held_replicate,held_border} = geometry_hold;
    wire sampler_ready,sampler_busy;
    wire [1:0] sampler_error;
    assign cmd_ready = !reset && command_stage == CMD_IDLE && sampler_ready;
    assign busy = command_stage != CMD_IDLE || sampler_busy;
    // Preserve the external tag/error behavior at command acceptance.
    assign frame_id = held_frame_id;
    assign error = command_stage != CMD_IDLE ? 2'd0 : sampler_error;
    wire accept = cmd_valid && cmd_ready;
    wire rd_valid,rd_ready,rsp_valid,rsp_ready,rsp_error;
    wire [15:0] rd_x,rd_y;
    wire [23:0] rsp_rgb;
    // Snapshot the entire descriptor before the range calculation. Its result
    // crosses a register before it can gate the sampler's high-fanout enables.
    wire [63:0] allocation_end = {32'd0,base_addr} +
        {32'd0,pitch_bytes} * {48'd0,held_src_h};
    wire storage_valid = base_addr[2:0] == 0 && pitch_bytes[2:0] == 0 &&
        {32'd0,pitch_bytes} >= ({48'd0,held_src_w} << (rgb565 ? 1 : 2)) &&
        allocation_end <= 64'h100000000;
    always @(posedge clk) begin
        if (reset) begin
            base_addr<=0; pitch_bytes<=0; rgb565<=0; geometry_hold<=0;
            command_stage<=CMD_IDLE; storage_valid_q<=0;
        end else case (command_stage)
            CMD_IDLE: if (accept) begin
                base_addr<=cmd_base_addr; pitch_bytes<=cmd_pitch_bytes; rgb565<=cmd_rgb565;
                geometry_hold <= {cmd_frame_id,cmd_src_w,cmd_src_h,cmd_content_w,cmd_content_h,
                    cmd_canvas_w,cmd_canvas_h,cmd_m00,cmd_m01,cmd_m02,cmd_m10,cmd_m11,cmd_m12,
                    cmd_replicate,cmd_border};
                command_stage<=CMD_CHECK;
            end
            CMD_CHECK: begin storage_valid_q<=storage_valid; command_stage<=CMD_SEND; end
            CMD_SEND: if (sampler_ready) command_stage<=CMD_IDLE;
            default: begin command_stage<=CMD_IDLE; storage_valid_q<=0; end
        endcase
    end
    wcis_affine_sampler sampler (
        .clk(clk),.reset(reset),.cmd_valid(!reset && command_stage == CMD_SEND),.cmd_ready(sampler_ready),
        .cmd_frame_id(held_frame_id),.cmd_src_w(storage_valid_q ? held_src_w : 16'd0),.cmd_src_h(held_src_h),
        .cmd_content_w(held_content_w),.cmd_content_h(held_content_h),
        .cmd_canvas_w(held_canvas_w),.cmd_canvas_h(held_canvas_h),
        .cmd_m00(held_m00),.cmd_m01(held_m01),.cmd_m02(held_m02),
        .cmd_m10(held_m10),.cmd_m11(held_m11),.cmd_m12(held_m12),
        .cmd_replicate(held_replicate),.cmd_border(held_border),
        .busy(sampler_busy),.done(done),.error(sampler_error),.frame_id(),
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
