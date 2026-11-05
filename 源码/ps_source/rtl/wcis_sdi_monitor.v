// Passive diagnostics of the real RX stream, before VTC/source selection.
// Shared reset is required. Source may stop indefinitely: never cancel/reuse
// an outstanding toggle; mark its last snapshot stale in the running AXI domain.
module wcis_sdi_monitor #(
    parameter integer CFG_HZ = 50000000,
    parameter integer SAMPLE_CYCLES = 500000,
    parameter integer STALE_CYCLES = 5000000
) (
    input wire cfg_clk, input wire reset_n,
    input wire rx_clk,
    input wire [11:0] rx_flags, // scan[11], rate[10:7], family[6:3], mode[2:1], lock[0]
    input wire rx_vs, input wire rx_de,
    input wire ref_stable, input wire gt_reset_released,
    output wire [415:0] words
);
    // Assert reset even when a clock is stopped; release locally on two edges.
    (* ASYNC_REG = "TRUE" *) reg [1:0] src_reset, dst_reset;
    always @(posedge rx_clk or negedge reset_n)
        if (!reset_n) src_reset <= 0; else src_reset <= {src_reset[0],1'b1};
    always @(posedge cfg_clk or negedge reset_n)
        if (!reset_n) dst_reset <= 0; else dst_reset <= {dst_reset[0],1'b1};

    reg request_toggle, ack_toggle;
    (* ASYNC_REG = "TRUE" *) reg [1:0] request_sync, ack_sync;
    (* ASYNC_REG = "TRUE" *) reg [1:0] ref_sync, gt_sync;
    // Synchronizer chains have no clock enable or intervening logic.
    always @(posedge rx_clk or negedge reset_n)
        if (!reset_n) request_sync <= 0;
        else request_sync <= {request_sync[0],request_toggle};
    always @(posedge cfg_clk or negedge reset_n) begin
        if (!reset_n) begin ack_sync <= 0; ref_sync <= 0; gt_sync <= 0; end
        else begin
            ack_sync <= {ack_sync[0],ack_toggle};
            ref_sync <= {ref_sync[0],ref_stable};
            gt_sync <= {gt_sync[0],gt_reset_released};
        end
    end
    reg [31:0] cycles, frames, lines, pixels;
    reg old_vs, old_de, old_lock, in_frame;
    reg [15:0] line_pixels, frame_lines, max_width, width, height;
    // Packed payload is stable from acknowledgement until next request.
    // Its physical max-delay/bus-skew constraints must accompany integration.
    reg [191:0] payload_hold;
    wire frame_edge = rx_flags[0] && rx_vs && !old_vs;
    wire line_start = rx_flags[0] && rx_de && !old_de;
    wire line_end = rx_flags[0] && !rx_de && old_de;
    always @(posedge rx_clk or negedge reset_n) begin
        if (!reset_n) begin
            ack_toggle <= 0; payload_hold <= 0;
            cycles <= 0; frames <= 0; lines <= 0; pixels <= 0;
            old_vs <= 0; old_de <= 0; old_lock <= 0; in_frame <= 0;
            line_pixels <= 0; frame_lines <= 0; max_width <= 0;
            width <= 0; height <= 0;
        end else if (!src_reset[1]) begin
            ack_toggle <= 0;
        end else begin
            cycles <= cycles + 1'b1;
            old_vs <= rx_vs; old_de <= rx_de; old_lock <= rx_flags[0];
            if (rx_flags[0] && rx_de) pixels <= pixels + 1'b1;
            if (line_start) lines <= lines + 1'b1;
            if (!rx_flags[0] || !old_lock) begin
                in_frame <= 0; line_pixels <= 0; frame_lines <= 0;
                max_width <= 0; width <= 0; height <= 0;
            end else if (frame_edge) begin
                frames <= frames + 1'b1;
                // Only a complete interval between two boundaries is measured.
                if (in_frame) begin
                    width <= (line_end && line_pixels > max_width) ? line_pixels : max_width;
                    height <= frame_lines;
                end
                in_frame <= 1; frame_lines <= line_start ? 1 : 0; max_width <= 0;
                line_pixels <= rx_de ? 1 : 0;
            end else if (in_frame) begin
                if (line_start) begin
                    line_pixels <= 1;
                    if (frame_lines != 16'hffff) frame_lines <= frame_lines + 1'b1;
                end else if (rx_de && line_pixels != 16'hffff)
                    line_pixels <= line_pixels + 1'b1;
                if (line_end && line_pixels > max_width) max_width <= line_pixels;
            end
            if (request_sync[1] != ack_toggle) begin
                payload_hold <= {{height,width},pixels,lines,frames,cycles,{20'd0,rx_flags}};
                ack_toggle <= request_sync[1];
            end
        end
    end

    reg [191:0] snapshot;
    reg [31:0] sample_timer, tick, commit_tick, age, snapshot_seq;
    reg ever_received;
    wire pending = request_toggle != ack_sync[1];
    // Equality with the ACK alone is insufficient during reset. Commit occurs
    // only for a request whose ACK has arrived and has not already been consumed.
    reg consumed_ack;
    always @(posedge cfg_clk or negedge reset_n) begin
        if (!reset_n) begin
            request_toggle <= 0; consumed_ack <= 0; snapshot <= 0;
            sample_timer <= 0; tick <= 0; commit_tick <= 0;
            age <= 32'hffffffff; snapshot_seq <= 0; ever_received <= 0;
        end else if (!dst_reset[1]) begin
            request_toggle <= 0; consumed_ack <= 0;
        end else begin
            tick <= tick + 1'b1;
            if (age != 32'hffffffff) age <= age + 1'b1;
            if (ack_sync[1] != consumed_ack) begin
                snapshot <= payload_hold; consumed_ack <= ack_sync[1];
                snapshot_seq <= snapshot_seq + 1'b1; commit_tick <= tick;
                age <= 0; ever_received <= 1;
            end
            if (sample_timer == SAMPLE_CYCLES-1) begin
                sample_timer <= 0;
                if (!pending && ack_sync[1] == consumed_ack)
                    request_toggle <= !request_toggle;
            end else sample_timer <= sample_timer + 1'b1;
        end
    end
    localparam [31:0] CFG_FREQUENCY = CFG_HZ;
    assign words = {
        CFG_FREQUENCY, snapshot[191:160], snapshot[159:128],
        snapshot[127:96], snapshot[95:64], snapshot[63:32], snapshot[31:0],
        age, commit_tick, snapshot_seq,
        {27'd0,gt_sync[1],ref_sync[1],pending,
         (ever_received && age < STALE_CYCLES),ever_received},
        32'd1,32'h53444932 // SDI2; offsets 0x100..0x130
    };
endmodule
