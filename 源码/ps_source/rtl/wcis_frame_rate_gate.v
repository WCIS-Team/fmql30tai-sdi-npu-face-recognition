`timescale 1ns/1ps
// Select whole DVP frames. This block cannot backpressure a live camera.
// cfg_word = {enable, active}; reset defaults to bypass for demo compatibility.
// Bundled-data mailbox: hold payload until acknowledgement at a frame boundary.
// Both domains must reset together. Reset release is synchronized locally.
module wcis_frame_rate_gate #(
    parameter integer SOURCE_FPS = 30,
    parameter integer ACTIVE_FPS = 20,
    parameter integer STANDBY_FPS = 1
)(
    input wire cfg_clk,
    input wire cam_clk,
    input wire reset,
    input wire cfg_valid,
    input wire [1:0] cfg_word,
    output wire cfg_ready,
    output reg [1:0] cfg_applied,
    input wire s_vsync,
    input wire s_href,
    input wire [23:0] s_data,
    output reg m_vsync,
    output reg m_href,
    output reg [23:0] m_data,
    output reg [31:0] seen_frames,
    output reg [31:0] selected_frames,
    output reg [31:0] dropped_frames
);
    (* ASYNC_REG = "TRUE" *) reg [1:0] cfg_reset_sync, cam_reset_sync;
    always @(posedge cfg_clk or posedge reset)
        if (reset) cfg_reset_sync <= 2'b11;
        else cfg_reset_sync <= {cfg_reset_sync[0], 1'b0};
    always @(posedge cam_clk or posedge reset)
        if (reset) cam_reset_sync <= 2'b11;
        else cam_reset_sync <= {cam_reset_sync[0], 1'b0};

    reg [1:0] payload_hold;
    reg request_toggle;
    reg applied_toggle;
    (* ASYNC_REG = "TRUE" *) reg [1:0] request_sync, ack_sync;
    reg ack_seen;
    assign cfg_ready = !cfg_reset_sync[1] && (request_toggle == ack_sync[1]);

    always @(posedge cfg_clk or posedge reset) begin
        if (reset) begin
            payload_hold <= 2'b01;
            request_toggle <= 1'b0;
            ack_sync <= 2'b00;
            ack_seen <= 1'b0;
            cfg_applied <= 2'b01;
        end else if (cfg_reset_sync[1]) begin
            payload_hold <= 2'b01;
            request_toggle <= 1'b0;
            ack_sync <= 2'b00;
            ack_seen <= 1'b0;
            cfg_applied <= 2'b01;
        end else begin
            ack_sync <= {ack_sync[0], applied_toggle};
            if (ack_sync[1] != ack_seen) begin
                cfg_applied <= payload_hold;
                ack_seen <= ack_sync[1];
            end
            if (cfg_valid && cfg_ready) begin
                payload_hold <= cfg_word;
                request_toggle <= ~request_toggle;
            end
        end
    end

    reg [1:0] current_config;
    reg vsync_d;
    reg keep_frame;
    localparam integer PHASE_BITS = (SOURCE_FPS > 1) ? $clog2(SOURCE_FPS + 1) : 1;
    reg [PHASE_BITS-1:0] phase;
    wire frame_start = s_vsync && !vsync_d;
    wire pending = (request_sync[1] != applied_toggle);
    wire [1:0] boundary_config = pending ? payload_hold : current_config;
    wire [PHASE_BITS:0] target_fps = boundary_config[0] ? ACTIVE_FPS : STANDBY_FPS;
    // A configuration commit restarts the fractional phase at zero.
    wire [PHASE_BITS:0] phase_sum = {1'b0, pending ? {PHASE_BITS{1'b0}} : phase} + target_fps;
    wire boundary_keep = !boundary_config[1] || (phase_sum >= SOURCE_FPS);
    wire pixel_keep = frame_start ? boundary_keep : keep_frame;

    always @(posedge cam_clk or posedge reset) begin
        if (reset) begin
            request_sync <= 2'b00;
            applied_toggle <= 1'b0;
            current_config <= 2'b01;
            vsync_d <= 1'b0;
            keep_frame <= 1'b0;
            phase <= 32'd0;
            m_vsync <= 1'b0; m_href <= 1'b0; m_data <= 24'd0;
            seen_frames <= 32'd0;
            selected_frames <= 32'd0;
            dropped_frames <= 32'd0;
        end else if (cam_reset_sync[1]) begin
            request_sync <= 2'b00;
            applied_toggle <= 1'b0;
            current_config <= 2'b01;
            vsync_d <= 1'b0;
            keep_frame <= 1'b0;
            phase <= 32'd0;
            m_vsync <= 1'b0; m_href <= 1'b0; m_data <= 24'd0;
            seen_frames <= 32'd0;
            selected_frames <= 32'd0;
            dropped_frames <= 32'd0;
        end else begin
            request_sync <= {request_sync[0], request_toggle};
            vsync_d <= s_vsync;
            m_vsync <= s_vsync && pixel_keep;
            m_href <= s_href && pixel_keep;
            // Payload is meaningful only when m_href is high. Register it
            // unconditionally so VS/frame selection is not a 24-bit data mux.
            m_data <= s_data;
            if (frame_start) begin
                if (pending) begin
                    current_config <= payload_hold;
                    applied_toggle <= request_sync[1];
                end
                keep_frame <= boundary_keep;
                phase <= !boundary_config[1] ? 32'd0 :
                         (boundary_keep ? phase_sum - SOURCE_FPS : phase_sum);
                seen_frames <= seen_frames + 1'b1;
                if (boundary_keep) selected_frames <= selected_frames + 1'b1;
                else dropped_frames <= dropped_frames + 1'b1;
            end
        end
    end

    // Elaboration/simulation guard. Static parameters are not runtime controls.
    initial begin
        if (SOURCE_FPS < 1 || ACTIVE_FPS < 1 || STANDBY_FPS < 1 ||
            ACTIVE_FPS > SOURCE_FPS || STANDBY_FPS > SOURCE_FPS)
            $error("Invalid frame-rate parameters");
    end
endmodule
