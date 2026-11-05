`timescale 1ns/1ps
// Candidate fixed-next-hop IPv4/UDP transmitter. Configuration is held until
// reset. The management plane must verify PHY 1000/full duplex and the TX
// delay ownership before releasing reset. This block never receives Ethernet.
// USE_PHY_TX_DELAY=0 retains MAC +90 degrees / PHY TX delay zero.
// USE_PHY_TX_DELAY=1 is an OFFLINE CANDIDATE: forward the same 125 MHz clock
// as the data, with delay supplied inside the PHY. Its receiver timing contract
// is not yet admitted for a board build; simulation alone must not enable it.
// Pinned MIT upstream sources remain unmodified; only their TX blocks compose.
module wcis_jpeg_network_tx #(
 parameter TARGET="XILINX",
 parameter USE_PHY_TX_DELAY=0,
 parameter USE_SERDES_TX=0
)(
 input wire clk,reset,gtx_clk,gtx_clk90,gtx_reset,
 // Used only by the offline USE_SERDES_TX candidate.
 input wire gtx_clk250,
 input wire [47:0] local_mac,next_hop_mac,
 input wire [31:0] local_ip,destination_ip,
 input wire [15:0] source_port,destination_port,s_udp_length,
 input wire s_hdr_valid,output wire s_hdr_ready,
 input wire [7:0] s_data,input wire s_valid,s_last,output wire s_ready,
 output wire rgmii_tx_clk,output wire [3:0] rgmii_txd,output wire rgmii_tx_ctl,
 output wire tx_underflow,packet_error,configuration_error
);
wire valid_destination=(next_hop_mac!=0)&&!next_hop_mac[40]&&!(USE_SERDES_TX&&USE_PHY_TX_DELAY);
assign configuration_error=!valid_destination;
wire accepted_header=s_hdr_valid&&valid_destination&&(s_udp_length>=8)&&(s_udp_length<=1480);
wire header_ready;
assign s_hdr_ready=header_ready&&valid_destination&&(s_udp_length>=8)&&(s_udp_length<=1480);
wire  checked_udp_hdr_valid;
wire  checked_udp_hdr_ready;
wire [47:0] checked_eth_dest_mac;
wire [47:0] checked_eth_src_mac;
wire [15:0] checked_eth_type;
wire [3:0] checked_ip_version;
wire [3:0] checked_ip_ihl;
wire [5:0] checked_ip_dscp;
wire [1:0] checked_ip_ecn;
wire [15:0] checked_ip_length;
wire [15:0] checked_ip_identification;
wire [2:0] checked_ip_flags;
wire [12:0] checked_ip_fragment_offset;
wire [7:0] checked_ip_ttl;
wire [7:0] checked_ip_protocol;
wire [15:0] checked_ip_header_checksum;
wire [31:0] checked_ip_source_ip;
wire [31:0] checked_ip_dest_ip;
wire [15:0] checked_udp_source_port;
wire [15:0] checked_udp_dest_port;
wire [15:0] checked_udp_length;
wire [15:0] checked_udp_checksum;
wire [7:0] checked_udp_payload_axis_tdata;
wire  checked_udp_payload_axis_tvalid;
wire  checked_udp_payload_axis_tready;
wire  checked_udp_payload_axis_tlast;
wire  checked_udp_payload_axis_tuser;
wire  ip_ip_hdr_valid;
wire  ip_ip_hdr_ready;
wire [47:0] ip_eth_dest_mac;
wire [47:0] ip_eth_src_mac;
wire [15:0] ip_eth_type;
wire [3:0] ip_ip_version;
wire [3:0] ip_ip_ihl;
wire [5:0] ip_ip_dscp;
wire [1:0] ip_ip_ecn;
wire [15:0] ip_ip_length;
wire [15:0] ip_ip_identification;
wire [2:0] ip_ip_flags;
wire [12:0] ip_ip_fragment_offset;
wire [7:0] ip_ip_ttl;
wire [7:0] ip_ip_protocol;
wire [15:0] ip_ip_header_checksum;
wire [31:0] ip_ip_source_ip;
wire [31:0] ip_ip_dest_ip;
wire [7:0] ip_ip_payload_axis_tdata;
wire  ip_ip_payload_axis_tvalid;
wire  ip_ip_payload_axis_tready;
wire  ip_ip_payload_axis_tlast;
wire  ip_ip_payload_axis_tuser;
wire  udp_transmitter_error;
wire  eth_eth_hdr_valid;
wire  eth_eth_hdr_ready;
wire [47:0] eth_eth_dest_mac;
wire [47:0] eth_eth_src_mac;
wire [15:0] eth_eth_type;
wire [7:0] eth_eth_payload_axis_tdata;
wire  eth_eth_payload_axis_tvalid;
wire  eth_eth_payload_axis_tready;
wire  eth_eth_payload_axis_tlast;
wire  eth_eth_payload_axis_tuser;
wire  ipv4_transmitter_error;
wire [7:0] tx_axis_tdata;
wire [0:0] tx_axis_tkeep;
wire  tx_axis_tvalid;
wire  tx_axis_tready;
wire  tx_axis_tlast;
wire  tx_axis_tuser;
udp_checksum_gen #(.PAYLOAD_FIFO_DEPTH(2048),.HEADER_FIFO_DEPTH(8)) checksum_generator (
    .clk(clk),
    .rst(reset),
    .s_udp_hdr_valid(accepted_header),
    .s_udp_hdr_ready(header_ready),
    .s_eth_dest_mac(next_hop_mac),
    .s_eth_src_mac(local_mac),
    .s_eth_type(16'h0800),
    .s_ip_version(4'd4),
    .s_ip_ihl(4'd5),
    .s_ip_dscp(6'd0),
    .s_ip_ecn(2'd0),
    .s_ip_identification(16'd0),
    .s_ip_flags(3'b010),
    .s_ip_fragment_offset(13'd0),
    .s_ip_ttl(8'd64),
    .s_ip_header_checksum(16'd0),
    .s_ip_source_ip(local_ip),
    .s_ip_dest_ip(destination_ip),
    .s_udp_source_port(source_port),
    .s_udp_dest_port(destination_port),
    .s_udp_payload_axis_tdata(s_data),
    .s_udp_payload_axis_tvalid(s_valid),
    .s_udp_payload_axis_tready(s_ready),
    .s_udp_payload_axis_tlast(s_last),
    .s_udp_payload_axis_tuser(1'b0),
    .m_udp_hdr_valid(checked_udp_hdr_valid),
    .m_udp_hdr_ready(checked_udp_hdr_ready),
    .m_eth_dest_mac(checked_eth_dest_mac),
    .m_eth_src_mac(checked_eth_src_mac),
    .m_eth_type(checked_eth_type),
    .m_ip_version(checked_ip_version),
    .m_ip_ihl(checked_ip_ihl),
    .m_ip_dscp(checked_ip_dscp),
    .m_ip_ecn(checked_ip_ecn),
    .m_ip_length(checked_ip_length),
    .m_ip_identification(checked_ip_identification),
    .m_ip_flags(checked_ip_flags),
    .m_ip_fragment_offset(checked_ip_fragment_offset),
    .m_ip_ttl(checked_ip_ttl),
    .m_ip_protocol(checked_ip_protocol),
    .m_ip_header_checksum(checked_ip_header_checksum),
    .m_ip_source_ip(checked_ip_source_ip),
    .m_ip_dest_ip(checked_ip_dest_ip),
    .m_udp_source_port(checked_udp_source_port),
    .m_udp_dest_port(checked_udp_dest_port),
    .m_udp_length(checked_udp_length),
    .m_udp_checksum(checked_udp_checksum),
    .m_udp_payload_axis_tdata(checked_udp_payload_axis_tdata),
    .m_udp_payload_axis_tvalid(checked_udp_payload_axis_tvalid),
    .m_udp_payload_axis_tready(checked_udp_payload_axis_tready),
    .m_udp_payload_axis_tlast(checked_udp_payload_axis_tlast),
    .m_udp_payload_axis_tuser(checked_udp_payload_axis_tuser),
    .busy()
);

udp_ip_tx udp_transmitter (
    .clk(clk),
    .rst(reset),
    .s_udp_hdr_valid(checked_udp_hdr_valid),
    .s_udp_hdr_ready(checked_udp_hdr_ready),
    .s_eth_dest_mac(checked_eth_dest_mac),
    .s_eth_src_mac(checked_eth_src_mac),
    .s_eth_type(checked_eth_type),
    .s_ip_version(checked_ip_version),
    .s_ip_ihl(checked_ip_ihl),
    .s_ip_dscp(checked_ip_dscp),
    .s_ip_ecn(checked_ip_ecn),
    .s_ip_identification(checked_ip_identification),
    .s_ip_flags(checked_ip_flags),
    .s_ip_fragment_offset(checked_ip_fragment_offset),
    .s_ip_ttl(checked_ip_ttl),
    .s_ip_protocol(checked_ip_protocol),
    .s_ip_header_checksum(checked_ip_header_checksum),
    .s_ip_source_ip(checked_ip_source_ip),
    .s_ip_dest_ip(checked_ip_dest_ip),
    .s_udp_source_port(checked_udp_source_port),
    .s_udp_dest_port(checked_udp_dest_port),
    .s_udp_length(checked_udp_length),
    .s_udp_checksum(checked_udp_checksum),
    .s_udp_payload_axis_tdata(checked_udp_payload_axis_tdata),
    .s_udp_payload_axis_tvalid(checked_udp_payload_axis_tvalid),
    .s_udp_payload_axis_tready(checked_udp_payload_axis_tready),
    .s_udp_payload_axis_tlast(checked_udp_payload_axis_tlast),
    .s_udp_payload_axis_tuser(checked_udp_payload_axis_tuser),
    .m_ip_hdr_valid(ip_ip_hdr_valid),
    .m_ip_hdr_ready(ip_ip_hdr_ready),
    .m_eth_dest_mac(ip_eth_dest_mac),
    .m_eth_src_mac(ip_eth_src_mac),
    .m_eth_type(ip_eth_type),
    .m_ip_version(ip_ip_version),
    .m_ip_ihl(ip_ip_ihl),
    .m_ip_dscp(ip_ip_dscp),
    .m_ip_ecn(ip_ip_ecn),
    .m_ip_length(ip_ip_length),
    .m_ip_identification(ip_ip_identification),
    .m_ip_flags(ip_ip_flags),
    .m_ip_fragment_offset(ip_ip_fragment_offset),
    .m_ip_ttl(ip_ip_ttl),
    .m_ip_protocol(ip_ip_protocol),
    .m_ip_header_checksum(ip_ip_header_checksum),
    .m_ip_source_ip(ip_ip_source_ip),
    .m_ip_dest_ip(ip_ip_dest_ip),
    .m_ip_payload_axis_tdata(ip_ip_payload_axis_tdata),
    .m_ip_payload_axis_tvalid(ip_ip_payload_axis_tvalid),
    .m_ip_payload_axis_tready(ip_ip_payload_axis_tready),
    .m_ip_payload_axis_tlast(ip_ip_payload_axis_tlast),
    .m_ip_payload_axis_tuser(ip_ip_payload_axis_tuser),
    .busy(),
    .error_payload_early_termination(udp_transmitter_error)
);

ip_eth_tx ipv4_transmitter (
    .clk(clk),
    .rst(reset),
    .s_ip_hdr_valid(ip_ip_hdr_valid),
    .s_ip_hdr_ready(ip_ip_hdr_ready),
    .s_eth_dest_mac(ip_eth_dest_mac),
    .s_eth_src_mac(ip_eth_src_mac),
    .s_eth_type(ip_eth_type),
    .s_ip_dscp(ip_ip_dscp),
    .s_ip_ecn(ip_ip_ecn),
    .s_ip_length(ip_ip_length),
    .s_ip_identification(ip_ip_identification),
    .s_ip_flags(ip_ip_flags),
    .s_ip_fragment_offset(ip_ip_fragment_offset),
    .s_ip_ttl(ip_ip_ttl),
    .s_ip_protocol(ip_ip_protocol),
    .s_ip_source_ip(ip_ip_source_ip),
    .s_ip_dest_ip(ip_ip_dest_ip),
    .s_ip_payload_axis_tdata(ip_ip_payload_axis_tdata),
    .s_ip_payload_axis_tvalid(ip_ip_payload_axis_tvalid),
    .s_ip_payload_axis_tready(ip_ip_payload_axis_tready),
    .s_ip_payload_axis_tlast(ip_ip_payload_axis_tlast),
    .s_ip_payload_axis_tuser(ip_ip_payload_axis_tuser),
    .m_eth_hdr_valid(eth_eth_hdr_valid),
    .m_eth_hdr_ready(eth_eth_hdr_ready),
    .m_eth_dest_mac(eth_eth_dest_mac),
    .m_eth_src_mac(eth_eth_src_mac),
    .m_eth_type(eth_eth_type),
    .m_eth_payload_axis_tdata(eth_eth_payload_axis_tdata),
    .m_eth_payload_axis_tvalid(eth_eth_payload_axis_tvalid),
    .m_eth_payload_axis_tready(eth_eth_payload_axis_tready),
    .m_eth_payload_axis_tlast(eth_eth_payload_axis_tlast),
    .m_eth_payload_axis_tuser(eth_eth_payload_axis_tuser),
    .busy(),
    .error_payload_early_termination(ipv4_transmitter_error)
);

eth_axis_tx ethernet_transmitter (
    .clk(clk),
    .rst(reset),
    .s_eth_hdr_valid(eth_eth_hdr_valid),
    .s_eth_hdr_ready(eth_eth_hdr_ready),
    .s_eth_dest_mac(eth_eth_dest_mac),
    .s_eth_src_mac(eth_eth_src_mac),
    .s_eth_type(eth_eth_type),
    .s_eth_payload_axis_tdata(eth_eth_payload_axis_tdata),
    .s_eth_payload_axis_tkeep(1'b1),
    .s_eth_payload_axis_tvalid(eth_eth_payload_axis_tvalid),
    .s_eth_payload_axis_tready(eth_eth_payload_axis_tready),
    .s_eth_payload_axis_tlast(eth_eth_payload_axis_tlast),
    .s_eth_payload_axis_tuser(eth_eth_payload_axis_tuser),
    .m_axis_tdata(tx_axis_tdata),
    .m_axis_tkeep(tx_axis_tkeep),
    .m_axis_tvalid(tx_axis_tvalid),
    .m_axis_tready(tx_axis_tready),
    .m_axis_tlast(tx_axis_tlast),
    .m_axis_tuser(tx_axis_tuser),
    .busy()
);

wire [7:0] mac_data,gmii_data;
wire mac_valid,mac_ready,mac_last,mac_user,gmii_enable,gmii_error;
wire fifo_overflow,fifo_bad_frame;
// Store complete Ethernet frames before crossing to the physical MAC clock.
// Full FIFO backpressures the producer; oversized/bad frames are discarded.
axis_async_fifo #(.DEPTH(4096),.DATA_WIDTH(8),.KEEP_ENABLE(0),.KEEP_WIDTH(1),
 .LAST_ENABLE(1),.ID_ENABLE(0),.DEST_ENABLE(0),.USER_ENABLE(1),.USER_WIDTH(1),
 .RAM_PIPELINE(1),.FRAME_FIFO(1),.DROP_OVERSIZE_FRAME(1),.DROP_BAD_FRAME(1),.DROP_WHEN_FULL(0)) transmit_fifo(
 .s_clk(clk),.s_rst(reset),.s_axis_tdata(tx_axis_tdata),.s_axis_tkeep(1'b1),
 .s_axis_tvalid(tx_axis_tvalid),.s_axis_tready(tx_axis_tready),.s_axis_tlast(tx_axis_tlast),
 .s_axis_tid(8'd0),.s_axis_tdest(8'd0),.s_axis_tuser(tx_axis_tuser),
 .m_clk(gtx_clk),.m_rst(gtx_reset),.m_axis_tdata(mac_data),.m_axis_tkeep(),
 .m_axis_tvalid(mac_valid),.m_axis_tready(mac_ready),.m_axis_tlast(mac_last),
 .m_axis_tid(),.m_axis_tdest(),.m_axis_tuser(mac_user),.s_pause_req(1'b0),.s_pause_ack(),.m_pause_req(1'b0),.m_pause_ack(),
 .s_status_overflow(fifo_overflow),.s_status_bad_frame(fifo_bad_frame),.s_status_good_frame(),
 .m_status_overflow(),.m_status_bad_frame(),.m_status_good_frame());
axis_gmii_tx #(.ENABLE_PADDING(1),.MIN_FRAME_LENGTH(64)) physical_mac(
 .clk(gtx_clk),.rst(gtx_reset),.s_axis_tdata(mac_data),.s_axis_tvalid(mac_valid),
 .s_axis_tready(mac_ready),.s_axis_tlast(mac_last),.s_axis_tuser(mac_user),
 .gmii_txd(gmii_data),.gmii_tx_en(gmii_enable),.gmii_tx_er(gmii_error),
 .ptp_ts(96'd0),.m_axis_ptp_ts(),.m_axis_ptp_ts_tag(),.m_axis_ptp_ts_valid(),
 .clk_enable(1'b1),.mii_select(1'b0),.cfg_ifg(8'd12),.cfg_tx_enable(1'b1),
 .start_packet(),.error_underflow(tx_underflow));
// The default keeps the previously verified +90-degree clock arrangement.
// PHY-delay candidate uses the SAME gtx_clk as all five data/control ODDRs.
generate if(USE_SERDES_TX)begin: shared_clock_pins
 wcis_rgmii_tx_serdes transmit_pins(
  .clk125(gtx_clk),.clk250(gtx_clk250),.reset(gtx_reset),
  .gmii_data(gmii_data),.gmii_enable(gmii_enable),.gmii_error(gmii_error),
  .rgmii_tx_clk(rgmii_tx_clk),.rgmii_tx_ctl(rgmii_tx_ctl),.rgmii_txd(rgmii_txd));
end else begin: ddr_pins
ssio_ddr_out #(.TARGET(TARGET),.IODDR_STYLE("IODDR"),
 .USE_CLK90(USE_PHY_TX_DELAY ? "FALSE" : "TRUE"),.WIDTH(5)) transmit_pins(
 .clk(gtx_clk),.clk90(gtx_clk90),.input_d1({gmii_enable,gmii_data[3:0]}),
 .input_d2({gmii_enable^gmii_error,gmii_data[7:4]}),
 .output_clk(rgmii_tx_clk),.output_q({rgmii_tx_ctl,rgmii_txd}));
end endgenerate
assign packet_error=udp_transmitter_error|ipv4_transmitter_error|fifo_overflow|fifo_bad_frame;
endmodule
