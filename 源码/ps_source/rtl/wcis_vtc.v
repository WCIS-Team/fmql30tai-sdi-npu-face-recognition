`timescale 1ns/1ps
// Registered test-pattern source, compatible with the vendor vtc ports.
// Configure timing while VTC is deselected. Hold values stable for >=4 clk
// edges before selecting it. These registers do not implement an AXI CDC.
// On startup hold rst_n low for >=4 running clk edges with stable timing.
// Relative to the vendor counter sequence, all outputs have two pipeline
// stages. RGB is meaningful only when de=1; it is not cleared in blanking.
module vtc (
    input wire clk, input wire rst_n,
    input wire [31:0] H_SYNC, H_BACK_PORCH, H_ACTIVE, H_FRONT_PORCH,
    input wire [31:0] V_SYNC, V_BACK_PORCH, V_ACTIVE, V_FRONT_PORCH,
    output reg [23:0] data,
    output reg vs, hs, de
);
    // Cache timing arithmetic separately from counter/valid/pixel paths.
    // Keep the original 32-bit register contract, including sum arithmetic.
    reg [31:0] h_start, h_tail, v_start, v_tail;
    reg [31:0] h_stop, v_stop, h_total, v_total;
    reg [31:0] h_last, v_last;
    always @(posedge clk) begin
        h_start <= H_SYNC + H_BACK_PORCH;
        h_tail <= H_ACTIVE + H_FRONT_PORCH;
        v_start <= V_SYNC + V_BACK_PORCH;
        v_tail <= V_ACTIVE + V_FRONT_PORCH;
        h_stop <= h_start + H_ACTIVE;
        v_stop <= v_start + V_ACTIVE;
        h_total <= h_start + h_tail;
        v_total <= v_start + v_tail;
        h_last <= h_total - 1'b1;
        v_last <= v_total - 1'b1;
    end

    reg [31:0] hcnt, vcnt;
    reg [7:0] frame_cnt;
    wire line_end = (hcnt == h_last);
    wire frame_end = (vcnt == v_last);
    always @(posedge clk) begin
        if (!rst_n) begin
            hcnt <= 0;
            vcnt <= 0;
            frame_cnt <= 0;
        end else begin
            hcnt <= line_end ? 32'd0 : hcnt + 1'b1;
            if (line_end) vcnt <= frame_end ? 32'd0 : vcnt + 1'b1;
            if ((hcnt == 0) && (vcnt == 0)) frame_cnt <= frame_cnt + 1'b1;
        end
    end

    // Stage 1: independent comparisons and grayscale addition.
    // Stage 2: combine already registered validity, forward RGB without
    // a validity-dependent payload mux. VS/HS use the same two stages.
    reg h_active_d, v_active_d, hs_d, vs_d;
    reg [7:0] gray_d;
    always @(posedge clk) begin
        if (!rst_n) begin
            h_active_d <= 0; v_active_d <= 0;
            hs_d <= 0; vs_d <= 0; gray_d <= 0;
            hs <= 0; vs <= 0; de <= 0; data <= 0;
        end else begin
            h_active_d <= (hcnt >= h_start) && (hcnt < h_stop);
            v_active_d <= (vcnt >= v_start) && (vcnt < v_stop);
            hs_d <= (hcnt < H_SYNC);
            vs_d <= (vcnt < V_SYNC);
            gray_d <= hcnt[7:0] + frame_cnt;
            hs <= hs_d;
            vs <= vs_d;
            de <= h_active_d && v_active_d;
            data <= {3{gray_d}};
        end
    end
endmodule
