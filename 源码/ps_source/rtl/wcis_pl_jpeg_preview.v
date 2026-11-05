`timescale 1ns/1ps
// Pure PL video path: raw SDI RGB -> JPEG -> UDP -> RGMII. No DDR master,
// PS pixel copies, VPU, model ownership or NPU clock changes in this module.
module wcis_pl_jpeg_preview(
    input wire hp_clk,gp_clk,reset,cam_clk,cam_locked,cam_vsync,cam_de,
    input wire [23:0] cam_rgb,
    input wire [31:0] awaddr,awdata,input wire awvalid,output wire awready,
    input wire [31:0] araddr,input wire arvalid,output wire arready,
    output wire [31:0] rdata,output wire rvalid,input wire rready,
    output wire legacy_awvalid,legacy_arvalid,legacy_rready,
    input wire legacy_awready,legacy_arready,legacy_rvalid,input wire [31:0] legacy_rdata,
    output wire phy_tx_clk,phy_tx_ctl,output wire [3:0] phy_txd,
    output wire phy_reset_n,phy_mdc,output wire phy_mdio_out,phy_mdio_tristate,input wire phy_mdio_in
);
    wire net_clk,gtx_clk,gtx_clk250,locked,feedback,feedback_buf;
    wire pll_150,pll_125,pll_250;
    // The existing shell already uses all five MMCMs. Use a spare PLL with
    // 1500 MHz VCO instead, without changing any existing NPU/video clocks.
    PLLE2_BASE #(.BANDWIDTH("OPTIMIZED"),.CLKIN1_PERIOD(5.0),
        .DIVCLK_DIVIDE(2),.CLKFBOUT_MULT(15),.CLKOUT0_DIVIDE(10),
        .CLKOUT1_DIVIDE(12),.CLKOUT2_DIVIDE(6),.CLKOUT2_PHASE(0.0)) clocks(
        .CLKIN1(hp_clk),.RST(reset),.PWRDWN(1'b0),.CLKFBIN(feedback_buf),.CLKFBOUT(feedback),
        .CLKOUT0(pll_150),.CLKOUT1(pll_125),.CLKOUT2(pll_250),.LOCKED(locked));
    BUFG feedback_clock(.I(feedback),.O(feedback_buf));
    BUFG logic_clock(.I(pll_150),.O(net_clk));
    BUFG transmit_clock(.I(pll_125),.O(gtx_clk));
    BUFG transmit_clock_fast(.I(pll_250),.O(gtx_clk250));
    wire enabled;wire [31:0] session_id,local_ip,destination_ip,gateway_ip,subnet_mask;
    wire [47:0] local_mac,next_hop_mac;wire [15:0] source_port,destination_port;
    wire [1:0] speed;wire arp_failed,tx_underflow,rx_bad_fcs,packet_error;
    (* ASYNC_REG="TRUE" *) reg [1:0] enable_to_network,lock_status_sync;
    reg [3:0] sticky_errors;
    wire [31:0] jpeg_frames,rejected_frames,udp_frames,aborted_frames,udp_packets;
    wire ctrl_awvalid,ctrl_awready,ctrl_arvalid,ctrl_arready,ctrl_rvalid,ctrl_rready;
    wire [31:0] ctrl_rdata;
    wcis_preview_csr_router router(
        .clk(gp_clk),.reset(reset),.awaddr(awaddr),.araddr(araddr),
        .awvalid(awvalid),.awready(awready),.arvalid(arvalid),.arready(arready),
        .rdata(rdata),.rvalid(rvalid),.rready(rready),
        .legacy_awvalid(legacy_awvalid),.legacy_awready(legacy_awready),
        .legacy_arvalid(legacy_arvalid),.legacy_arready(legacy_arready),
        .legacy_rvalid(legacy_rvalid),.legacy_rdata(legacy_rdata),.legacy_rready(legacy_rready),
        .preview_awvalid(ctrl_awvalid),.preview_awready(ctrl_awready),
        .preview_arvalid(ctrl_arvalid),.preview_arready(ctrl_arready),
        .preview_rvalid(ctrl_rvalid),.preview_rdata(ctrl_rdata),.preview_rready(ctrl_rready));
    wcis_preview_registers #(.TX_ONLY_SERDES(1)) registers(
        .clk(gp_clk),.reset(reset),.awaddr(awaddr),.awdata(awdata),.awvalid(ctrl_awvalid),.awready(ctrl_awready),
        .araddr(araddr),.arvalid(ctrl_arvalid),.arready(ctrl_arready),.rdata(ctrl_rdata),.rvalid(ctrl_rvalid),.rready(ctrl_rready),
        .enable(enabled),.phy_reset_n(phy_reset_n),.session_id(session_id),.local_ip(local_ip),
        .destination_ip(destination_ip),.gateway_ip(gateway_ip),.subnet_mask(subnet_mask),
        .local_mac(local_mac),.next_hop_mac(next_hop_mac),.source_port(source_port),.destination_port(destination_port),
        .net_clk(net_clk),.speed(speed),.clock_locked(lock_status_sync[1]),.jpeg_frames(jpeg_frames),
        .rejected_frames(rejected_frames),.udp_frames(udp_frames),.aborted_frames(aborted_frames),
        .udp_packets(udp_packets),.arp_failed(sticky_errors[0]),.tx_underflow(sticky_errors[1]),
        .rx_bad_fcs(sticky_errors[2]),.packet_error(sticky_errors[3]),
        .phy_mdc(phy_mdc),.phy_mdio_out(phy_mdio_out),.phy_mdio_tristate(phy_mdio_tristate),.phy_mdio_in(phy_mdio_in));
    // One atomic, held configuration crosses into the encoder/network clock.
    // Reset this mailbox on disable to cancel any old in-flight configuration.
    wire configuration_reset=reset||!enabled;
    reg configuration_sent,network_enabled;
    always @(posedge net_clk or posedge reset)begin
        if(reset)begin enable_to_network<=0;lock_status_sync<=0;end
        else begin enable_to_network<={enable_to_network[0],enabled};lock_status_sync<={lock_status_sync[0],locked};end
    end
    wire configuration_ready,configuration_valid;
    wire [223:0] configuration_payload;
    reg [31:0] net_session,net_local_ip,net_destination_ip;
    reg [47:0] net_mac,net_next_hop_mac;reg [15:0] net_source_port,net_destination_port;
    always @(posedge gp_clk)begin
        if(reset||!enabled)configuration_sent<=0;
        else if(configuration_ready)configuration_sent<=1;
    end
    wcis_cdc_mailbox #(.WIDTH(224)) configuration(
        .reset(configuration_reset),.s_clk(gp_clk),.m_clk(net_clk),
        .s_valid(enabled&&!configuration_sent),.s_ready(configuration_ready),
        .s_data({session_id,local_ip,destination_ip,local_mac,next_hop_mac,source_port,destination_port}),
        .m_valid(configuration_valid),.m_ready(1'b1),.m_data(configuration_payload));
    always @(posedge net_clk)begin
        // enable_to_network asserts reset asynchronously and releases only on
        // this clock. Do not also feed the HP-domain reset into this bank's
        // synchronous enable/data muxes (200 -> 150 MHz, 1.667 ns edge gap).
        if(!enable_to_network[1])network_enabled<=0;
        else if(configuration_valid)begin
            {net_session,net_local_ip,net_destination_ip,net_mac,net_next_hop_mac,
                net_source_port,net_destination_port}<=configuration_payload;
            network_enabled<=1;
        end
    end
    wire common_reset=reset||!locked||!enabled||!network_enabled;
    (* ASYNC_REG="TRUE" *) reg [2:0] net_reset_sync,gtx_reset_sync;
    always @(posedge net_clk or posedge common_reset)
        if(common_reset)net_reset_sync<=7;else net_reset_sync<={net_reset_sync[1:0],1'b0};
    always @(posedge gtx_clk or posedge common_reset)
        if(common_reset)gtx_reset_sync<=7;else gtx_reset_sync<={gtx_reset_sync[1:0],1'b0};
    wire [7:0] jpeg_data,udp_data;wire jpeg_valid,jpeg_ready,jpeg_sof,jpeg_last,source_abort;
    wire [31:0] frame_id;wire packetizer_busy,udp_hvalid,udp_hready,udp_valid,udp_ready,udp_last;
    wire [15:0] udp_length;
    // Retain the 125 MHz MAC pulse at its source, then transfer a level.
    // This status path must not directly feed the 150 MHz sticky register.
    reg underflow_seen;
    wire underflow_status;
    always @(posedge gtx_clk) begin
        if(gtx_reset_sync[2])underflow_seen<=1'b0;
        else if(tx_underflow)underflow_seen<=1'b1;
    end
    wcis_status_sync underflow_crossing(
        .clk(net_clk),.reset(net_reset_sync[2]),
        .s_status(underflow_seen),.m_status(underflow_status));
    always @(posedge net_clk)begin
        if(net_reset_sync[2])sticky_errors<=0;
        else sticky_errors<=sticky_errors|{packet_error,rx_bad_fcs,underflow_status,arp_failed};
    end
    wcis_sdi_jpeg_stream #(.LOGIC_HZ(150000000)) stream(
        .cam_clk(cam_clk),.clk(net_clk),.reset(common_reset),.enable(enabled),.cam_locked(cam_locked),
        .cam_vsync(cam_vsync),.cam_de(cam_de),.cam_rgb(cam_rgb),.m_data(jpeg_data),.m_valid(jpeg_valid),
        .m_sof(jpeg_sof),.m_last(jpeg_last),.m_ready(jpeg_ready),.downstream_idle(!packetizer_busy),
        .m_frame_id(frame_id),.abort_frame(source_abort),.frames_encoded(jpeg_frames),.frames_rejected(rejected_frames));
    wcis_jpeg_udp_packetizer packetizer(
        .clk(net_clk),.reset(net_reset_sync[2]),.session_id(net_session),.s_frame_id(frame_id),
        .s_data(jpeg_data),.s_valid(jpeg_valid),.s_sof(jpeg_sof),.s_last(jpeg_last),.s_ready(jpeg_ready),
        .abort_frame(source_abort),.m_hdr_valid(udp_hvalid),.m_hdr_ready(udp_hready),.m_udp_length(udp_length),
        .m_data(udp_data),.m_valid(udp_valid),.m_ready(udp_ready),.m_last(udp_last),.busy(packetizer_busy),
        .protocol_error(packet_error),.frames_done(udp_frames),.frames_aborted(aborted_frames),.packets_sent(udp_packets));
    // These are a fixed MAC mode and sticky configuration/packet errors,
    // not a measurement of PHY link speed. Management must read the PHY first.
    assign speed=2'b10;
    wire [7:0] piped_udp_data;wire piped_udp_valid,piped_udp_last,piped_udp_ready;
    wcis_udp_payload_pipe payload_pipe(
        .clk(net_clk),.reset(net_reset_sync[2]),.s_data(udp_data),.s_valid(udp_valid),.s_last(udp_last),.s_ready(udp_ready),
        .m_data(piped_udp_data),.m_valid(piped_udp_valid),.m_last(piped_udp_last),.m_ready(piped_udp_ready));
    wcis_jpeg_network_tx #(.TARGET("XILINX"),.USE_SERDES_TX(1)) network(
        .clk(net_clk),.reset(net_reset_sync[2]),.gtx_clk(gtx_clk),.gtx_clk90(1'b0),.gtx_clk250(gtx_clk250),.gtx_reset(gtx_reset_sync[2]),
        .local_mac(net_mac),.local_ip(net_local_ip),.destination_ip(net_destination_ip),.next_hop_mac(net_next_hop_mac),
        .source_port(net_source_port),.destination_port(net_destination_port),
        .s_hdr_valid(udp_hvalid),.s_hdr_ready(udp_hready),.s_udp_length(udp_length),
        .s_data(piped_udp_data),.s_valid(piped_udp_valid),.s_last(piped_udp_last),.s_ready(piped_udp_ready),
        .rgmii_tx_clk(phy_tx_clk),.rgmii_txd(phy_txd),.rgmii_tx_ctl(phy_tx_ctl),
        .configuration_error(arp_failed),.tx_underflow(tx_underflow),.packet_error(rx_bad_fcs));
endmodule
