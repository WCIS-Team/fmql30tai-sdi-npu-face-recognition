`timescale 1ns/1ps
// ModelBackend pixel operator, not an application/model scheduler.
// Inverse affine coordinates are signed Q16.16, output is packed RGB888.
// Reference semantics: OpenCV remap INTER_LINEAR (1/32 pixel table), constant
// or replicate border. PS computes the InsightFace five-point transform.
// Source pixels must belong to the immutable frame named by cmd_frame_id.
module wcis_affine_sampler (
    input wire clk, input wire reset,
    input wire cmd_valid, output wire cmd_ready,
    input wire [31:0] cmd_frame_id,
    input wire [15:0] cmd_src_w, cmd_src_h,
    input wire [15:0] cmd_content_w, cmd_content_h,
    input wire [15:0] cmd_canvas_w, cmd_canvas_h,
    input wire signed [31:0] cmd_m00, cmd_m01, cmd_m02,
    input wire signed [31:0] cmd_m10, cmd_m11, cmd_m12,
    input wire cmd_replicate,
    input wire [23:0] cmd_border,
    output wire busy, output reg done,
    output reg [1:0] error, output reg [31:0] frame_id,
    output wire rd_valid, input wire rd_ready,
    output wire [15:0] rd_x, rd_y,
    input wire rsp_valid, output wire rsp_ready,
    input wire [23:0] rsp_rgb, input wire rsp_error,
    output wire m_valid, input wire m_ready,
    output reg [23:0] m_rgb,
    output wire m_sof, m_eol, m_eof
);
    localparam IDLE=0, COORD=1, NEIGHBOR=2, REQUEST=3, RESPONSE=4,
               HORIZONTAL=5, VERTICAL=6, OUTPUT_PIXEL=7;
    reg [3:0] state;
    reg [15:0] src_w, src_h, content_w, content_h, canvas_w, canvas_h;
    reg signed [31:0] m00, m01, m10, m11;
    // Wide accumulators prevent wrapping when a transform maps outside a frame.
    reg signed [47:0] row_sx, row_sy, sx, sy;
    reg signed [36:0] qx, qy;
    reg [4:0] fx, fy;
    reg [15:0] x, y;
    reg [1:0] neighbor;
    reg replicate_border;
    reg [23:0] border;
    reg [23:0] p00, p01, p10, p11;
    reg [12:0] h0 [0:2];
    reg [12:0] h1 [0:2];
    integer channel;
    wire signed [36:0] nx = (qx >>> 5) + $signed({36'd0,neighbor[0]});
    wire signed [36:0] ny = (qy >>> 5) + $signed({36'd0,neighbor[1]});
    wire outside = nx < 0 || ny < 0 || nx >= $signed({21'd0,src_w}) || ny >= $signed({21'd0,src_h});
    wire [15:0] clipped_x = nx < 0 ? 16'd0 : (nx >= $signed({21'd0,src_w}) ? src_w-16'd1 : nx[15:0]);
    wire [15:0] clipped_y = ny < 0 ? 16'd0 : (ny >= $signed({21'd0,src_h}) ? src_h-16'd1 : ny[15:0]);
    wire geometry_valid = cmd_src_w > 0 && cmd_src_h > 0 &&
        cmd_src_w <= 8192 && cmd_src_h <= 8192 &&
        cmd_content_w > 0 && cmd_content_h > 0 &&
        cmd_content_w <= cmd_canvas_w && cmd_content_h <= cmd_canvas_h &&
        cmd_canvas_w <= 640 && cmd_canvas_h <= 640;
    assign cmd_ready = !reset && state == IDLE;
    assign busy = state != IDLE;
    assign rd_valid = !reset && state == REQUEST;
    assign rd_x = clipped_x;
    assign rd_y = clipped_y;
    assign rsp_ready = !reset && state == RESPONSE;
    assign m_valid = !reset && state == OUTPUT_PIXEL;
    assign m_sof = m_valid && x == 0 && y == 0;
    assign m_eol = m_valid && x == canvas_w-1;
    assign m_eof = m_eol && y == canvas_h-1;

    // Unsigned, explicitly widened arithmetic: 255 * 32 * 32 fits 18 bits.
    function [12:0] horizontal;
        input [7:0] a,b; input [4:0] f;
        reg [5:0] left_weight;
        begin
            left_weight = 6'd32 - {1'b0,f};
            horizontal = {5'd0,a} * left_weight + {5'd0,b} * {1'b0,f};
        end
    endfunction
    function [7:0] vertical;
        input [12:0] a,b; input [4:0] f;
        reg [18:0] value;
        begin
            value = {6'd0,a} * (6'd32 - {1'b0,f}) +
                    {6'd0,b} * {1'b0,f} + 19'd512;
            vertical = value[17:10];
        end
    endfunction
    task store_neighbor;
        input [23:0] value;
        begin
            case(neighbor)
                0: p00 <= value; 1: p01 <= value;
                2: p10 <= value; 3: p11 <= value;
            endcase
            if (neighbor == 3) state <= HORIZONTAL;
            else begin neighbor <= neighbor + 1'b1; state <= NEIGHBOR; end
        end
    endtask

    always @(posedge clk) begin
        if (reset) begin
            state <= IDLE; done <= 0; error <= 0; frame_id <= 0;
            x <= 0; y <= 0; m_rgb <= 0;
            src_w <= 0; src_h <= 0; content_w <= 0; content_h <= 0;
            canvas_w <= 0; canvas_h <= 0; m00 <= 0; m01 <= 0;
            m10 <= 0; m11 <= 0; row_sx <= 0; row_sy <= 0;
            sx <= 0; sy <= 0; qx <= 0; qy <= 0; fx <= 0; fy <= 0;
            neighbor <= 0; replicate_border <= 0; border <= 0;
            p00 <= 0; p01 <= 0; p10 <= 0; p11 <= 0;
            for (channel=0; channel<3; channel=channel+1) begin h0[channel]<=0; h1[channel]<=0; end
        end else begin
            done <= 0;
            case(state)
                IDLE: if (cmd_valid) begin
                    frame_id <= cmd_frame_id; error <= 0;
                    if (!geometry_valid) begin error <= 1; done <= 1; end
                    else begin
                        src_w <= cmd_src_w; src_h <= cmd_src_h;
                        content_w <= cmd_content_w; content_h <= cmd_content_h;
                        canvas_w <= cmd_canvas_w; canvas_h <= cmd_canvas_h;
                        m00 <= cmd_m00; m01 <= cmd_m01;
                        m10 <= cmd_m10; m11 <= cmd_m11;
                        row_sx <= {{16{cmd_m02[31]}},cmd_m02};
                        row_sy <= {{16{cmd_m12[31]}},cmd_m12};
                        sx <= {{16{cmd_m02[31]}},cmd_m02};
                        sy <= {{16{cmd_m12[31]}},cmd_m12};
                        replicate_border <= cmd_replicate; border <= cmd_border;
                        x <= 0; y <= 0; state <= COORD;
                    end
                end
                COORD: begin
                    if (x >= content_w || y >= content_h) begin
                        m_rgb <= border; state <= OUTPUT_PIXEL;
                    end else begin
                        // Round Q16 coordinates to the nearest 1/32 pixel,
                        // ties toward +infinity, including negative positions.
                        qx <= (sx + 48'sd1024) >>> 11;
                        qy <= (sy + 48'sd1024) >>> 11;
                        fx <= (sx + 48'sd1024) >>> 11;
                        fy <= (sy + 48'sd1024) >>> 11;
                        neighbor <= 0; state <= NEIGHBOR;
                    end
                end
                NEIGHBOR: begin
                    // Zero-weight taps need no memory transaction.
                    if ((neighbor[0] && fx == 0) || (neighbor[1] && fy == 0)) store_neighbor(24'd0);
                    else if (outside && !replicate_border) store_neighbor(border);
                    else state <= REQUEST;
                end
                REQUEST: if (rd_ready) state <= RESPONSE;
                RESPONSE: if (rsp_valid) begin
                    if (rsp_error) begin error <= 2; done <= 1; state <= IDLE; end
                    else store_neighbor(rsp_rgb);
                end
                HORIZONTAL: begin
                    for (channel=0; channel<3; channel=channel+1) begin
                        h0[channel] <= horizontal(p00[channel*8 +: 8],p01[channel*8 +: 8],fx);
                        h1[channel] <= horizontal(p10[channel*8 +: 8],p11[channel*8 +: 8],fx);
                    end
                    state <= VERTICAL;
                end
                VERTICAL: begin
                    for (channel=0; channel<3; channel=channel+1)
                        m_rgb[channel*8 +: 8] <= vertical(h0[channel],h1[channel],fy);
                    state <= OUTPUT_PIXEL;
                end
                OUTPUT_PIXEL: if (m_ready) begin
                    if (m_eof) begin done <= 1; state <= IDLE; end
                    else begin
                        if (x == canvas_w-1) begin
                            x <= 0; y <= y+1'b1;
                            row_sx <= row_sx + {{16{m01[31]}},m01};
                            row_sy <= row_sy + {{16{m11[31]}},m11};
                            sx <= row_sx + {{16{m01[31]}},m01};
                            sy <= row_sy + {{16{m11[31]}},m11};
                        end else begin
                            x <= x+1'b1;
                            sx <= sx + {{16{m00[31]}},m00};
                            sy <= sy + {{16{m10[31]}},m10};
                        end
                        state <= COORD;
                    end
                end
                default: begin state <= IDLE; error <= 3; done <= 1; end
            endcase
        end
    end
endmodule
