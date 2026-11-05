`timescale 1ns/1ps
module tb_jpeg_network;
    parameter integer PAYLOAD_BYTES=1440;
    reg clk=0;always #2.5 clk=~clk;
    reg gtx_clk=0;always #4 gtx_clk=~gtx_clk;
    reg gtx_clk90=0;initial begin #2;forever #4 gtx_clk90=~gtx_clk90;end
    reg rgmii_rx_clk=0;always #4 rgmii_rx_clk=~rgmii_rx_clk;
    reg reset=0,gtx_reset=0;
    reg [3:0] rgmii_rxd=0;reg rgmii_rx_ctl=0;
    wire rgmii_tx_clk,rgmii_tx_ctl;wire [3:0] rgmii_txd;
    reg [47:0] local_mac=48'h025743495302;
    reg [31:0] local_ip=32'hc0a80172,destination_ip=32'hc0a80166;
    reg [31:0] gateway_ip=32'hc0a80101,subnet_mask=32'hffffff00;
    reg [15:0] source_port=5004,destination_port=5004;
    reg s_hdr_valid=0,s_valid=0,s_last=0;reg [7:0] s_data=0;
    wire s_hdr_ready,s_ready;wire [15:0] s_udp_length=PAYLOAD_BYTES+8;
    wire [1:0] speed;wire arp_failed,tx_underflow,rx_bad_fcs;
    reg bad_seen=0;
    reg [7:0] arp[0:71],payload[0:PAYLOAD_BYTES-1];
    string arpfile,payloadfile,filename;
    integer output_file=0,frame_count=0,i;
    reg [3:0] lower;reg valid_lower;
    wcis_jpeg_network #(.TARGET("SIM")) dut(.*);
    always @(posedge clk) if(rx_bad_fcs)bad_seen<=1;
    always @(posedge rgmii_tx_clk) begin #0.1;lower=rgmii_txd;valid_lower=rgmii_tx_ctl;end
    always @(negedge rgmii_tx_clk) begin
        #0.1;
        if(valid_lower) begin
            if(!rgmii_tx_ctl)$fatal(1,"TX error on RGMII");
            if(!output_file)begin
                filename=$sformatf("ethernet_%0d.bin",frame_count);
                output_file=$fopen(filename,"wb");if(!output_file)$fatal(1,"Output open");
            end
            $fwrite(output_file,"%c",{rgmii_txd,lower});
        end else if(output_file)begin
            $fclose(output_file);output_file=0;frame_count=frame_count+1;
        end
    end
    task send_arp(input bit corrupt);
        integer n;reg [7:0] octet;
        begin
            @(negedge rgmii_rx_clk);#1;
            for(n=0;n<72;n=n+1)begin
                octet=arp[n];if(corrupt&&n==71)octet=octet^1;
                rgmii_rxd=octet[3:0];rgmii_rx_ctl=1;
                @(posedge rgmii_rx_clk);#1;rgmii_rxd=octet[7:4];
                @(negedge rgmii_rx_clk);#1;
            end
            rgmii_rx_ctl=0;rgmii_rxd=0;
        end
    endtask
    initial begin
        if(!$value$plusargs("ARP=%s",arpfile)||!$value$plusargs("PAYLOAD=%s",payloadfile))$fatal(1,"Fixtures required");
        $readmemh(arpfile,arp);$readmemh(payloadfile,payload);
        // Assert a real reset after clocks start; do not depend on time-zero
        // event ordering of upstream declaration-initialised FIFO pointers.
        #20;@(negedge clk);reset=1;gtx_reset=1;
        #100;@(negedge clk);reset=0;gtx_reset=0;
        #20000;
        send_arp(1);#10000;
        if(frame_count!=0||!bad_seen)$fatal(1,"Bad Ethernet FCS was not rejected");
        send_arp(0);wait(frame_count==1);$display("ARP_REPLY time=%0t",$time);
        @(negedge clk);s_hdr_valid=1;
        @(posedge clk);while(!s_hdr_ready)@(posedge clk);
        @(negedge clk);s_hdr_valid=0;$display("UDP_HEADER_ACCEPTED time=%0t",$time);
        for(i=0;i<PAYLOAD_BYTES;i=i+1)begin
            s_data=payload[i];s_valid=1;s_last=(i==PAYLOAD_BYTES-1);
            @(posedge clk);while(!s_ready)@(posedge clk);
            @(negedge clk);
        end
        s_valid=0;s_last=0;$display("UDP_PAYLOAD_ACCEPTED time=%0t",$time);
        wait(frame_count==2);#1000;
        if(arp_failed||tx_underflow||speed!=2)$fatal(1,"MAC/UDP status failure");
        $display("PASS jpeg_network 1G RGMII ARP UDP checksum and FCS");$finish;
    end
    initial begin #200000;$fatal(1,"Network simulation deadline frames=%0d speed=%0d byte=%0d ready=%b valid=%b",frame_count,speed,i,s_ready,s_valid);end
endmodule
