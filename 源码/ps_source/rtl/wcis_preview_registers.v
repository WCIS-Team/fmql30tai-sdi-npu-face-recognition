`timescale 1ns/1ps
// NTP1 page at CustomOp offset 0x2200. Networking is disabled after reset.
// No pixel buffer addresses are exposed; the preview uses independent FIFOs.
module wcis_preview_registers #(
    parameter TX_ONLY_SERDES=0
)(
    input wire clk,reset,
    input wire [31:0] awaddr,awdata,input wire awvalid,output wire awready,
    input wire [31:0] araddr,input wire arvalid,output wire arready,
    output reg [31:0] rdata,output reg rvalid,input wire rready,
    output reg enable,output reg phy_reset_n,
    output reg [31:0] session_id,local_ip,destination_ip,gateway_ip,subnet_mask,
    output reg [47:0] local_mac,next_hop_mac,output reg [15:0] source_port,destination_port,
    input wire net_clk,input wire [1:0] speed,input wire clock_locked,
    input wire [31:0] jpeg_frames,rejected_frames,udp_frames,aborted_frames,udp_packets,
    input wire arp_failed,tx_underflow,rx_bad_fcs,packet_error,
    output wire phy_mdc,output wire phy_mdio_out,phy_mdio_tristate,input wire phy_mdio_in
);
    reg command_valid,command_read;
    reg [4:0] mdio_phy,mdio_reg;reg [15:0] mdio_write;
    wire command_ready,mdio_done,mdio_error;wire [15:0] mdio_read;
    reg mdio_complete;reg [31:0] rejected_writes;
    assign awready=!reset;assign arready=!reset&&!rvalid;
    wcis_mdio_clause22 management(
        .clk(clk),.reset(reset),.command_valid(command_valid),.command_read(command_read),
        .phy_address(mdio_phy),.register_address(mdio_reg),.write_data(mdio_write),
        .command_ready(command_ready),.done(mdio_done),.error(mdio_error),.read_data(mdio_read),
        .mdc(phy_mdc),.mdio_out(phy_mdio_out),.mdio_tristate(phy_mdio_tristate),.mdio_in(phy_mdio_in));
    // Snapshot stable statistics atomically across the independent clocks.
    wire snapshot_valid,snapshot_ready;wire [166:0] snapshot_data;
    reg [166:0] sampled_status;
    wcis_cdc_mailbox #(.WIDTH(167)) status_mailbox(
        .reset(reset),.s_clk(net_clk),.m_clk(clk),.s_valid(1'b1),.s_ready(snapshot_ready),
        .s_data({clock_locked,packet_error,rx_bad_fcs,tx_underflow,arp_failed,speed,
            jpeg_frames,rejected_frames,udp_frames,aborted_frames,udp_packets}),
        .m_valid(snapshot_valid),.m_ready(1'b1),.m_data(snapshot_data));
    always @(posedge clk)begin
        if(reset)begin
            enable<=0;phy_reset_n<=0;session_id<=0;local_mac<=0;next_hop_mac<=0;
            local_ip<=0;destination_ip<=0;gateway_ip<=0;subnet_mask<=0;
            source_port<=0;destination_port<=0;command_valid<=0;command_read<=0;
            mdio_phy<=0;mdio_reg<=0;mdio_write<=0;mdio_complete<=0;
            rejected_writes<=0;rvalid<=0;rdata<=0;sampled_status<=0;
        end else begin
            if(snapshot_valid)sampled_status<=snapshot_data;
            if(command_valid&&command_ready)command_valid<=0;
            if(mdio_done)mdio_complete<=1;
            if(rvalid&&rready)rvalid<=0;
            if(awvalid&&awready)begin
                if(awaddr[7:0]==8'h04)begin
                    if(!awdata[0])enable<=0;
                    else if(session_id!=0&&local_ip!=0&&destination_ip!=0&&
                        local_mac!=0&&!local_mac[40]&&source_port!=0&&destination_port!=0&&phy_reset_n&&command_ready&&!command_valid&&
                        (!TX_ONLY_SERDES||(next_hop_mac!=0&&!next_hop_mac[40])))
                        enable<=1;
                    else rejected_writes<=rejected_writes+1;
                end else if(enable)rejected_writes<=rejected_writes+1;
                else case(awaddr[7:0])
                    8'h0c:session_id<=awdata;
                    8'h10:local_mac[31:0]<=awdata;
                    8'h14:local_mac[47:32]<=awdata[15:0];
                    8'h18:local_ip<=awdata;
                    8'h1c:destination_ip<=awdata;
                    8'h20:gateway_ip<=awdata;
                    8'h24:subnet_mask<=awdata;
                    8'h28:begin source_port<=awdata[31:16];destination_port<=awdata[15:0];end
                    8'h30:if(!command_valid&&command_ready)begin
                        command_valid<=1;command_read<=awdata[30];mdio_phy<=awdata[25:21];
                        mdio_reg<=awdata[20:16];mdio_write<=awdata[15:0];mdio_complete<=0;
                    end else rejected_writes<=rejected_writes+1;
                    8'h38:phy_reset_n<=awdata[0];
                    8'h60:if(TX_ONLY_SERDES)next_hop_mac[31:0]<=awdata;else rejected_writes<=rejected_writes+1;
                    8'h64:if(TX_ONLY_SERDES)next_hop_mac[47:32]<=awdata[15:0];else rejected_writes<=rejected_writes+1;
                    default:rejected_writes<=rejected_writes+1;
                endcase
            end
            if(arvalid&&arready)begin
                rvalid<=1;
                case(araddr[7:0])
                    8'h00:rdata<=TX_ONLY_SERDES?32'h4e545032:32'h4e545031; // NTP2 / NTP1
                    8'h04:rdata<={31'd0,enable};
                    8'h08:rdata<={25'd0,sampled_status[166:160]};
                    8'h0c:rdata<=session_id;
                    8'h10:rdata<=local_mac[31:0];
                    8'h14:rdata<={16'd0,local_mac[47:32]};
                    8'h18:rdata<=local_ip;
                    8'h1c:rdata<=destination_ip;
                    8'h20:rdata<=gateway_ip;
                    8'h24:rdata<=subnet_mask;
                    8'h28:rdata<={source_port,destination_port};
                    8'h2c:rdata<=rejected_writes;
                    8'h34:rdata<={13'd0,mdio_error,mdio_complete,(!command_ready||command_valid),mdio_read};
                    8'h38:rdata<={31'd0,phy_reset_n};
                    8'h40:rdata<=sampled_status[159:128];
                    8'h44:rdata<=sampled_status[127:96];
                    8'h48:rdata<=sampled_status[95:64];
                    8'h4c:rdata<=sampled_status[63:32];
                    8'h50:rdata<=sampled_status[31:0];
                    8'h54:rdata<=1920;
                    8'h58:rdata<=1080;
                    // bit0: explicit next-hop, bit1: fixed 1G full duplex,
                    // bit2: shared-clock serializer, PHY extra TX delay zero.
                    8'h5c:rdata<=TX_ONLY_SERDES?32'h7:32'h0;
                    8'h60:rdata<=next_hop_mac[31:0];
                    8'h64:rdata<={16'd0,next_hop_mac[47:32]};
                    default:rdata<=0;
                endcase
            end
        end
    end
endmodule
