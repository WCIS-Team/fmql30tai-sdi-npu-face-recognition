`timescale 1ns/1ps
// Independent candidate, not a board-qualified PHY interface.
// UG471 v1.10: 4:1 DDR OSERDESE2, same PLL / same buffer type for CLK/CLKDIV.
// Six serializers share phase-aligned 250 MHz CLK and 125 MHz CLKDIV.
// Data patterns L,L,H,H hold each RGMII nibble for 4 ns. Clock 0,1,1,0
// puts its rising/falling edges 2 ns after each actual nibble transition.
// PHY TX internal delay MUST remain zero. Physical timing still needs review.
module wcis_rgmii_tx_serdes(
 input wire clk125,clk250,reset,
 input wire [7:0] gmii_data,
 input wire gmii_enable,gmii_error,
 output wire rgmii_tx_clk,rgmii_tx_ctl,
 output wire [3:0] rgmii_txd
);
 wire [4:0] low_nibble={gmii_enable,gmii_data[3:0]};
 wire [4:0] high_nibble={gmii_enable^gmii_error,gmii_data[7:4]};
 wire [4:0] pins;
 genvar i;
 generate for(i=0;i<5;i=i+1)begin: data_lane
  OSERDESE2 #(.DATA_RATE_OQ("DDR"),.DATA_RATE_TQ("DDR"),.DATA_WIDTH(4),
   .TRISTATE_WIDTH(4),.SERDES_MODE("MASTER"),.INIT_OQ(1'b0),.SRVAL_OQ(1'b0),
   .INIT_TQ(1'b0),.SRVAL_TQ(1'b0),.TBYTE_CTL("FALSE"),.TBYTE_SRC("FALSE")) serializer(
   .CLK(clk250),.CLKDIV(clk125),.RST(reset),.OCE(1'b1),
   .D1(low_nibble[i]),.D2(low_nibble[i]),.D3(high_nibble[i]),.D4(high_nibble[i]),
   .D5(1'b0),.D6(1'b0),.D7(1'b0),.D8(1'b0),.OQ(pins[i]),
   .OFB(),.SHIFTOUT1(),.SHIFTOUT2(),.SHIFTIN1(1'b0),.SHIFTIN2(1'b0),
   .T1(1'b0),.T2(1'b0),.T3(1'b0),.T4(1'b0),.TCE(1'b0),.TBYTEIN(1'b0),
   .TBYTEOUT(),.TFB(),.TQ());
 end endgenerate
 assign {rgmii_tx_ctl,rgmii_txd}=pins;
 OSERDESE2 #(.DATA_RATE_OQ("DDR"),.DATA_RATE_TQ("DDR"),.DATA_WIDTH(4),
  .TRISTATE_WIDTH(4),.SERDES_MODE("MASTER"),.INIT_OQ(1'b0),.SRVAL_OQ(1'b0),
  .INIT_TQ(1'b0),.SRVAL_TQ(1'b0),.TBYTE_CTL("FALSE"),.TBYTE_SRC("FALSE")) clock_serializer(
  .CLK(clk250),.CLKDIV(clk125),.RST(reset),.OCE(1'b1),
  .D1(1'b0),.D2(1'b1),.D3(1'b1),.D4(1'b0),
  .D5(1'b0),.D6(1'b0),.D7(1'b0),.D8(1'b0),.OQ(rgmii_tx_clk),
  .OFB(),.SHIFTOUT1(),.SHIFTOUT2(),.SHIFTIN1(1'b0),.SHIFTIN2(1'b0),
  .T1(1'b0),.T2(1'b0),.T3(1'b0),.T4(1'b0),.TCE(1'b0),.TBYTEIN(1'b0),
  .TBYTEOUT(),.TFB(),.TQ());
endmodule
