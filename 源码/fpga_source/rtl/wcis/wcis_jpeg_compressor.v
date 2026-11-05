// RGB24 -> baseline JPEG (4:2:2). Project adapter; JPEG core is vendored.
// One command owns exactly IMG_WIDTH*IMG_HEIGHT accepted RGB pixels.
// Output is ready/valid, with SOF/EOF, frame ID, and explicit frame abort.
// Sink MUST commit a frame only after EOF. On frame_abort discard its partial
// frame. Finite FIFO cannot absorb an arbitrarily long downstream stall.
// Live SDI cannot obey ready: feed through an independently owned frame buffer.
module wcis_jpeg_compressor #(
    parameter IMG_WIDTH = 1920,
    parameter IMG_HEIGHT = 1080,
    parameter QUALITY = 75,
    parameter FIFO_AW = 12
)(
    input wire clk, reset,
    input wire cmd_valid, output wire cmd_ready,
    input wire [31:0] cmd_frame_id,
    input wire [23:0] s_rgb,
    input wire s_valid, output wire s_ready,
    input wire abort_frame,
    output wire [7:0] m_data,
    output wire m_valid, input wire m_ready,
    output wire m_sof, m_last,
    output reg [31:0] frame_id,
    output reg frame_abort,
    output wire busy,
    output reg overflow_sticky,
    output reg [31:0] frames_done, frames_aborted, fifo_overflows,
    output reg [31:0] last_frame_bytes, last_frame_cycles
);
    localparam FIFO_DEPTH = (1 << FIFO_AW);
    localparam PIXELS = IMG_WIDTH * IMG_HEIGHT;
    reg recover;
    reg init_aw, init_w, initialized;
    wire core_reset_n = !reset && !recover;
    wire awready, wready, bvalid;
    wire [1:0] bresp;

    // Set CTRL.enable once after every reset/recovery. AXI AW/W are independent.
    always @(posedge clk) begin
        if (reset || recover) begin
            init_aw <= 0; init_w <= 0; initialized <= 0;
        end else begin
            if (!init_aw && awready) init_aw <= 1;
            if (!init_w && wready) init_w <= 1;
            if (bvalid && bresp == 0) initialized <= 1;
        end
    end

    reg inflight, feeding;
    reg [31:0] pixel_index, byte_index, cycle_count;
    reg [15:0] column;
    wire core_ready, jpg_valid, jpg_last;
    wire [7:0] jpg_data;
    assign cmd_ready = !reset && !recover && initialized && !inflight && !abort_frame;
    assign s_ready = !reset && !recover && initialized && feeding &&
                     !abort_frame && core_ready;
    assign busy = inflight || recover || !initialized;

    mjpegzero_enc_top #(
        .LITE_MODE(1), .LITE_QUALITY(QUALITY),
        .IMG_WIDTH(IMG_WIDTH), .IMG_HEIGHT(IMG_HEIGHT), .RGB_INPUT(1)
    ) encoder (
        .clk(clk), .rst_n(core_reset_n),
        .s_axis_vid_tdata(s_rgb),
        .s_axis_vid_tvalid(s_valid && feeding && initialized && !recover && !abort_frame),
        .s_axis_vid_tready(core_ready),
        .s_axis_vid_tlast(column == IMG_WIDTH-1),
        .s_axis_vid_tuser(pixel_index == 0),
        .m_axis_jpg_tvalid(jpg_valid), .m_axis_jpg_tdata(jpg_data),
        .m_axis_jpg_tlast(jpg_last),
        .s_axi_awaddr(5'd0), .s_axi_awvalid(!init_aw), .s_axi_awready(awready),
        .s_axi_wdata(32'd1), .s_axi_wstrb(4'hf), .s_axi_wvalid(!init_w),
        .s_axi_wready(wready), .s_axi_bresp(bresp), .s_axi_bvalid(bvalid),
        .s_axi_bready(1'b1), .s_axi_araddr(5'd0), .s_axi_arvalid(1'b0),
        .s_axi_arready(), .s_axi_rdata(), .s_axi_rresp(), .s_axi_rvalid(),
        .s_axi_rready(1'b1)
    );

    // FWFT distributed FIFO. Async read is deliberate (not claimed as BRAM).
    // Store EOF with its byte; SOF follows the count of accepted output bytes.
    (* ram_style = "distributed" *) reg [8:0] fifo [0:FIFO_DEPTH-1];
    reg [FIFO_AW-1:0] wr_ptr, rd_ptr;
    reg [FIFO_AW:0] used;
    assign m_valid = !reset && !recover && inflight && !abort_frame && used != 0;
    assign m_data = fifo[rd_ptr][7:0];
    assign m_last = m_valid && fifo[rd_ptr][8];
    assign m_sof = m_valid && byte_index == 0;
    wire pop = m_valid && m_ready;
    wire push = jpg_valid && initialized && inflight && !recover && !abort_frame;
    wire overflow_now = push && used == FIFO_DEPTH && !pop;

    always @(posedge clk) begin
        if (reset) begin
            recover <= 0; inflight <= 0; feeding <= 0;
            frame_id <= 0; frame_abort <= 0; overflow_sticky <= 0;
            frames_done <= 0; frames_aborted <= 0; fifo_overflows <= 0;
            last_frame_bytes <= 0; last_frame_cycles <= 0;
            pixel_index <= 0; column <= 0; byte_index <= 0; cycle_count <= 0;
            wr_ptr <= 0; rd_ptr <= 0; used <= 0;
        end else begin
            frame_abort <= 0;
            recover <= 0;
            if ((abort_frame && inflight) || overflow_now) begin
                recover <= 1; inflight <= 0; feeding <= 0;
                frame_abort <= 1; frames_aborted <= frames_aborted + 1;
                wr_ptr <= 0; rd_ptr <= 0; used <= 0;
                if (overflow_now) begin
                    overflow_sticky <= 1;
                    fifo_overflows <= fifo_overflows + 1;
                end
            end else begin
                if (cmd_valid && cmd_ready) begin
                    frame_id <= cmd_frame_id; inflight <= 1; feeding <= 1;
                    pixel_index <= 0; column <= 0; byte_index <= 0; cycle_count <= 0;
                end
                if (inflight) cycle_count <= cycle_count + 1;
                if (s_valid && s_ready) begin
                    pixel_index <= pixel_index + 1;
                    if (column == IMG_WIDTH-1) column <= 0;
                    else column <= column + 1;
                    if (pixel_index == PIXELS-1) feeding <= 0;
                end
                case ({push, pop})
                    2'b10: used <= used + 1;
                    2'b01: used <= used - 1;
                    default: ;
                endcase
                if (push) begin
                    fifo[wr_ptr] <= {jpg_last, jpg_data};
                    wr_ptr <= wr_ptr + 1;
                end
                if (pop) begin
                    rd_ptr <= rd_ptr + 1;
                    byte_index <= byte_index + 1;
                    if (m_last) begin
                        inflight <= 0; frames_done <= frames_done + 1;
                        last_frame_bytes <= byte_index + 1;
                        last_frame_cycles <= cycle_count + 1;
                    end
                end
            end
        end
    end
endmodule
