// Single-bit status only: the producer must retain the level long enough for
// two destination samples. Payload buses must use an atomic mailbox/FIFO.
// The existing pinned reset synchronizer makes reset release local to clk.
module wcis_status_sync (
    input wire clk,
    input wire reset,
    input wire s_status,
    output wire m_status
);
    wire local_reset;
    sync_reset #(.N(3)) reset_release (
        .clk(clk), .rst(reset), .out(local_reset)
    );
    (* ASYNC_REG="TRUE", SHREG_EXTRACT="NO" *) reg [1:0] status_reg = 2'b00;
    always @(posedge clk or posedge local_reset) begin
        if (local_reset) status_reg <= 2'b00;
        else status_reg <= {status_reg[0], s_status};
    end
    assign m_status = status_reg[1];
endmodule
