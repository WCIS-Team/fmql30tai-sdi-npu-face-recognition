`timescale 1ns/1ps
// Insert only in the existing native register interface; DDR/NPU are untouched.
// One outstanding read, with response ownership held until it is accepted.
module wcis_preview_csr_router(
    input wire clk,reset,
    input wire [31:0] awaddr,araddr,input wire awvalid,arvalid,rready,
    output wire awready,arready,rvalid,output wire [31:0] rdata,
    output wire legacy_awvalid,legacy_arvalid,legacy_rready,
    input wire legacy_awready,legacy_arready,legacy_rvalid,input wire [31:0] legacy_rdata,
    output wire preview_awvalid,preview_arvalid,preview_rready,
    input wire preview_awready,preview_arready,preview_rvalid,input wire [31:0] preview_rdata
);
    wire write_preview=awaddr[17:8]==10'h022;
    wire read_preview=araddr[17:8]==10'h022;
    reg pending,owner_preview;
    assign awready=!reset&&(write_preview ? preview_awready : legacy_awready);
    assign legacy_awvalid=awvalid&&!write_preview&&!reset;
    assign preview_awvalid=awvalid&&write_preview&&!reset;
    assign arready=!reset&&!pending&&(read_preview ? preview_arready : legacy_arready);
    assign legacy_arvalid=arvalid&&!read_preview&&!pending&&!reset;
    assign preview_arvalid=arvalid&&read_preview&&!pending&&!reset;
    assign rvalid=pending&&(owner_preview ? preview_rvalid : legacy_rvalid);
    assign rdata=owner_preview ? preview_rdata : legacy_rdata;
    assign legacy_rready=rready&&pending&&!owner_preview;
    assign preview_rready=rready&&pending&&owner_preview;
    always @(posedge clk)begin
        if(reset)begin pending<=0;owner_preview<=0;end
        else begin
            if(arvalid&&arready)begin pending<=1;owner_preview<=read_preview;end
            if(rvalid&&rready)pending<=0;
        end
    end
endmodule
