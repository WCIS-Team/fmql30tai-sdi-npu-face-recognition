`timescale 1ns/1ps
module tb_case_registers;
    reg clk=0, camclk=0;
    always #7 clk=~clk;
    always #5 camclk=~camclk;
    reg rstn=0, camvs=0;
    reg [8:0] awaddr=0, araddr=0;
    reg [31:0] wd=0;
    reg [3:0] strobe=0;
    reg av=0, wv=0, arv=0;
    wire awready,wready,arready,rv;
    wire [31:0] rd;
    wire [1:0] resp,word,applied;
    wire cv,cr,gv,gd;
    wire [23:0] gp;
    wire [31:0] seen,selected,dropped;
    frame_ctrl ctrl(
        .S_AXI_ACLK(clk),.S_AXI_ARESETN(rstn),
        .S_AXI_AWADDR(awaddr),.S_AXI_AWPROT(3'd0),.S_AXI_AWVALID(av),.S_AXI_AWREADY(awready),
        .S_AXI_WDATA(wd),.S_AXI_WSTRB(strobe),.S_AXI_WVALID(wv),.S_AXI_WREADY(wready),
        .S_AXI_ARADDR(araddr),.S_AXI_ARPROT(3'd0),.S_AXI_ARVALID(arv),.S_AXI_ARREADY(arready),
        .S_AXI_RDATA(rd),.S_AXI_RRESP(resp),.S_AXI_RVALID(rv),.S_AXI_RREADY(1'b1),
        .dvp_pclk(camclk),.dvp_prst_n(rstn),.dvp_vsync_in(gv),.dvp_href_in(gd),.dvp_db_in(gp),
        .wr_wfifo_err(1'b0),.rd_rfifo_err(1'b0),.wr_done_pulse(1'b0),.network_running(1'b0),
        .wr_buf_index(2'd0),.rd_buf_index(2'd0),.dvp_ov(1'b0),
        .M01_AXI_ACLK(clk),.M01_AXI_ARESETN(rstn),.sys_rst_n(rstn),
        .sdi_diag_words({32'd50000000,288'd0,32'd0,32'd1,32'h53444932}),
        .rate_cfg_valid(cv),.rate_cfg_word(word),.rate_cfg_ready(cr),.rate_cfg_applied(applied));
    wcis_frame_rate_gate gate(
        .cfg_clk(clk),.cam_clk(camclk),.reset(!rstn),.cfg_valid(cv),.cfg_word(word),
        .cfg_ready(cr),.cfg_applied(applied),.s_vsync(camvs),.s_href(1'b0),.s_data(24'd0),
        .m_vsync(gv),.m_href(gd),.m_data(gp),.seen_frames(seen),.selected_frames(selected),.dropped_frames(dropped));
    task write_reg(input [8:0] addr,input [31:0] value,input [3:0] bytes);
        begin
            @(negedge clk); awaddr=addr; wd=value; strobe=bytes; av=1; wv=1;
            @(posedge clk); while(!(awready && wready)) @(posedge clk);
            @(negedge clk); av=0; wv=0;
            repeat(3) @(negedge clk);
        end
    endtask
    task expect_reg(input [8:0] addr,input [31:0] want);
        begin
            @(negedge clk); araddr=addr; arv=1;
            @(posedge clk); while(!arready) @(posedge clk);
            #1;
            while(!rv) begin @(posedge clk); #1; end
            if(rd!==want || resp!==0) $fatal(1,"CSR %h got %h wanted %h",addr,rd,want);
            @(negedge clk); arv=0;
            repeat(3) @(negedge clk);
        end
    endtask
    task boundary;
        begin
            @(negedge camclk); camvs=1;
            repeat(3) @(negedge camclk);
            camvs=0;
            repeat(8) @(negedge clk);
        end
    endtask
    initial begin
        #31 rstn=1; repeat(10) @(negedge clk);
        expect_reg('h0b8,1); expect_reg('h0bc,1); expect_reg('h0c0,32'h57434953);
        expect_reg('h100,32'h53444932); expect_reg('h104,1); expect_reg('h130,50000000);
        write_reg('h100,32'hdeadbeef,15); expect_reg('h100,32'h53444932);
        write_reg('h0b8,3,1); expect_reg('h0bc,9);
        write_reg('h0b8,1,1); expect_reg('h0b8,7);
        write_reg('h0b8,2,2); expect_reg('h0b8,7);
        boundary(); expect_reg('h0bc,3);
        write_reg('h0b8,2,1); expect_reg('h0b8,2);
        boundary(); expect_reg('h0bc,2);
        write_reg('h020,3,1); expect_reg('h020,3);
        write_reg('h0b8,1,1); boundary(); expect_reg('h0bc,1);
        $display("PASS case_registers: real vendor AXI-Lite, applied/pending/busy rejection, byte strobe, legacy 0x20");
        $finish;
    end
    initial begin #100000; $fatal(1,"CSR test timed out"); end
endmodule
