`timescale 1ns/1ps
// One-entry bundled-data mailbox. Shared asynchronous assertion, local reset
// release. Hold source payload until destination consumption is acknowledged.
// Physical payload max-delay/bus-skew constraints are required at integration.
module wcis_cdc_mailbox #(parameter WIDTH=32)(
    input wire reset, s_clk, m_clk,
    input wire s_valid, output wire s_ready, input wire [WIDTH-1:0] s_data,
    output reg m_valid, input wire m_ready, output reg [WIDTH-1:0] m_data
);
    reg [WIDTH-1:0] payload_hold;
    reg request_toggle,ack_toggle;
    (* ASYNC_REG="TRUE" *) reg [1:0] request_sync,ack_sync,s_reset,m_reset;
    assign s_ready=!s_reset[1] && request_toggle==ack_sync[1];
    always @(posedge s_clk or posedge reset)
        if(reset) s_reset<=3;else s_reset<={s_reset[0],1'b0};
    always @(posedge m_clk or posedge reset)
        if(reset) m_reset<=3;else m_reset<={m_reset[0],1'b0};
    always @(posedge s_clk or posedge s_reset[1]) begin
        if(s_reset[1]) begin payload_hold<=0;request_toggle<=0;ack_sync<=0;end
        else begin
            ack_sync<={ack_sync[0],ack_toggle};
            if(s_valid && s_ready) begin payload_hold<=s_data;request_toggle<=~request_toggle;end
        end
    end
    always @(posedge m_clk or posedge m_reset[1]) begin
        if(m_reset[1]) begin request_sync<=0;ack_toggle<=0;m_valid<=0;m_data<=0;end
        else begin
            request_sync<={request_sync[0],request_toggle};
            if(!m_valid && request_sync[1]!=ack_toggle) begin m_data<=payload_hold;m_valid<=1;end
            if(m_valid && m_ready) begin m_valid<=0;ack_toggle<=request_sync[1];end
        end
    end
endmodule
