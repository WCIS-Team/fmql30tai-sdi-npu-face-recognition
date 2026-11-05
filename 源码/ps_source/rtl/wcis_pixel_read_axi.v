`timescale 1ns/1ps
// Read-only 64-bit AXI client for the vendor DDR/HP interconnect boundary.
// One outstanding aligned 8-byte read, one-line cache, no speculative reads.
// Default little-endian B,G,R,X pixels preserve RGB888 precision. Optional
// RGB565 reads the vendor preview format; this is NOT an equivalent model input.
// AXI reset must be shared with the interconnect; never cancel a live read by
// resetting only this client. clear_cache is legal only between commands.
module wcis_pixel_read_axi (
    input wire clk, input wire reset, input wire clear_cache,
    input wire [31:0] base_addr, pitch_bytes,
    input wire format_rgb565,
    input wire s_valid, output wire s_ready,
    input wire [15:0] s_x, s_y,
    output wire m_valid, input wire m_ready,
    output reg [23:0] m_rgb, output reg m_error,
    output reg [31:0] m_axi_araddr,
    output wire [7:0] m_axi_arlen, output wire [2:0] m_axi_arsize,
    output wire [1:0] m_axi_arburst,
    output wire m_axi_arvalid, input wire m_axi_arready,
    input wire [63:0] m_axi_rdata, input wire [1:0] m_axi_rresp,
    input wire m_axi_rlast, m_axi_rvalid, output wire m_axi_rready
);
    localparam IDLE=0, ROW_OFFSET=1, ADD_OFFSET=2, CHECK_ADDRESS=3,
               ADDRESS=4, DATA=5, DRAIN=6, RESPONSE=7;
    reg [2:0] state;
    reg cache_valid;
    reg [31:0] cache_addr;
    reg [63:0] cache_data;
    // A successful physical read also establishes a logical word tag. With
    // 8-byte aligned base/pitch, coordinates within that word need no repeated
    // row multiply/address pipeline. Other layouts keep the checked slow path.
    reg [31:0] cache_base,cache_pitch;
    reg [15:0] cache_y,cache_word_x;
    reg cache_format;
    reg [2:0] byte_lane;
    reg rgb565;
    reg [15:0] request_x,request_y;
    reg [31:0] request_base,request_pitch;
    reg [47:0] row_offset;
    reg [63:0] address;
    wire [15:0] input_word_x=format_rgb565 ? (s_x>>2) : (s_x>>1);
    wire [2:0] input_lane=format_rgb565 ? {s_x[1:0],1'b0} : {s_x[0],2'b00};
    wire coordinate_hit=cache_valid && base_addr[2:0]==0 && pitch_bytes[2:0]==0 &&
        pitch_bytes!=0 && base_addr==cache_base && pitch_bytes==cache_pitch &&
        format_rgb565==cache_format && s_y==cache_y && input_word_x==cache_word_x;
    // Register coordinates before multiplication and register the row product
    // before address addition; no sampler->multiply->compare path in one cycle.
    wire invalid_address = |address[63:32] ||
        (rgb565 ? (request_base[0] || request_pitch[0]) : (|request_base[1:0] || |request_pitch[1:0])) ||
        request_pitch == 0;
    assign s_ready = !reset && !clear_cache && state == IDLE;
    assign m_valid = !reset && state == RESPONSE;
    assign m_axi_arvalid = !reset && state == ADDRESS;
    assign m_axi_arlen = 0;
    assign m_axi_arsize = 3; // 8 bytes, same beat width as vendor aq_axi_master.
    assign m_axi_arburst = 1;
    assign m_axi_rready = !reset && (state == DATA || state == DRAIN);
    function [23:0] unpack_pixel;
        input [63:0] word; input [2:0] lane; input fmt;
        reg [63:0] shifted;
        reg [15:0] p;
        begin
            shifted = word >> (lane*8); p = shifted[15:0];
            // RGB565 -> RGB888 uses bit replication, not zero-fill.
            unpack_pixel = fmt ? {p[15:11],p[15:13],p[10:5],p[10:9],p[4:0],p[4:2]} : shifted[23:0];
        end
    endfunction
    always @(posedge clk) begin
        if (reset) begin
            state <= IDLE; cache_valid <= 0; cache_addr <= 0;
            cache_data <= 0; byte_lane <= 0; rgb565 <= 0;
            cache_base<=0;cache_pitch<=0;cache_y<=0;cache_word_x<=0;cache_format<=0;
            m_rgb <= 0; m_error <= 0; m_axi_araddr <= 0;
            request_x<=0;request_y<=0;request_base<=0;request_pitch<=0;
            row_offset<=0;address<=0;
        end else begin
            if (clear_cache) cache_valid <= 0;
            case(state)
                IDLE: if (s_valid && s_ready) begin
                    request_x<=s_x;request_y<=s_y;
                    request_base<=base_addr;request_pitch<=pitch_bytes;
                    rgb565<=format_rgb565;
                    if(coordinate_hit)begin
                        m_error<=0;m_rgb<=unpack_pixel(cache_data,input_lane,format_rgb565);state<=RESPONSE;
                    end else state<=ROW_OFFSET;
                end
                ROW_OFFSET: begin row_offset<=request_y*request_pitch;state<=ADD_OFFSET;end
                ADD_OFFSET: begin
                    address <= {32'd0,request_base} + {16'd0,row_offset} +
                        ({48'd0,request_x} << (rgb565 ? 1 : 2));
                    state<=CHECK_ADDRESS;
                end
                CHECK_ADDRESS: begin
                    byte_lane <= address[2:0];
                    m_error <= 0;
                    if (invalid_address) begin m_error <= 1; m_rgb <= 0; state <= RESPONSE; end
                    else if (cache_valid && cache_addr == {address[31:3],3'b000}) begin
                        m_rgb <= unpack_pixel(cache_data,address[2:0],rgb565);
                        cache_base<=request_base;cache_pitch<=request_pitch;cache_y<=request_y;
                        cache_word_x<=rgb565 ? (request_x>>2) : (request_x>>1);cache_format<=rgb565;
                        state <= RESPONSE;
                    end else begin m_axi_araddr <= {address[31:3],3'b000}; state <= ADDRESS; end
                end
                ADDRESS: if (m_axi_arready) state <= DATA;
                DATA: if (m_axi_rvalid) begin
                    m_error <= (m_axi_rresp != 0) || !m_axi_rlast;
                    m_rgb <= unpack_pixel(m_axi_rdata,byte_lane,rgb565);
                    cache_valid <= m_axi_rresp == 0 && m_axi_rlast;
                    cache_addr <= m_axi_araddr; cache_data <= m_axi_rdata;
                    cache_base<=request_base;cache_pitch<=request_pitch;cache_y<=request_y;
                    cache_word_x<=rgb565 ? (request_x>>2) : (request_x>>1);cache_format<=rgb565;
                    // Unexpected multi-beat response must be fully drained
                    // before another command can reuse this AXI ID.
                    state <= m_axi_rlast ? RESPONSE : DRAIN;
                end
                DRAIN: if (m_axi_rvalid && m_axi_rlast) state <= RESPONSE;
                RESPONSE: if (m_ready) state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end
endmodule
