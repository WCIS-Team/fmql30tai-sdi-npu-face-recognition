`timescale 1ns/1ps
// JPG1 register page + bounded 512-bit native PL-DDR DMA. Encoding runs at GP
// clock, with two input lines and one outstanding read. No raw PS-side encode.
module wcis_jpeg_customop #(
    parameter IMG_WIDTH=1920, IMG_HEIGHT=1080, QUALITY=75
)(
    input wire [31:0] itf_ra_awaddr,itf_ra_awdata,
    input wire itf_ra_awvalid,output wire itf_ra_awready,
    input wire [31:0] itf_ra_araddr,input wire itf_ra_arvalid,
    output wire itf_ra_arready,output reg [31:0] itf_ra_rdata,
    output reg itf_ra_rvalid,input wire itf_ra_rready,
    output wire [31:0] itf_awaddr,output wire [511:0] itf_awdata,
    output wire [71:0] itf_awinfo,output wire itf_awvalid,input wire itf_awready,
    output wire [31:0] itf_araddr,output wire [31:0] itf_arinfo,
    output wire itf_arvalid,input wire itf_arready,
    input wire [511:0] itf_rdata,input wire [31:0] itf_rinfo,
    input wire itf_rvalid,output wire itf_rready,
    input wire clk,ra_clk,rst_n,ra_rst_n
);
    wire reset=!rst_n || !ra_rst_n;
    (* ASYNC_REG="TRUE" *) reg [1:0] reset_sync;
    always @(posedge ra_clk or posedge reset)
        if(reset) reset_sync<=3; else reset_sync<={reset_sync[0],1'b0};
    wire gp_reset=reset_sync[1];
    localparam PIXELS=IMG_WIDTH*IMG_HEIGHT;
    reg [31:0] cfg_frame,cfg_src,cfg_dst,cfg_capacity,cfg_format;
    reg busy,done,rejected,launch_pending,launched,encoded_eof;
    reg [3:0] error;
    reg [31:0] completed_frame,bytes_encoded,job_cycles,last_cycles;
    reg [31:0] input_wait,output_wait,read_blocks,write_blocks;
    wire [31:0] input_bytes=cfg_format[0] ? PIXELS*4 : PIXELS*2;
    wire [32:0] src_end={1'b0,cfg_src}+{1'b0,input_bytes};
    wire [32:0] dst_end={1'b0,cfg_dst}+{1'b0,cfg_capacity};
    wire valid_storage=cfg_src[5:0]==0 && cfg_dst[5:0]==0 &&
        cfg_capacity>=64 && cfg_capacity[5:0]==0 && cfg_format<=1 &&
        src_end<=33'h08000000 && dst_end<=33'h08000000 &&
        (src_end<={1'b0,cfg_dst} || dst_end<={1'b0,cfg_src});

    reg [31:0] fetch_offset,pixel_index,dst_pointer;
    reg read_outstanding;
    reg [511:0] lines[0:1];
    reg line_rd,line_wr;
    reg [1:0] line_count;
    reg [4:0] lane;
    wire req_ready,rsp_valid;
    wire [511:0] rsp_data;
    wire req_valid=busy && error==0 && !read_outstanding &&
                   line_count<2 && fetch_offset<input_bytes;
    wire rsp_ready=read_outstanding;
    wire input_push=rsp_valid && rsp_ready && error==0;
    wire [511:0] pixel_line=lines[line_rd];
    wire [31:0] pixel_word=pixel_line >> (cfg_format[0] ? lane*32 : lane*16);
    wire [15:0] p565=pixel_word[15:0];
    wire [23:0] rgb=cfg_format[0] ? pixel_word[23:0] :
        {p565[15:11],p565[15:13],p565[10:5],p565[10:9],p565[4:0],p565[4:2]};
    wire pixel_valid=busy && launched && error==0 && line_count!=0 && pixel_index<PIXELS;
    wire pixel_ready;
    wire pixel_pop=pixel_valid && pixel_ready;
    wire line_pop=pixel_pop && lane==(cfg_format[0] ? 15 : 31);
    wcis_cdc_mailbox #(.WIDTH(32)) read_request(
        .reset(reset),.s_clk(ra_clk),.m_clk(clk),.s_valid(req_valid),.s_ready(req_ready),
        .s_data(cfg_src+fetch_offset),.m_valid(itf_arvalid),.m_ready(itf_arready),.m_data(itf_araddr));
    assign itf_arinfo=1;
    wcis_cdc_mailbox #(.WIDTH(512)) read_response(
        .reset(reset),.s_clk(clk),.m_clk(ra_clk),.s_valid(itf_rvalid),.s_ready(itf_rready),
        .s_data(itf_rdata),.m_valid(rsp_valid),.m_ready(rsp_ready),.m_data(rsp_data));

    wire encoder_cmd_ready,encoder_busy,encoder_abort_event,encoder_overflow;
    reg encoder_abort;
    wire [7:0] jpeg_data;
    wire jpeg_valid,jpeg_ready,jpeg_sof,jpeg_last;
    wire [31:0] encoder_frame,encoder_done,encoder_aborted,encoder_overflows;
    wire [31:0] encoder_bytes,encoder_cycles;
    wcis_jpeg_compressor #(.IMG_WIDTH(IMG_WIDTH),.IMG_HEIGHT(IMG_HEIGHT),.QUALITY(QUALITY)) encoder(
        .clk(ra_clk),.reset(gp_reset),.cmd_valid(launch_pending),.cmd_ready(encoder_cmd_ready),
        .cmd_frame_id(cfg_frame),.s_rgb(rgb),.s_valid(pixel_valid),.s_ready(pixel_ready),
        .abort_frame(encoder_abort),.m_data(jpeg_data),.m_valid(jpeg_valid),.m_ready(jpeg_ready),
        .m_sof(jpeg_sof),.m_last(jpeg_last),.frame_id(encoder_frame),.frame_abort(encoder_abort_event),
        .busy(encoder_busy),.overflow_sticky(encoder_overflow),.frames_done(encoder_done),
        .frames_aborted(encoder_aborted),.fifo_overflows(encoder_overflows),
        .last_frame_bytes(encoder_bytes),.last_frame_cycles(encoder_cycles));

    reg [511:0] output_pack;
    reg [63:0] byte_mask;
    reg [5:0] byte_lane;
    reg write_pending;
    wire write_mail_ready;
    wire [607:0] native_write;
    assign jpeg_ready=busy && error==0 && !write_pending && bytes_encoded<cfg_capacity;
    wire byte_pop=jpeg_valid && jpeg_ready;
    wcis_cdc_mailbox #(.WIDTH(608)) write_request(
        .reset(reset),.s_clk(ra_clk),.m_clk(clk),.s_valid(write_pending),.s_ready(write_mail_ready),
        .s_data({dst_pointer,output_pack,byte_mask}),.m_valid(itf_awvalid),.m_ready(itf_awready),.m_data(native_write));
    assign itf_awaddr=native_write[607:576];
    assign itf_awdata=native_write[575:64];
    assign itf_awinfo={1'b0,native_write[63:0],6'd0,1'b1};
    assign itf_ra_awready=!gp_reset;
    assign itf_ra_arready=!gp_reset && !itf_ra_rvalid;

    always @(posedge ra_clk or posedge gp_reset) begin
        if(gp_reset) begin
            cfg_frame<=0;cfg_src<=0;cfg_dst<=0;cfg_capacity<=0;cfg_format<=0;
            busy<=0;done<=0;rejected<=0;error<=0;launch_pending<=0;launched<=0;encoded_eof<=0;
            completed_frame<=0;bytes_encoded<=0;job_cycles<=0;last_cycles<=0;
            input_wait<=0;output_wait<=0;read_blocks<=0;write_blocks<=0;
            fetch_offset<=0;pixel_index<=0;dst_pointer<=0;read_outstanding<=0;
            line_rd<=0;line_wr<=0;line_count<=0;lane<=0;
            output_pack<=0;byte_mask<=0;byte_lane<=0;write_pending<=0;encoder_abort<=0;
            itf_ra_rdata<=0;itf_ra_rvalid<=0;
        end else begin
            encoder_abort<=0;
            if(itf_ra_rvalid && itf_ra_rready) itf_ra_rvalid<=0;
            if(itf_ra_arvalid && itf_ra_arready) begin
                itf_ra_rvalid<=1;
                case(itf_ra_araddr[7:2])
                    0: itf_ra_rdata<=32'h4a504731; // JPG1
                    1: itf_ra_rdata<={24'd0,error,rejected,1'b0,done,busy};
                    2: itf_ra_rdata<=completed_frame;
                    3: itf_ra_rdata<=bytes_encoded;
                    4: itf_ra_rdata<=cfg_frame;
                    5: itf_ra_rdata<=cfg_src;
                    6: itf_ra_rdata<=cfg_dst;
                    7: itf_ra_rdata<=cfg_capacity;
                    8: itf_ra_rdata<=cfg_format;
                    9: itf_ra_rdata<=IMG_WIDTH;
                    10: itf_ra_rdata<=IMG_HEIGHT;
                    11: itf_ra_rdata<=QUALITY;
                    12: itf_ra_rdata<=last_cycles;
                    13: itf_ra_rdata<=encoder_cycles;
                    14: itf_ra_rdata<=input_wait;
                    15: itf_ra_rdata<=output_wait;
                    16: itf_ra_rdata<=read_blocks;
                    17: itf_ra_rdata<=write_blocks;
                    default: itf_ra_rdata<=0;
                endcase
            end
            if(itf_ra_awvalid && itf_ra_awready) begin
                if(busy) rejected<=1;
                else case(itf_ra_awaddr[7:2])
                    0: if(itf_ra_awdata[0]) begin
                        done<=0;rejected<=0;error<=0;
                        bytes_encoded<=0;job_cycles<=0;last_cycles<=0;
                        input_wait<=0;output_wait<=0;read_blocks<=0;write_blocks<=0;
                        completed_frame<=cfg_frame;
                        if(!valid_storage) begin done<=1;error<=1;end
                        else begin
                            busy<=1;launch_pending<=1;launched<=0;encoded_eof<=0;
                            fetch_offset<=0;pixel_index<=0;dst_pointer<=cfg_dst;
                            line_rd<=0;line_wr<=0;line_count<=0;lane<=0;
                            output_pack<=0;byte_mask<=0;byte_lane<=0;write_pending<=0;
                        end
                    end
                    4: cfg_frame<=itf_ra_awdata;
                    5: cfg_src<=itf_ra_awdata;
                    6: cfg_dst<=itf_ra_awdata;
                    7: cfg_capacity<=itf_ra_awdata;
                    8: cfg_format<=itf_ra_awdata;
                    default: ;
                endcase
            end
            if(busy) begin
                job_cycles<=job_cycles+1;
                if(launched && pixel_index<PIXELS && !pixel_valid) input_wait<=input_wait+1;
                if(jpeg_valid && !jpeg_ready) output_wait<=output_wait+1;
                if(launch_pending && encoder_cmd_ready) begin launch_pending<=0;launched<=1;end
                if(req_valid && req_ready) begin
                    fetch_offset<=fetch_offset+64;read_outstanding<=1;read_blocks<=read_blocks+1;
                end
                if(rsp_valid && rsp_ready) read_outstanding<=0;
                if(error==0) begin
                    case({input_push,line_pop})
                        2'b10: line_count<=line_count+1;
                        2'b01: line_count<=line_count-1;
                        default: ;
                    endcase
                    if(input_push) begin lines[line_wr]<=rsp_data;line_wr<=!line_wr;end
                    if(pixel_pop) begin
                        pixel_index<=pixel_index+1;
                        if(line_pop) begin line_rd<=!line_rd;lane<=0;end
                        else lane<=lane+1;
                    end
                    if(byte_pop) begin
                        output_pack[byte_lane*8 +: 8]<=jpeg_data;
                        byte_mask[byte_lane]<=1;
                        bytes_encoded<=bytes_encoded+1;
                        if(byte_lane==63 || jpeg_last) write_pending<=1;
                        else byte_lane<=byte_lane+1;
                        if(jpeg_last) encoded_eof<=1;
                    end
                    if(encoder_abort_event || (jpeg_valid && bytes_encoded>=cfg_capacity)) begin
                        error<=encoder_abort_event ? 2 : 3;encoder_abort<=1;launch_pending<=0;
                    end
                end else line_count<=0;
                if(write_pending && write_mail_ready) begin
                    write_pending<=0;byte_lane<=0;byte_mask<=0;output_pack<=0;
                    dst_pointer<=dst_pointer+64;write_blocks<=write_blocks+1;
                end
                // Mailbox readiness includes destination consumption/ack. A
                // native write has no B response, exactly as the vendor path.
                if(!launch_pending && (encoded_eof || (error!=0 && !encoder_busy)) &&
                   !write_pending && write_mail_ready && !read_outstanding && req_ready) begin
                    busy<=0;done<=1;last_cycles<=job_cycles+1;
                end
            end
        end
    end
endmodule
