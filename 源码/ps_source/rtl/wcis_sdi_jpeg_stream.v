`timescale 1ns/1ps
// Independent live-video consumer. SDI has no ready; admit a whole frame only
// when the encoder is idle, otherwise skip it. The first overflow invalidates
// that frame. JPEG EOF is withheld until the source frame's geometry commits.
// Uses the pinned upstream asynchronous FIFO and existing JPEG compressor.
module wcis_sdi_jpeg_stream #(
    parameter integer IMAGE_WIDTH=1920, IMAGE_HEIGHT=1080,
    parameter integer QUALITY=75, PIXEL_FIFO_DEPTH=8192,
    parameter integer LOGIC_HZ=200000000
)(
    input wire cam_clk,clk,reset,enable,cam_locked,
    input wire cam_vsync,cam_de,input wire [23:0] cam_rgb,
    output wire [7:0] m_data,output wire m_valid,m_sof,m_last,
    input wire m_ready,input wire downstream_idle,
    output reg [31:0] m_frame_id,output wire abort_frame,
    output wire idle,output wire [31:0] frames_encoded,
    output reg [31:0] frames_rejected
);
    localparam integer PIXELS=IMAGE_WIDTH*IMAGE_HEIGHT;
    (* ASYNC_REG="TRUE" *) reg [2:0] cam_reset_sync,logic_reset_sync;
    always @(posedge cam_clk or posedge reset)
        if(reset)cam_reset_sync<=7;else cam_reset_sync<={cam_reset_sync[1:0],1'b0};
    always @(posedge clk or posedge reset)
        if(reset)logic_reset_sync<=7;else logic_reset_sync<={logic_reset_sync[1:0],1'b0};
    wire cam_reset=cam_reset_sync[2],logic_reset=logic_reset_sync[2];
    (* ASYNC_REG="TRUE" *) reg [1:0] idle_sync,enable_sync;
    reg vs_d,de_d,selected,selected_once,source_bad;
    reg [31:0] source_frame,pixels,columns,rows;
    wire source_start=cam_vsync&&!vs_d;
    wire source_end=!cam_vsync&&vs_d;
    wire descriptor_ready;
    wire admission=enable_sync[1]&&idle_sync[1]&&descriptor_ready&&cam_locked;
    wire select_now=source_start ? admission : selected;
    wire [31:0] pixel_number=source_start ? 0 : pixels;
    wire [31:0] source_id=source_start ? source_frame+1 : source_frame;
    wire fifo_write=select_now&&cam_de&&cam_locked&&pixel_number<PIXELS;
    wire fifo_ready;
    reg descriptor_valid;
    reg [32:0] descriptor;
    wire descriptor_out_valid;wire [32:0] descriptor_out;
    wcis_cdc_mailbox #(.WIDTH(33)) validation(
        .reset(reset),.s_clk(cam_clk),.m_clk(clk),.s_valid(descriptor_valid),.s_ready(descriptor_ready),
        .s_data(descriptor),.m_valid(descriptor_out_valid),.m_ready(1'b1),.m_data(descriptor_out));
    always @(posedge cam_clk) begin
        if(cam_reset) begin
            idle_sync<=0;enable_sync<=0;vs_d<=0;de_d<=0;
            selected<=0;selected_once<=0;source_bad<=0;source_frame<=0;
            pixels<=0;columns<=0;rows<=0;descriptor_valid<=0;descriptor<=0;
        end else begin
            idle_sync<={idle_sync[0],idle};enable_sync<={enable_sync[0],enable};
            vs_d<=cam_vsync;de_d<=cam_de;
            if(descriptor_valid&&descriptor_ready)descriptor_valid<=0;
            if(source_start) begin
                source_frame<=source_frame+1;selected<=admission;selected_once<=admission;
                source_bad<=0;pixels<=0;columns<=0;rows<=0;
            end
            if(select_now&&cam_de) begin
                pixels<=pixel_number+1;columns<=(source_start ? 0 : columns)+1;
                if(!fifo_ready||!cam_locked||pixel_number>=PIXELS)begin
                    source_bad<=1;selected<=0;
                end
            end
            if(selected_once&&!cam_de&&de_d) begin
                if(columns!=IMAGE_WIDTH)source_bad<=1;
                columns<=0;rows<=rows+1;
            end
            if(source_end&&selected_once) begin
                // The descriptor slot was reserved at admission and no other
                // source frame can be admitted until this one has retired.
                descriptor<={(!source_bad&&cam_locked&&pixels==PIXELS&&
                    rows+(de_d ? 1 : 0)==IMAGE_HEIGHT&&(!de_d||columns==IMAGE_WIDTH)),source_frame};
                descriptor_valid<=1;selected<=0;selected_once<=0;
            end
        end
    end
    wire [23:0] pixel_data;wire pixel_valid,pixel_ready,pixel_last,pixel_sof;
    wire [31:0] pixel_frame;
    axis_async_fifo #(.DEPTH(PIXEL_FIFO_DEPTH),.DATA_WIDTH(24),.KEEP_ENABLE(0),
        .ID_ENABLE(1),.ID_WIDTH(32),.USER_ENABLE(1),.USER_WIDTH(1),.FRAME_FIFO(0)) pixels_cdc(
        .s_clk(cam_clk),.s_rst(cam_reset),.s_axis_tdata(cam_rgb),.s_axis_tkeep(1'b1),
        .s_axis_tvalid(fifo_write),.s_axis_tready(fifo_ready),.s_axis_tlast(pixel_number==PIXELS-1),
        .s_axis_tid(source_id),.s_axis_tdest(8'd0),.s_axis_tuser(pixel_number==0),
        .m_clk(clk),.m_rst(logic_reset),.m_axis_tdata(pixel_data),.m_axis_tvalid(pixel_valid),
        .m_axis_tready(pixel_ready),.m_axis_tlast(pixel_last),.m_axis_tid(pixel_frame),.m_axis_tuser(pixel_sof),
        .s_pause_req(1'b0),.m_pause_req(1'b0));
    localparam WAIT=0,START=1,FEED=2,FINISH=3,DROP=4;
    reg [2:0] state;
    reg [31:0] consumed,deadline;
    reg validation_known,validation_good;
    wire encoder_cmd_ready,encoder_ready,encoder_busy,encoder_abort;
    wire [7:0] jpeg_data;wire jpeg_valid,jpeg_sof,jpeg_last;
    wire [31:0] encoder_frame;
    wire mismatch=state==FEED&&pixel_valid&&(pixel_frame!=m_frame_id||(pixel_sof&&consumed!=0));
    wire invalid_end=descriptor_out_valid&&descriptor_out[31:0]==m_frame_id&&!descriptor_out[32]&&state!=WAIT;
    wire timeout_frame=state!=WAIT&&state!=DROP&&deadline>=LOGIC_HZ/10;
    wire cancel=mismatch||invalid_end||timeout_frame;
    assign abort_frame=(encoder_abort||cancel)&&state!=DROP&&state!=WAIT;
    reg idle_registered;
    assign idle=idle_registered;
    assign pixel_ready=(state==WAIT&&!pixel_sof)||(state==FEED&&!mismatch&&encoder_ready)||(state==DROP);
    assign m_data=jpeg_data;assign m_sof=jpeg_sof;
    assign m_last=jpeg_last;
    // Do not advertise EOF at all until capture geometry has been checked.
    assign m_valid=jpeg_valid&&(!jpeg_last||(validation_known&&validation_good))&&!cancel;
    wire encoder_output_ready=m_ready&&(!jpeg_last||(validation_known&&validation_good))&&!cancel;
    wcis_jpeg_compressor #(.IMG_WIDTH(IMAGE_WIDTH),.IMG_HEIGHT(IMAGE_HEIGHT),.QUALITY(QUALITY),.PIPELINED_FIFO(1)) encoder(
        .clk(clk),.reset(logic_reset),.cmd_valid(state==START),.cmd_ready(encoder_cmd_ready),
        .cmd_frame_id(m_frame_id),.s_rgb(pixel_data),.s_valid(state==FEED&&pixel_valid&&!mismatch),
        .s_ready(encoder_ready),.abort_frame(cancel),.m_data(jpeg_data),.m_valid(jpeg_valid),
        .m_ready(encoder_output_ready),.m_sof(jpeg_sof),.m_last(jpeg_last),.frame_id(encoder_frame),
        .frame_abort(encoder_abort),.busy(encoder_busy),.frames_done(frames_encoded));
    always @(posedge clk) begin
        if(logic_reset) begin
            state<=WAIT;m_frame_id<=0;consumed<=0;deadline<=0;
            validation_known<=0;validation_good<=0;frames_rejected<=0;idle_registered<=0;
        end else begin
            // The admission indication crosses into the camera domain. Register
            // the whole condition here so a combinational glitch cannot start
            // a source frame between encoder/FIFO state transitions.
            idle_registered<=state==WAIT&&!pixel_valid&&encoder_cmd_ready&&downstream_idle;
            if(state!=WAIT)deadline<=deadline+1;
            if(descriptor_out_valid&&descriptor_out[31:0]==m_frame_id)begin
                validation_known<=1;validation_good<=descriptor_out[32];
            end
            if(cancel||encoder_abort) begin
                state<=DROP;
                if(state!=DROP&&state!=WAIT)frames_rejected<=frames_rejected+1;
            end
            else case(state)
                WAIT:if(pixel_valid&&pixel_sof&&encoder_cmd_ready&&downstream_idle)begin
                    m_frame_id<=pixel_frame;state<=START;consumed<=0;deadline<=0;
                    validation_known<=0;validation_good<=0;
                end
                START:if(encoder_cmd_ready)state<=FEED;
                FEED:if(pixel_valid&&pixel_ready) begin
                    consumed<=consumed+1;
                    if(pixel_last)state<=FINISH;
                end
                FINISH:if(!encoder_busy&&downstream_idle)state<=WAIT;
                DROP:if(!pixel_valid&&encoder_cmd_ready&&downstream_idle)state<=WAIT;
                default:state<=DROP;
            endcase
        end
    end
endmodule
