`timescale 1ns/1ps
// WJP1/IPv4-UDP payload packetizer. Metadata is sampled with JPEG SOF.
// No output packet exceeds HEADER_BYTES+CHUNK_BYTES. Complete datagrams remain
// stable under backpressure; an encoder abort is emitted after an in-flight
// datagram, never by truncating its already-advertised UDP length.
module wcis_jpeg_udp_packetizer #(
    parameter integer CHUNK_BYTES = 1400,
    parameter integer IMAGE_WIDTH = 1920,
    parameter integer IMAGE_HEIGHT = 1080,
    parameter integer MAX_FRAME_BYTES = 8*1024*1024
)(
    input wire clk, reset,
    input wire [31:0] session_id,
    input wire [31:0] s_frame_id,
    input wire [7:0] s_data,
    input wire s_valid, s_sof, s_last,
    output wire s_ready,
    input wire abort_frame,
    output wire m_hdr_valid,
    input wire m_hdr_ready,
    output wire [15:0] m_udp_length,
    output reg [7:0] m_data,
    output wire m_valid,
    input wire m_ready,
    output wire m_last,
    output wire busy,
    output reg protocol_error,
    output reg [31:0] frames_done, frames_aborted, packets_sent
);
    localparam HEADER_BYTES=40;
    localparam COLLECT=0, UDP_HEADER=1, APP_HEADER=2, PAYLOAD=3;
    reg [1:0] state;
    // A synchronous RAM FIFO avoids distributing one counter address to every
    // LUT RAM bank. The packet's application header hides the read latency.
    localparam PAYLOAD_DEPTH = CHUNK_BYTES < 16 ? 16 : (1 << $clog2(CHUNK_BYTES));
    reg [15:0] count, position;
    reg [5:0] header_position;
    reg [31:0] current_session, current_frame, offset;
    reg [31:0] packet_offset, packet_total, packet_crc;
    reg [31:0] crc;
    reg [7:0] flags;
    reg active, abort_pending, packet_end;
    wire push=s_valid && s_ready;
    wire output_pop=m_valid && m_ready;
    wire last_byte=state==PAYLOAD && position==count-1;
    wire last_header=state==APP_HEADER && header_position==HEADER_BYTES-1;
    wire chunk_ready, chunk_valid;
    wire [7:0] chunk_data;
    wire malformed_input=(!active && (!s_sof || session_id==0)) ||
                         (active && s_sof) || offset+count>=MAX_FRAME_BYTES;
    // An already-advertised UDP packet must finish before an abort can flush
    // the partial next chunk. Never reset the FIFO during PAYLOAD.
    wire discard_partial=state==COLLECT && (abort_pending || (abort_frame && active));
    axis_fifo #(.DEPTH(PAYLOAD_DEPTH),.DATA_WIDTH(8),.KEEP_ENABLE(0),
        .LAST_ENABLE(0),.ID_ENABLE(0),.DEST_ENABLE(0),.USER_ENABLE(0),
        .RAM_PIPELINE(1),.OUTPUT_FIFO_ENABLE(0),.FRAME_FIFO(0),
        .DROP_WHEN_FULL(0),.MARK_WHEN_FULL(0)) chunk_storage (
        .clk(clk),.rst(reset || discard_partial),
        .s_axis_tdata(s_data),.s_axis_tkeep(1'b1),
        .s_axis_tvalid(s_valid && state==COLLECT && !abort_pending && !abort_frame && !malformed_input),
        .s_axis_tready(chunk_ready),.s_axis_tlast(1'b0),
        .s_axis_tid(8'd0),.s_axis_tdest(8'd0),.s_axis_tuser(1'b0),
        .m_axis_tdata(chunk_data),.m_axis_tvalid(chunk_valid),
        .m_axis_tready(state==PAYLOAD && m_ready),.pause_req(1'b0));
    function [31:0] crc_byte;
        input [31:0] previous;
        input [7:0] value;
        reg [31:0] c;
        integer i;
        begin
            c=previous ^ value;
            for(i=0;i<8;i=i+1) c=c[0] ? (c>>1)^32'hedb88320 : c>>1;
            crc_byte=c;
        end
    endfunction
    assign s_ready=state==COLLECT && !abort_pending && !abort_frame && chunk_ready;
    assign m_hdr_valid=state==UDP_HEADER;
    // UDP length includes its own 8-byte header.
    assign m_udp_length=8+HEADER_BYTES+count;
    assign m_valid=state==APP_HEADER || (state==PAYLOAD && chunk_valid);
    assign m_last=(last_header && count==0) || last_byte;
    assign busy=active || state!=COLLECT || abort_pending;
    always @* begin
        m_data=0;
        if(state==PAYLOAD) m_data=chunk_data;
        else case(header_position)
            0:m_data="W"; 1:m_data="J"; 2:m_data="P"; 3:m_data="1";
            4:m_data=1; 5:m_data=flags; 6:m_data=0; 7:m_data=HEADER_BYTES;
            8:m_data=current_session[31:24]; 9:m_data=current_session[23:16];
            10:m_data=current_session[15:8]; 11:m_data=current_session[7:0];
            12:m_data=current_frame[31:24]; 13:m_data=current_frame[23:16];
            14:m_data=current_frame[15:8]; 15:m_data=current_frame[7:0];
            16:m_data=packet_offset[31:24]; 17:m_data=packet_offset[23:16];
            18:m_data=packet_offset[15:8]; 19:m_data=packet_offset[7:0];
            20:m_data=packet_total[31:24]; 21:m_data=packet_total[23:16];
            22:m_data=packet_total[15:8]; 23:m_data=packet_total[7:0];
            24:m_data=count[15:8]; 25:m_data=count[7:0];
            26:m_data=(IMAGE_WIDTH>>8)&255; 27:m_data=IMAGE_WIDTH&255;
            28:m_data=(IMAGE_HEIGHT>>8)&255; 29:m_data=IMAGE_HEIGHT&255;
            30:m_data=0; 31:m_data=0;
            32:m_data=packet_crc[31:24]; 33:m_data=packet_crc[23:16];
            34:m_data=packet_crc[15:8]; 35:m_data=packet_crc[7:0];
            36:m_data="J";37:m_data="P";38:m_data="E";39:m_data="G";
            default:m_data=0;
        endcase
    end
    always @(posedge clk) begin
        if(reset) begin
            state<=COLLECT;count<=0;position<=0;header_position<=0;
            current_session<=0;current_frame<=0;offset<=0;packet_offset<=0;
            packet_total<=0;packet_crc<=0;crc<=32'hffffffff;flags<=0;
            active<=0;abort_pending<=0;packet_end<=0;protocol_error<=0;
            frames_done<=0;frames_aborted<=0;packets_sent<=0;
        end else begin
            // A later SOF cannot replace an in-flight frame. The producer must
            // issue abort_frame first; malformed input fails closed.
            if(abort_frame && active) abort_pending<=1;
            case(state)
                COLLECT: begin
                    if(abort_pending || (abort_frame && active)) begin
                        count<=0;packet_offset<=offset;packet_total<=0;
                        packet_crc<=0;flags<=4;packet_end<=0;
                        abort_pending<=0;state<=UDP_HEADER;
                        frames_aborted<=frames_aborted+1;
                    end else if(push) begin
                        if(malformed_input) begin
                            protocol_error<=1;
                            if(active) abort_pending<=1;
                        end else begin
                            if(!active) begin
                                current_session<=session_id;current_frame<=s_frame_id;
                                active<=1;offset<=0;
                            end
                            crc<=crc_byte(crc,s_data);count<=count+1;
                            if(count==CHUNK_BYTES-1 || s_last) begin
                                packet_offset<=active ? offset : 0;
                                packet_total<=s_last ? ((active ? offset : 0)+count+1) : 0;
                                packet_crc<=~crc_byte(crc,s_data);
                                flags<=((!active || offset==0) ? 1 : 0) | (s_last ? 2 : 0);
                                packet_end<=s_last;state<=UDP_HEADER;
                            end
                        end
                    end
                end
                UDP_HEADER: if(m_hdr_ready) begin state<=APP_HEADER;header_position<=0;end
                APP_HEADER: if(output_pop) begin
                    if(last_header) begin
                        position<=0;
                        if(count!=0) state<=PAYLOAD;
                        else begin
                            packets_sent<=packets_sent+1;active<=0;offset<=0;
                            count<=0;crc<=32'hffffffff;state<=COLLECT;
                        end
                    end else header_position<=header_position+1;
                end
                PAYLOAD: if(output_pop) begin
                    if(last_byte) begin
                        packets_sent<=packets_sent+1;offset<=packet_offset+count;
                        count<=0;crc<=32'hffffffff;state<=COLLECT;
                        if(packet_end) begin
                            active<=0;offset<=0;frames_done<=frames_done+1;
                        end
                    end else position<=position+1;
                end
            endcase
        end
    end
    initial begin
        if(CHUNK_BYTES<1 || CHUNK_BYTES+HEADER_BYTES>1472 || MAX_FRAME_BYTES<CHUNK_BYTES)
            $error("Invalid IPv4/UDP fragmentation bounds");
    end
endmodule
