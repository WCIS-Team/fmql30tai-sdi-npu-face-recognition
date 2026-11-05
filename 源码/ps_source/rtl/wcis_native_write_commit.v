`timescale 1ns/1ps
// Native DDR has no B response. Backpressure each client write until a read
// of the same address matches every enabled byte. This is a data-visibility
// receipt, not an invented AXI B response. Keep the software epoch/guards too.
module wcis_native_write_commit #(
    parameter MAX_READS=1024, MAX_CYCLES=100000000
)(
    input wire clk,reset,
    input wire [31:0] c_awaddr,input wire [511:0] c_awdata,input wire [71:0] c_awinfo,
    input wire c_awvalid,c_requires_verify,output wire c_awready,
    input wire [31:0] c_araddr,c_arinfo,input wire c_arvalid,output wire c_arready,
    output wire [511:0] c_rdata,output wire [31:0] c_rinfo,
    output wire c_rvalid,input wire c_rready,
    output wire [31:0] m_awaddr,output wire [511:0] m_awdata,output wire [71:0] m_awinfo,
    output wire m_awvalid,input wire m_awready,
    output wire [31:0] m_araddr,m_arinfo,output wire m_arvalid,input wire m_arready,
    input wire [511:0] m_rdata,input wire [31:0] m_rinfo,
    input wire m_rvalid,output wire m_rready,
    output reg fault,output reg [31:0] writes_visible,retry_reads,last_address
);
    localparam ISSUE=0,READ=1,WAIT=2,ACK=3,FAILED=4;
    reg [2:0] state;
    reg [511:0] expected;
    reg [63:0] mask;
    reg [31:0] address,attempts,age;
    reg read_busy,read_verify,grant_hold,grant_verify;
    // A timeout cannot retract an AR request already offered under stall.
    wire verify_request=(state==READ && !fault) || (fault && grant_hold && grant_verify);
    wire choose_verify=grant_hold ? grant_verify : verify_request;
    assign m_awaddr=c_awaddr;
    assign m_awdata=c_awdata;
    assign m_awinfo=c_awinfo;
    assign m_awvalid=!reset && state==ISSUE && c_awvalid && !fault;
    assign c_awready=!reset && !fault && (state==ACK || (state==ISSUE && !c_requires_verify && m_awready));
    assign m_araddr=choose_verify ? address : c_araddr;
    assign m_arinfo=choose_verify ? 32'd1 : c_arinfo;
    assign m_arvalid=!reset && !read_busy && (choose_verify ? verify_request : c_arvalid);
    assign c_arready=!reset && !read_busy && !choose_verify && m_arready;
    assign c_rdata=m_rdata;
    assign c_rinfo=m_rinfo;
    assign c_rvalid=!reset && read_busy && !read_verify && m_rvalid;
    // Even on a timeout, consume a late verification response. A fault never
    // acknowledges the client write or permits another write to replace it.
    assign m_rready=!reset && read_busy && (read_verify || c_rready);
    integer i;
    reg equal_bytes;
    always @* begin
        equal_bytes=1;
        for(i=0;i<64;i=i+1)
            if(mask[i] && m_rdata[i*8 +: 8]!==expected[i*8 +: 8]) equal_bytes=0;
    end
    always @(posedge clk or posedge reset) begin
        if(reset) begin
            state<=ISSUE;expected<=0;mask<=0;address<=0;attempts<=0;age<=0;
            fault<=0;writes_visible<=0;retry_reads<=0;last_address<=0;
            read_busy<=0;read_verify<=0;grant_hold<=0;grant_verify<=0;
        end else begin
            if(m_arvalid && !m_arready) begin grant_hold<=1;grant_verify<=choose_verify;end
            if(m_arvalid && m_arready) begin
                read_busy<=1;read_verify<=choose_verify;grant_hold<=0;
                if(choose_verify) begin state<=WAIT;attempts<=attempts+1;end
            end
            if(m_rvalid && m_rready) begin
                read_busy<=0;
                if(read_verify && state==WAIT && !fault) begin
                    if(equal_bytes) state<=ACK;
                    else begin
                        retry_reads<=retry_reads+1;
                        if(attempts>=MAX_READS) begin fault<=1;state<=FAILED;end
                        else state<=READ;
                    end
                end
            end
            if(m_awvalid && m_awready && c_requires_verify) begin
                expected<=c_awdata;mask<=c_awinfo[70:7];address<=c_awaddr;
                last_address<=c_awaddr;attempts<=0;age<=0;state<=READ;
            end
            if(c_awvalid && c_awready && state==ACK) begin state<=ISSUE;writes_visible<=writes_visible+1;end
            if(state==READ || state==WAIT) begin
                age<=age+1;
                if(age>=MAX_CYCLES-1) begin fault<=1;state<=FAILED;end
            end
        end
    end
endmodule
