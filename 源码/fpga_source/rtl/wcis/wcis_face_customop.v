`timescale 1ns/1ps
// Vendor CustomOp integration. Preserve the original adder register page and
// operation, add FACE at offset 0x2000. Both clients use the existing 512-bit
// PL-DDR port; AI_Mate, pins, clocks and existing camera interfaces are retained.
module wcis_face_customop(
    input wire [31:0] itf_ra_awaddr,itf_ra_awdata,
    input wire itf_ra_awvalid,output wire itf_ra_awready,
    input wire [31:0] itf_ra_araddr,input wire itf_ra_arvalid,
    output wire itf_ra_arready,output wire [31:0] itf_ra_rdata,
    output wire itf_ra_rvalid,input wire itf_ra_rready,
    output wire [31:0] itf_awaddr,output wire [511:0] itf_awdata,
    output wire [71:0] itf_awinfo,output wire itf_awvalid,input wire itf_awready,
    output wire [31:0] itf_araddr,output wire [31:0] itf_arinfo,
    output wire itf_arvalid,input wire itf_arready,
    input wire [511:0] itf_rdata,input wire [31:0] itf_rinfo,
    input wire itf_rvalid,output wire itf_rready,
    input wire clk,ra_clk,rst_n,ra_rst_n
);
    wire reset=!rst_n || !ra_rst_n;
    (* ASYNC_REG="TRUE" *) reg [1:0] gp_reset_sync,hp_reset_sync;
    always @(posedge ra_clk or posedge reset)
        if(reset) gp_reset_sync<=3;else gp_reset_sync<={gp_reset_sync[0],1'b0};
    always @(posedge clk or posedge reset)
        if(reset) hp_reset_sync<=3;else hp_reset_sync<={hp_reset_sync[0],1'b0};
    wire gp_reset=gp_reset_sync[1],hp_reset=hp_reset_sync[1];
    wire face_write=itf_ra_awaddr[17:8]==10'h020;
    wire face_read=itf_ra_araddr[17:8]==10'h020;
    reg read_pending,read_face,face_rvalid;
    reg [31:0] face_rdata;
    wire old_awready,old_arready,old_rvalid;
    wire [31:0] old_rdata;
    wire [31:0] old_awaddr,old_araddr;
    wire [63:0] old_awdata;
    wire old_awvalid,old_awready_mem,old_arvalid,old_arready_mem,old_rready;
    reg memory_read_busy,memory_read_face;
    reg write_hold,write_owner,read_hold,read_owner;
    wire face_native_arvalid,face_native_arready,face_native_rready;
    wire [31:0] face_native_araddr;
    wire face_native_awvalid,face_native_awready;
    wire [607:0] face_native_write;
    wire old_memory_rvalid=itf_rvalid && memory_read_busy && !memory_read_face;
    wire select_write_face=write_hold ? write_owner : face_native_awvalid;
    wire select_read_face=read_hold ? read_owner : face_native_arvalid;
    assign itf_ra_awready=face_write ? !gp_reset : old_awready;
    assign itf_ra_arready=!gp_reset && !read_pending && (face_read ? !face_rvalid : old_arready);
    assign itf_ra_rvalid=read_pending && (read_face ? face_rvalid : old_rvalid);
    assign itf_ra_rdata=read_face ? face_rdata : old_rdata;
    adder_top legacy_adder(
        .itf_ra_awaddr(itf_ra_awaddr),.itf_ra_awdata(itf_ra_awdata),
        .itf_ra_awvalid(itf_ra_awvalid && !face_write),.itf_ra_awready(old_awready),
        .itf_ra_araddr(itf_ra_araddr),.itf_ra_arvalid(itf_ra_arvalid && !face_read && !read_pending),
        .itf_ra_arready(old_arready),.itf_ra_rdata(old_rdata),.itf_ra_rvalid(old_rvalid),
        .itf_ra_rready(itf_ra_rready && read_pending && !read_face),
        .itf_awaddr(old_awaddr),.itf_awdata(old_awdata),.itf_awvalid(old_awvalid),.itf_awready(old_awready_mem),
        .itf_araddr(old_araddr),.itf_arvalid(old_arvalid),.itf_arready(old_arready_mem),
        .itf_rdata(itf_rdata[63:0]),.itf_rvalid(old_memory_rvalid),.itf_rready(old_rready),
        .reset_reg(),.clk(clk),.ra_clk(ra_clk),.rst_n(rst_n),.ra_rst_n(ra_rst_n));

    // Native port has no write response: done means all beats were accepted,
    // exactly the completion boundary used by the supplied adder DMA example.
    assign itf_awvalid=!hp_reset && (select_write_face ? face_native_awvalid : old_awvalid);
    assign itf_awaddr=select_write_face ? face_native_write[607:576] : old_awaddr;
    assign itf_awdata=select_write_face ? face_native_write[575:64] : {448'd0,old_awdata};
    assign itf_awinfo={1'b0,(select_write_face ? face_native_write[63:0] : 64'hffffffffffffffff),6'b0,1'b1};
    assign face_native_awready=!hp_reset && itf_awready && select_write_face;
    assign old_awready_mem=!hp_reset && itf_awready && !select_write_face;
    assign itf_arvalid=!hp_reset && !memory_read_busy && (select_read_face ? face_native_arvalid : old_arvalid);
    assign itf_araddr=select_read_face ? face_native_araddr : old_araddr;
    assign itf_arinfo=1;
    assign face_native_arready=!hp_reset && !memory_read_busy && itf_arready && select_read_face;
    assign old_arready_mem=!hp_reset && !memory_read_busy && !select_read_face && itf_arready;
    assign itf_rready=memory_read_busy && (memory_read_face ? face_native_rready : old_rready);
    always @(posedge clk or posedge hp_reset) begin
        if(hp_reset) begin
            memory_read_busy<=0;memory_read_face<=0;
            write_hold<=0;write_owner<=0;read_hold<=0;read_owner<=0;
        end
        else begin
            if(itf_awvalid && !itf_awready) begin write_hold<=1;write_owner<=select_write_face;end
            if(itf_awvalid && itf_awready) write_hold<=0;
            if(itf_arvalid && !itf_arready) begin read_hold<=1;read_owner<=select_read_face;end
            if(itf_arvalid && itf_arready) begin memory_read_busy<=1;memory_read_face<=select_read_face;read_hold<=0;end
            if(itf_rvalid && itf_rready) memory_read_busy<=0;
        end
    end

    reg [31:0] cfg[0:18];
    reg start,busy,completed,rejected;
    reg [1:0] validate_state;
    reg [47:0] source_bytes;
    reg [33:0] output_bytes;
    reg [48:0] source_end;
    reg [34:0] output_end;
    reg storage_ok;
    reg [3:0] job_error;
    reg [31:0] completed_frame,pixel_count;
    wire core_cmd_ready,core_busy,core_done,core_valid,core_ready,core_sof,core_eol,core_eof;
    wire [1:0] core_error;
    wire [31:0] core_frame;
    wire [23:0] core_rgb;
    wire [31:0] araddr;
    wire [7:0] arlen;wire [2:0] arsize;wire [1:0] arburst;
    wire arvalid,arready,rvalid,rready;
    wire [63:0] rdata;
    reg core_finished,writer_finished;
    reg [511:0] output_buffer;
    reg [63:0] output_mask;
    reg [3:0] output_index;
    reg [31:0] output_address;
    reg output_pending,output_last;
    wire write_mail_ready;
    // The visible vendor port has a 27-bit byte address downstream. Keep this
    // prototype inside that verified address window rather than truncating.
    // Multiply, add and compare in separate cycles at the actual 100 MHz GP
    // clock. busy locks cfg throughout validation; no relaxed timing exception.
    assign core_ready=!gp_reset && !output_pending;
    wcis_face_preprocess backend(
        .clk(ra_clk),.reset(gp_reset),.cmd_valid(start),.cmd_ready(core_cmd_ready),
        .cmd_frame_id(cfg[4]),.cmd_base_addr(cfg[5]),.cmd_pitch_bytes(cfg[6]),.cmd_rgb565(cfg[11][1]),
        .cmd_src_w(storage_ok ? cfg[8][15:0] : 16'd0),.cmd_src_h(cfg[8][31:16]),
        .cmd_content_w(cfg[9][15:0]),.cmd_content_h(cfg[9][31:16]),
        .cmd_canvas_w(cfg[10][15:0]),.cmd_canvas_h(cfg[10][31:16]),
        .cmd_m00(cfg[13]),.cmd_m01(cfg[14]),.cmd_m02(cfg[15]),
        .cmd_m10(cfg[16]),.cmd_m11(cfg[17]),.cmd_m12(cfg[18]),
        .cmd_replicate(cfg[11][0]),.cmd_border(cfg[12][23:0]),
        .busy(core_busy),.done(core_done),.error(core_error),.frame_id(core_frame),
        .m_valid(core_valid),.m_ready(core_ready),.m_rgb(core_rgb),
        .m_sof(core_sof),.m_eol(core_eol),.m_eof(core_eof),
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),
        .m_axi_arvalid(arvalid),.m_axi_arready(arready),.m_axi_rdata(rdata),.m_axi_rresp(2'b00),
        .m_axi_rlast(1'b1),.m_axi_rvalid(rvalid),.m_axi_rready(rready));

    // Two fully associative native 64-byte lines retain both source rows of
    // bilinear sampling. LRU eviction, one outstanding read, no prefetch.
    // The legacy AXI reader still sees single 8-byte beats. Both lines are
    // invalidated on every job, even when a physical address is reused.
    reg [1:0] read_state;
    reg [31:0] read_line;
    reg [2:0] read_lane;
    reg line_valid;
    reg [31:0] line_address;
    reg [511:0] line_data;
    reg second_valid;
    reg [31:0] second_address;
    reg [511:0] second_data;
    reg replace_second,fill_second;
    reg [63:0] read_data;
    wire rd_mail_ready,rd_response_valid;
    wire [543:0] rd_response;
    assign arready=!gp_reset && read_state==0;
    assign rvalid=read_state==3;
    assign rdata=read_data;
    wcis_cdc_mailbox #(.WIDTH(32)) read_request(
        .reset(reset),.s_clk(ra_clk),.m_clk(clk),.s_valid(read_state==1),.s_ready(rd_mail_ready),.s_data(read_line),
        .m_valid(face_native_arvalid),.m_ready(face_native_arready),.m_data(face_native_araddr));
    wcis_cdc_mailbox #(.WIDTH(544)) read_response(
        .reset(reset),.s_clk(clk),.m_clk(ra_clk),
        .s_valid(itf_rvalid && memory_read_busy && memory_read_face),.s_ready(face_native_rready),
        .s_data({itf_rinfo,itf_rdata}),.m_valid(rd_response_valid),.m_ready(read_state==2),.m_data(rd_response));
    wcis_cdc_mailbox #(.WIDTH(608)) write_request(
        .reset(reset),.s_clk(ra_clk),.m_clk(clk),.s_valid(output_pending),.s_ready(write_mail_ready),
        .s_data({output_address,output_buffer,output_mask}),
        .m_valid(face_native_awvalid),.m_ready(face_native_awready),.m_data(face_native_write));
    always @(posedge ra_clk or posedge gp_reset) begin
        if(gp_reset) begin
            read_state<=0;read_line<=0;read_lane<=0;
            line_valid<=0;line_address<=0;line_data<=0;read_data<=0;
            second_valid<=0;second_address<=0;second_data<=0;
            replace_second<=0;fill_second<=0;
        end
        else begin
            if(start) begin line_valid<=0;second_valid<=0;replace_second<=0;end
            case(read_state)
                0: if(arvalid) begin
                    read_lane<=araddr[5:3];read_line<={araddr[31:6],6'b0};
                    if(line_valid && line_address=={araddr[31:6],6'b0}) begin
                        read_data<=line_data>>(araddr[5:3]*64);replace_second<=1;read_state<=3;
                    end else if(second_valid && second_address=={araddr[31:6],6'b0}) begin
                        read_data<=second_data>>(araddr[5:3]*64);replace_second<=0;read_state<=3;
                    end else begin
                        // Prefer an invalid slot before evicting the LRU line.
                        fill_second<=line_valid && (!second_valid || replace_second);
                        read_state<=1;
                    end
                end
                1: if(rd_mail_ready) read_state<=2;
                2: if(rd_response_valid) begin
                    if(fill_second) begin
                        second_data<=rd_response[511:0];second_address<=read_line;second_valid<=1;
                        replace_second<=0;
                    end else begin
                        line_data<=rd_response[511:0];line_address<=read_line;line_valid<=1;
                        replace_second<=1;
                    end
                    read_data<=rd_response[511:0]>>(read_lane*64);read_state<=3;
                end
                3: if(rready) read_state<=0;
            endcase
        end
    end
    integer i;
    always @(posedge ra_clk or posedge gp_reset) begin
        if(gp_reset) begin
            for(i=0;i<19;i=i+1) cfg[i]<=0;
            read_pending<=0;read_face<=0;face_rvalid<=0;face_rdata<=0;
            start<=0;busy<=0;completed<=0;rejected<=0;job_error<=0;completed_frame<=0;pixel_count<=0;
            validate_state<=0;source_bytes<=0;output_bytes<=0;source_end<=0;output_end<=0;storage_ok<=0;
            core_finished<=0;writer_finished<=0;output_buffer<=0;output_mask<=0;
            output_index<=0;output_address<=0;output_pending<=0;output_last<=0;
        end else begin
            start<=0;
            case(validate_state)
                1: begin
                    source_bytes<={16'd0,cfg[6]}*{32'd0,cfg[8][31:16]};
                    output_bytes<=({18'd0,cfg[10][15:0]}*{18'd0,cfg[10][31:16]})<<2;
                    validate_state<=2;
                end
                2: begin
                    source_end<={17'd0,cfg[5]}+{1'b0,source_bytes};
                    output_end<={3'd0,cfg[7]}+(({1'b0,output_bytes}+35'd63)&35'h7ffffffc0);
                    validate_state<=3;
                end
                3: begin
                    storage_ok<=cfg[7][5:0]==0 && output_end<=35'h08000000 && source_end<=49'h08000000 &&
                        (source_end<={17'd0,cfg[7]} || output_end<={3'd0,cfg[5]});
                    start<=1;validate_state<=0;
                end
            endcase
            if(itf_ra_arvalid && itf_ra_arready) begin
                read_pending<=1;read_face<=face_read;
                if(face_read) begin
                    face_rvalid<=1;
                    case(itf_ra_araddr[7:2])
                        0: face_rdata<=32'h46414331; // FAC1, distinct from the preserved adder ID
                        1: face_rdata<={24'd0,job_error,rejected,1'b0,completed,busy};
                        2: face_rdata<=completed_frame;
                        3: face_rdata<=pixel_count;
                        default: face_rdata<=itf_ra_araddr[7:2]<19 ? cfg[itf_ra_araddr[7:2]] : 0;
                    endcase
                end
            end
            if(itf_ra_rvalid && itf_ra_rready) begin read_pending<=0;if(read_face) face_rvalid<=0;end
            if(itf_ra_awvalid && itf_ra_awready && face_write) begin
                if(busy) rejected<=1;
                else if(itf_ra_awaddr[7:2]==0 && itf_ra_awdata[0]) begin
                    validate_state<=1;busy<=1;completed<=0;rejected<=0;job_error<=0;pixel_count<=0;
                    core_finished<=0;writer_finished<=0;output_buffer<=0;output_mask<=0;
                    output_index<=0;output_address<=cfg[7];output_pending<=0;output_last<=0;
                end else if(itf_ra_awaddr[7:2]>=4 && itf_ra_awaddr[7:2]<19)
                    cfg[itf_ra_awaddr[7:2]]<=itf_ra_awdata;
            end
            if(core_valid && core_ready) begin
                output_buffer[output_index*32 +: 32]<={8'd0,core_rgb};
                output_mask[output_index*4 +: 4]<=4'hf;
                pixel_count<=pixel_count+1;
                if(output_index==15 || core_eof) begin output_pending<=1;output_last<=core_eof;end
                else output_index<=output_index+1;
            end
            if(output_pending && write_mail_ready) begin
                output_pending<=0;output_index<=0;output_mask<=0;output_address<=output_address+64;
                if(output_last) writer_finished<=1;
            end
            if(core_done) begin core_finished<=1;job_error<={2'b00,core_error};end
            if(busy && core_finished && !output_pending && write_mail_ready &&
               (job_error!=0 || writer_finished)) begin
                busy<=0;completed<=1;completed_frame<=core_frame;
                // A partial buffer on an error is intentionally not committed.
                if(job_error!=0) begin output_index<=0;output_mask<=0;end
            end
        end
    end
endmodule
