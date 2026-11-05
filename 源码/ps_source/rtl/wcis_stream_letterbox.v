`timescale 1ns/1ps
// Ready/valid RGB888 stream -> padded canvas. No resizing or normalization.
// Input must contain exactly CONTENT_W*CONTENT_H pixels per frame, row major.
// s_data must remain stable while s_valid && !s_ready. Feed from a buffered,
// backpressure-capable stream, NOT directly from an unstoppable DVP camera.
// m_sof/m_eol/m_eof are carried WITH pixels and remain stable during stalls.
module wcis_stream_letterbox #(
    parameter integer CONTENT_W = 640,
    parameter integer CONTENT_H = 360,
    parameter integer CANVAS_W = 640,
    parameter integer CANVAS_H = 640,
    parameter integer PAD_LEFT = 0,
    parameter integer PAD_TOP = 0,
    parameter [23:0] PAD_RGB = 24'h727272
)(
    input wire clk,
    input wire reset,
    input wire s_valid,
    output wire s_ready,
    input wire [23:0] s_data,
    output wire m_valid,
    input wire m_ready,
    output wire [23:0] m_data,
    output wire m_sof,
    output wire m_eol,
    output wire m_eof
);
    localparam integer X_BITS = (CANVAS_W > 1) ? $clog2(CANVAS_W) : 1;
    localparam integer Y_BITS = (CANVAS_H > 1) ? $clog2(CANVAS_H) : 1;
    reg [X_BITS-1:0] x;
    reg [Y_BITS-1:0] y;
    reg active;
    wire content = (x >= PAD_LEFT) && (x < PAD_LEFT + CONTENT_W) &&
                   (y >= PAD_TOP) && (y < PAD_TOP + CONTENT_H);
    wire started = active || s_valid;
    assign m_valid = !reset && started && (content ? s_valid : 1'b1);
    assign s_ready = !reset && content && m_ready;
    assign m_data = content ? s_data : PAD_RGB;
    assign m_sof = m_valid && (x == 0) && (y == 0);
    assign m_eol = m_valid && (x == CANVAS_W-1);
    assign m_eof = m_eol && (y == CANVAS_H-1);
    always @(posedge clk) begin
        if (reset) begin x <= 0; y <= 0; active <= 0; end
        else if (m_valid && m_ready) begin
            if (x == CANVAS_W-1) begin
                x <= 0;
                if (y == CANVAS_H-1) begin y <= 0; active <= 0; end
                else begin y <= y + 1'b1; active <= 1; end
            end else begin x <= x + 1'b1; active <= 1; end
        end
    end
    initial begin
        if (CONTENT_W < 1 || CONTENT_H < 1 || CANVAS_W < 1 || CANVAS_H < 1 ||
            PAD_LEFT < 0 || PAD_TOP < 0 || PAD_LEFT + CONTENT_W > CANVAS_W ||
            PAD_TOP + CONTENT_H > CANVAS_H)
            $error("Invalid letterbox geometry");
    end
endmodule
