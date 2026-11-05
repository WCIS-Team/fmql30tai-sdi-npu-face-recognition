`timescale 1ns/1ps
// Clause 22 MDIO, one bounded transaction. Change driven data at MDC falling
// edges. PHY read data is allowed to change after MDC rises (YT8521S t6).
// Synchronize it, then sample in the middle of the high phase, not on the edge.
module wcis_mdio_clause22 #(
    parameter integer HALF_PERIOD=25
)(
    input wire clk,reset,command_valid,command_read,
    input wire [4:0] phy_address,register_address,
    input wire [15:0] write_data,
    output wire command_ready,output reg done,error,
    output reg [15:0] read_data,
    output reg mdc,output wire mdio_out,mdio_tristate,input wire mdio_in
);
    reg busy,read_mode;
    reg [63:0] bits;
    reg [6:0] position;
    reg [$clog2(HALF_PERIOD+1)-1:0] divider;
    (* ASYNC_REG="TRUE" *) reg [1:0] mdio_sync;
    assign command_ready=!busy;
    assign mdio_out=bits[63];
    assign mdio_tristate=!busy || (read_mode&&position>=46);
    always @(posedge clk)begin
        if(reset)begin
            busy<=0;read_mode<=0;bits<=64'hffffffffffffffff;position<=0;
            divider<=0;mdc<=0;done<=0;error<=0;read_data<=0;mdio_sync<=3;
        end else begin
            mdio_sync<={mdio_sync[0],mdio_in};
            done<=0;
            if(command_valid&&command_ready)begin
                bits<={32'hffffffff,2'b01,command_read ? 2'b10 : 2'b01,
                        phy_address,register_address,2'b10,write_data};
                busy<=1;read_mode<=command_read;position<=0;divider<=0;
                mdc<=0;read_data<=0;error<=0;
            end else if(busy) begin
                // At 100 MHz / HALF_PERIOD=25 this is 120 ns after MDC rises,
                // comfortably beyond 20 ns PHY t6 plus the two synchronizers.
                if(mdc&&divider==HALF_PERIOD/2)begin
                    if(read_mode&&position==47&&mdio_sync[1]!==1'b0)error<=1;
                    if(read_mode&&position>=48)read_data<={read_data[14:0],mdio_sync[1]};
                end
                if(divider==HALF_PERIOD-1)begin
                    divider<=0;mdc<=!mdc;
                    if(mdc)begin
                        if(position==63)begin busy<=0;done<=1;mdc<=0;end
                        else begin position<=position+1;bits<={bits[62:0],1'b1};end
                    end
                end else divider<=divider+1;
            end
        end
    end
    initial if(HALF_PERIOD<10)$error("MDIO divider leaves insufficient synchronized read settling time");
endmodule
