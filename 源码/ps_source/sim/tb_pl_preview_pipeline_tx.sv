`timescale 1ps/1ps
// Camera -> actual JPEG -> WJP1 -> TX-only Ethernet stack -> RGMII capture.
// No synthetic JPEG injection and no forcing of internal MAC/FIFO state.
module tb_pl_preview_pipeline_tx;
    parameter TARGET="SIM",USE_SERDES_TX=0;
    parameter integer W=64,H=16,TOTAL_W=W+280,TOTAL_H=H+45,FRAMES=3;
    reg clk=0;always #3333 clk=~clk;
    reg cam_clk=0;always #6734 cam_clk=~cam_clk;
    reg gtx_clk=0;always #4000 gtx_clk=~gtx_clk;
    // Rising edges align with the same-PLL 125 MHz CLKDIV (first at 4 ns).
    reg gtx_clk250=0;initial begin #2000;forever #2000 gtx_clk250=~gtx_clk250;end
    reg gtx_clk90=0;initial begin #2000;forever #4000 gtx_clk90=~gtx_clk90;end
    reg reset=0,cam_locked=1,cam_vsync=0,cam_de=0;
    reg [23:0] cam_rgb=0;
    wire rgmii_tx_clk,rgmii_tx_ctl;wire [3:0] rgmii_txd;
    wire [7:0] jpeg_data,udp_data;wire jpeg_valid,jpeg_ready,jpeg_sof,jpeg_last,source_abort;
    wire [31:0] frame_id,jpeg_frames,rejected_frames,udp_frames,aborted_frames,udp_packets;
    wire packetizer_busy,udp_hvalid,udp_hready,udp_valid,udp_ready,udp_last,idle;
    wire [15:0] udp_length;
    wire tx_underflow,packet_error,net_packet_error,configuration_error;
    wire [7:0] piped_data;wire piped_valid,piped_last,piped_ready;
    wcis_udp_payload_pipe payload_pipe(
        .clk(clk),.reset(reset),.s_data(udp_data),.s_valid(udp_valid),.s_last(udp_last),.s_ready(udp_ready),
        .m_data(piped_data),.m_valid(piped_valid),.m_last(piped_last),.m_ready(piped_ready));
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
    wcis_jpeg_network_tx #(.TARGET(TARGET),.USE_SERDES_TX(USE_SERDES_TX)) network(
        .clk(clk),.reset(reset),.gtx_clk(gtx_clk),.gtx_clk90(gtx_clk90),.gtx_clk250(gtx_clk250),.gtx_reset(reset),
        .local_mac(48'h025743495302),.local_ip(32'hc0a801f0),.destination_ip(32'hc0a80166),
        .next_hop_mac(48'h020000000002),.source_port(16'd5004),.destination_port(16'd5004),
        .s_hdr_valid(udp_hvalid),.s_hdr_ready(udp_hready),.s_udp_length(udp_length),
        .s_data(piped_data),.s_valid(piped_valid),.s_last(piped_last),.s_ready(piped_ready),
        .rgmii_tx_clk(rgmii_tx_clk),.rgmii_txd(rgmii_txd),.rgmii_tx_ctl(rgmii_tx_ctl),
        .packet_error(net_packet_error),.configuration_error(configuration_error),.tx_underflow(tx_underflow));
    reg [7:0] ethernet[0:2047];
    integer capture,size=0,ethernet_frames=0;
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
        noise=$test$plusargs("NOISE");capture=$fopen("ethernet-stream.bin","wb");
        #20000;reset=1;#100000;reset=0;
        #200000;
        for(integer f=0;f<FRAMES;f=f+1)camera_frame();
        @(negedge cam_clk);cam_vsync=0;cam_de=0;
        wait(idle);#100000000;
        if(tx_underflow||net_packet_error||configuration_error||packet_error||jpeg_frames==0)
            $fatal(1,"Pipeline status error");
        $fclose(capture);
        $display("PASS pipeline input=%0d JPEG=%0d rejected=%0d UDP=%0d aborted=%0d packets=%0d ethernet=%0d noise=%0d",FRAMES,jpeg_frames,rejected_frames,udp_frames,aborted_frames,udp_packets,ethernet_frames,noise);
        $finish;
    end
    initial begin #200000000000.0;$fatal(1,"Pipeline deadline");end
endmodule
