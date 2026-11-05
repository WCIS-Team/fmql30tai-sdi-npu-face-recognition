`timescale 1ps/1ps
// Camera -> actual JPEG -> WJP1 -> complete Ethernet stack -> RGMII capture.
// No synthetic JPEG injection and no forcing of internal MAC/FIFO state.
module tb_pl_preview_pipeline;
    parameter integer W=64,H=16,TOTAL_W=W+280,TOTAL_H=H+45,FRAMES=3;
    reg clk=0;always #3333 clk=~clk;
    reg cam_clk=0;always #6734 cam_clk=~cam_clk;
    reg gtx_clk=0;always #4000 gtx_clk=~gtx_clk;
    reg gtx_clk90=0;initial begin #2000;forever #4000 gtx_clk90=~gtx_clk90;end
    reg rgmii_rx_clk=0;always #4000 rgmii_rx_clk=~rgmii_rx_clk;
    reg reset=0,cam_locked=1,cam_vsync=0,cam_de=0;
    reg [23:0] cam_rgb=0;
    reg [3:0] rgmii_rxd=0;reg rgmii_rx_ctl=0;
    wire rgmii_tx_clk,rgmii_tx_ctl;wire [3:0] rgmii_txd;
    wire [7:0] jpeg_data,udp_data;wire jpeg_valid,jpeg_ready,jpeg_sof,jpeg_last,source_abort;
    wire [31:0] frame_id,jpeg_frames,rejected_frames,udp_frames,aborted_frames,udp_packets;
    wire packetizer_busy,udp_hvalid,udp_hready,udp_valid,udp_ready,udp_last,idle;
    wire [15:0] udp_length;
    wire [1:0] speed;wire arp_failed,tx_underflow,rx_bad_fcs,packet_error;
    wcis_sdi_jpeg_stream #(.IMAGE_WIDTH(W),.IMAGE_HEIGHT(H),.LOGIC_HZ(150000000)) stream(
        .cam_clk(cam_clk),.clk(clk),.reset(reset),.enable(1'b1),.cam_locked(cam_locked),
        .cam_vsync(cam_vsync),.cam_de(cam_de),.cam_rgb(cam_rgb),.m_data(jpeg_data),.m_valid(jpeg_valid),
        .m_sof(jpeg_sof),.m_last(jpeg_last),.m_ready(jpeg_ready),.downstream_idle(!packetizer_busy),
        .m_frame_id(frame_id),.abort_frame(source_abort),.frames_encoded(jpeg_frames),.frames_rejected(rejected_frames),.idle(idle));
    wcis_jpeg_udp_packetizer #(.IMAGE_WIDTH(W),.IMAGE_HEIGHT(H)) packetizer(
        .clk(clk),.reset(reset),.session_id(32'h23001080),.s_frame_id(frame_id),
        .s_data(jpeg_data),.s_valid(jpeg_valid),.s_sof(jpeg_sof),.s_last(jpeg_last),.s_ready(jpeg_ready),
        .abort_frame(source_abort),.m_hdr_valid(udp_hvalid),.m_hdr_ready(udp_hready),.m_udp_length(udp_length),
        .m_data(udp_data),.m_valid(udp_valid),.m_ready(udp_ready),.m_last(udp_last),.busy(packetizer_busy),
        .protocol_error(packet_error),.frames_done(udp_frames),.frames_aborted(aborted_frames),.packets_sent(udp_packets));
    wcis_jpeg_network #(.TARGET("SIM"),.LOGIC_HZ(150000000)) network(
        .clk(clk),.reset(reset),.gtx_clk(gtx_clk),.gtx_clk90(gtx_clk90),.gtx_reset(reset),
        .local_mac(48'h025743495302),.local_ip(32'hc0a80172),.destination_ip(32'hc0a80166),
        .gateway_ip(32'hc0a80101),.subnet_mask(32'hffffff00),.source_port(16'd5004),.destination_port(16'd5004),
        .s_hdr_valid(udp_hvalid),.s_hdr_ready(udp_hready),.s_udp_length(udp_length),
        .s_data(udp_data),.s_valid(udp_valid),.s_last(udp_last),.s_ready(udp_ready),
        .rgmii_rx_clk(rgmii_rx_clk),.rgmii_rxd(rgmii_rxd),.rgmii_rx_ctl(rgmii_rx_ctl),
        .rgmii_tx_clk(rgmii_tx_clk),.rgmii_txd(rgmii_txd),.rgmii_tx_ctl(rgmii_tx_ctl),
        .speed(speed),.arp_failed(arp_failed),.tx_underflow(tx_underflow),.rx_bad_fcs(rx_bad_fcs));
    reg [7:0] arp[0:71],ethernet[0:2047];
    string arpfile;integer capture,size=0,ethernet_frames=0;
    reg [3:0] lower;reg valid_lower;
    always @(posedge rgmii_tx_clk)begin #100;lower=rgmii_txd;valid_lower=rgmii_tx_ctl;end
    always @(negedge rgmii_tx_clk)begin
        #100;
        if(valid_lower)begin
            if(!rgmii_tx_ctl||size>=2048)$fatal(1,"RGMII transmit error/oversize");
            ethernet[size]={rgmii_txd,lower};size=size+1;
        end else if(size!=0)begin
            $fwrite(capture,"%c%c",8'(size>>8),8'(size));
            for(integer b=7;b>=0;b=b-1)$fwrite(capture,"%c",8'($time>>(b*8)));
            for(integer n=0;n<size;n=n+1)$fwrite(capture,"%c",ethernet[n]);
            size=0;ethernet_frames=ethernet_frames+1;
        end
    end
    task send_arp;
        begin
            @(negedge rgmii_rx_clk);#1000;
            for(integer n=0;n<72;n=n+1)begin
                rgmii_rxd=arp[n][3:0];rgmii_rx_ctl=1;
                @(posedge rgmii_rx_clk);#1000;rgmii_rxd=arp[n][7:4];
                @(negedge rgmii_rx_clk);#1000;
            end
            rgmii_rx_ctl=0;rgmii_rxd=0;
        end
    endtask
    reg [31:0] rng=32'hfa391025;integer noise=0;
    task camera_frame;
        begin
            for(integer y=0;y<TOTAL_H;y=y+1)begin
                for(integer x=0;x<TOTAL_W;x=x+1)begin
                    @(negedge cam_clk);cam_vsync=(y<H);cam_de=(x<W&&y<H);
                    if(cam_de)begin
                        rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);
                        cam_rgb=noise ? rng[23:0] : {8'(x*255/(W-1)),8'(y*255/(H-1)),8'((x*3+y*7)%256)};
                    end
                end
            end
        end
    endtask
    initial begin
        if(!$value$plusargs("ARP=%s",arpfile))$fatal(1,"ARP fixture required");
        noise=$test$plusargs("NOISE");$readmemh(arpfile,arp);capture=$fopen("ethernet-stream.bin","wb");
        #20000;reset=1;#100000;reset=0;
        #20000000;send_arp();#10000000;
        for(integer f=0;f<FRAMES;f=f+1)camera_frame();
        @(negedge cam_clk);cam_vsync=0;cam_de=0;
        wait(idle);#100000000;
        if(arp_failed||tx_underflow||rx_bad_fcs||packet_error||speed!=2||jpeg_frames==0)
            $fatal(1,"Pipeline status error");
        $fclose(capture);
        $display("PASS pipeline input=%0d JPEG=%0d rejected=%0d UDP=%0d aborted=%0d packets=%0d ethernet=%0d noise=%0d",FRAMES,jpeg_frames,rejected_frames,udp_frames,aborted_frames,udp_packets,ethernet_frames,noise);
        $finish;
    end
    initial begin #200000000000;$fatal(1,"Pipeline deadline");end
endmodule
