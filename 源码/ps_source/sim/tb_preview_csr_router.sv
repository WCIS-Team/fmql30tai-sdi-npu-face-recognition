`timescale 1ns/1ps
module tb_preview_csr_router;
    reg clk=0;always #5 clk=~clk;
    reg reset=1;
    reg [31:0] awaddr=0,araddr=0;
    reg awvalid=0,arvalid=0,rready=0;
    wire awready,arready,rvalid;wire [31:0] rdata;
    wire legacy_awvalid,legacy_arvalid,legacy_rready;
    wire preview_awvalid,preview_arvalid,preview_rready;
    reg legacy_awready=0,legacy_arready=0,legacy_rvalid=0;
    reg preview_awready=0,preview_arready=0,preview_rvalid=0;
    reg [31:0] legacy_rdata=32'hfac1,preview_rdata=32'h4e545031;
    wcis_preview_csr_router dut(.*);
    task read_stalled(input bit preview);
        begin
            @(negedge clk);araddr=preview?32'h2200:32'h2100;arvalid=1;
            legacy_arready=0;preview_arready=0;
            repeat(3)begin @(posedge clk);#1;
                if(arready||rvalid)$fatal(1,"accepted stalled read");
            end
            @(negedge clk);legacy_arready=1;preview_arready=1;
            #1;if(legacy_arvalid==preview||preview_arvalid!=preview)$fatal(1,"read selection");
            @(posedge clk);@(negedge clk);arvalid=0;araddr=preview?0:32'h2200;
            // Change addresses and raise both response signals while stalled.
            // The owner must remain the one selected at request handshake.
            legacy_rvalid=1;preview_rvalid=1;rready=0;
            repeat(5)begin @(posedge clk);#1;
                if(!rvalid||rdata!=(preview?32'h4e545031:32'hfac1)||arready||
                   legacy_rready||preview_rready)$fatal(1,"response ownership lost");
            end
            @(negedge clk);rready=1;#1;
            if(legacy_rready==preview||preview_rready!=preview)$fatal(1,"response drain selection");
            @(posedge clk);@(negedge clk);legacy_rvalid=0;preview_rvalid=0;rready=0;
            if(rvalid)$fatal(1,"duplicate response");
        end
    endtask
    initial begin
        repeat(4)@(negedge clk);reset=0;
        for(integer i=0;i<12;i=i+1)begin
            @(negedge clk);awaddr=i[0]?32'h2204:32'h2004;awvalid=1;
            legacy_awready=i[1];preview_awready=!i[1];#1;
            if(awready!=(i[0]?preview_awready:legacy_awready)||
               legacy_awvalid!=!i[0]||preview_awvalid!=i[0])$fatal(1,"write routing");
        end
        @(negedge clk);awvalid=0;
        repeat(4)begin read_stalled(0);read_stalled(1);end
        @(negedge clk);reset=1;awvalid=1;arvalid=1;#1;
        if(awready||arready||legacy_awvalid||preview_awvalid||legacy_arvalid||preview_arvalid)
            $fatal(1,"request admitted during reset");
        $display("PASS preview CSR: legacy/new decode, stalled requests, response ownership, reset isolation");$finish;
    end
    initial begin #20000;$fatal(1,"CSR deadline");end
endmodule
