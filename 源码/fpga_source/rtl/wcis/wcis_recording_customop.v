`timescale 1ns/1ps
// Preserve FAC1 + legacy adder and add JPG1 at page 0x2100. One outstanding
// native read, stable request ownership across backpressure, separate CSR owner.
module wcis_recording_customop #(
    parameter JPEG_WIDTH=1920,JPEG_HEIGHT=1080,JPEG_QUALITY=75
)(
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
    (* ASYNC_REG="TRUE" *) reg [1:0] hp_sync,gp_sync;
    always @(posedge clk or posedge reset)
        if(reset) hp_sync<=3;else hp_sync<={hp_sync[0],1'b0};
    always @(posedge ra_clk or posedge reset)
        if(reset) gp_sync<=3;else gp_sync<={gp_sync[0],1'b0};
    wire hp_reset=hp_sync[1],gp_reset=gp_sync[1];
    wire jw=itf_ra_awaddr[17:8]==10'h021;
    wire jr=itf_ra_araddr[17:8]==10'h021;
    reg csr_pending,csr_jpeg;
    wire f_cawready,j_cawready,f_carready,j_carready,f_crvalid,j_crvalid;
    wire [31:0] f_crdata,j_crdata;
    wire [31:0] f_awaddr,j_awaddr,f_araddr,j_araddr,f_arinfo,j_arinfo;
    wire [511:0] f_awdata,j_awdata;
    wire [71:0] f_awinfo,j_awinfo;
    wire f_awvalid,j_awvalid,f_arvalid,j_arvalid,f_rready,j_rready;
    wire f_awready,j_awready,f_arready,j_arready;
    reg rd_busy,rd_jpeg,wr_hold,wr_owner,rd_hold,rd_owner;
    wire choose_wr=wr_hold ? wr_owner : j_awvalid;
    wire choose_rd=rd_hold ? rd_owner : j_arvalid;
    assign itf_ra_awready=!gp_reset && (jw ? j_cawready : f_cawready);
    assign itf_ra_arready=!gp_reset && !csr_pending && (jr ? j_carready : f_carready);
    assign itf_ra_rvalid=csr_pending && (csr_jpeg ? j_crvalid : f_crvalid);
    assign itf_ra_rdata=csr_jpeg ? j_crdata : f_crdata;
    always @(posedge ra_clk or posedge gp_reset)
        if(gp_reset) begin csr_pending<=0;csr_jpeg<=0;end
        else begin
            if(itf_ra_arvalid && itf_ra_arready) begin csr_pending<=1;csr_jpeg<=jr;end
            if(itf_ra_rvalid && itf_ra_rready) csr_pending<=0;
        end
    wcis_face_customop face(
        .itf_ra_awaddr(itf_ra_awaddr),.itf_ra_awdata(itf_ra_awdata),
        .itf_ra_awvalid(itf_ra_awvalid && !jw && !gp_reset),.itf_ra_awready(f_cawready),
        .itf_ra_araddr(itf_ra_araddr),.itf_ra_arvalid(itf_ra_arvalid && !jr && !csr_pending && !gp_reset),
        .itf_ra_arready(f_carready),.itf_ra_rdata(f_crdata),.itf_ra_rvalid(f_crvalid),
        .itf_ra_rready(itf_ra_rready && csr_pending && !csr_jpeg),
        .itf_awaddr(f_awaddr),.itf_awdata(f_awdata),.itf_awinfo(f_awinfo),.itf_awvalid(f_awvalid),.itf_awready(f_awready),
        .itf_araddr(f_araddr),.itf_arinfo(f_arinfo),.itf_arvalid(f_arvalid),.itf_arready(f_arready),
        .itf_rdata(itf_rdata),.itf_rinfo(itf_rinfo),.itf_rvalid(itf_rvalid && rd_busy && !rd_jpeg),.itf_rready(f_rready),
        .clk(clk),.ra_clk(ra_clk),.rst_n(rst_n),.ra_rst_n(ra_rst_n));
    wcis_jpeg_customop #(.IMG_WIDTH(JPEG_WIDTH),.IMG_HEIGHT(JPEG_HEIGHT),.QUALITY(JPEG_QUALITY)) jpeg(
        .itf_ra_awaddr(itf_ra_awaddr),.itf_ra_awdata(itf_ra_awdata),
        .itf_ra_awvalid(itf_ra_awvalid && jw && !gp_reset),.itf_ra_awready(j_cawready),
        .itf_ra_araddr(itf_ra_araddr),.itf_ra_arvalid(itf_ra_arvalid && jr && !csr_pending && !gp_reset),
        .itf_ra_arready(j_carready),.itf_ra_rdata(j_crdata),.itf_ra_rvalid(j_crvalid),
        .itf_ra_rready(itf_ra_rready && csr_pending && csr_jpeg),
        .itf_awaddr(j_awaddr),.itf_awdata(j_awdata),.itf_awinfo(j_awinfo),.itf_awvalid(j_awvalid),.itf_awready(j_awready),
        .itf_araddr(j_araddr),.itf_arinfo(j_arinfo),.itf_arvalid(j_arvalid),.itf_arready(j_arready),
        .itf_rdata(itf_rdata),.itf_rinfo(itf_rinfo),.itf_rvalid(itf_rvalid && rd_busy && rd_jpeg),.itf_rready(j_rready),
        .clk(clk),.ra_clk(ra_clk),.rst_n(rst_n),.ra_rst_n(ra_rst_n));
    assign itf_awvalid=!hp_reset && (choose_wr ? j_awvalid : f_awvalid);
    assign itf_awaddr=choose_wr ? j_awaddr : f_awaddr;
    assign itf_awdata=choose_wr ? j_awdata : f_awdata;
    assign itf_awinfo=choose_wr ? j_awinfo : f_awinfo;
    assign j_awready=!hp_reset && choose_wr && itf_awready;
    assign f_awready=!hp_reset && !choose_wr && itf_awready;
    assign itf_arvalid=!hp_reset && !rd_busy && (choose_rd ? j_arvalid : f_arvalid);
    assign itf_araddr=choose_rd ? j_araddr : f_araddr;
    assign itf_arinfo=choose_rd ? j_arinfo : f_arinfo;
    assign j_arready=!hp_reset && !rd_busy && choose_rd && itf_arready;
    assign f_arready=!hp_reset && !rd_busy && !choose_rd && itf_arready;
    assign itf_rready=rd_busy && (rd_jpeg ? j_rready : f_rready);
    always @(posedge clk or posedge hp_reset) begin
        if(hp_reset) begin rd_busy<=0;rd_jpeg<=0;wr_hold<=0;wr_owner<=0;rd_hold<=0;rd_owner<=0;end
        else begin
            if(itf_awvalid && !itf_awready) begin wr_hold<=1;wr_owner<=choose_wr;end
            if(itf_awvalid && itf_awready) wr_hold<=0;
            if(itf_arvalid && !itf_arready) begin rd_hold<=1;rd_owner<=choose_rd;end
            if(itf_arvalid && itf_arready) begin rd_busy<=1;rd_jpeg<=choose_rd;rd_hold<=0;end
            if(itf_rvalid && itf_rready) rd_busy<=0;
        end
    end
endmodule
