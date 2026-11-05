`timescale 1ns/1ps
module tb_jpeg_customop;
    parameter W=64,H=16;
    reg clk=0,ra_clk=0;
    always #2.5 clk=~clk;
    initial begin #1;forever #5 ra_clk=~ra_clk;end
    reg rst_n=0,ra_rst_n=0;
    reg [31:0] itf_ra_awaddr=0,itf_ra_awdata=0,itf_ra_araddr=0;
    reg itf_ra_awvalid=0,itf_ra_arvalid=0,itf_ra_rready=0;
    wire itf_ra_awready,itf_ra_arready,itf_ra_rvalid;
    wire [31:0] itf_ra_rdata,itf_awaddr,itf_araddr,itf_arinfo;
    wire [511:0] itf_awdata;
    wire [71:0] itf_awinfo;
    wire itf_awvalid,itf_arvalid,itf_rready;
    reg itf_awready=0,itf_arready=0,itf_rvalid=0;
    reg [511:0] itf_rdata=0;
    reg [31:0] itf_rinfo=1;
    wcis_recording_customop #(.JPEG_WIDTH(W),.JPEG_HEIGHT(H)) dut(.*);
    reg [7:0] memory[0:65535];
    reg [31:0] random_state=32'h623eebf7;
    string directory;
    integer format=0,input_bytes,capacity=8192,reads=0,writes=0,i,j,delay_count=0;
    integer pending_address=0,watchdog=0,f,frame;
    reg pending=0,stalled_read=0,stalled_write=0;
    reg [31:0] held_read,status,value,length;
    reg [607:0] held_write;
    localparam SRC=32'h1000,DST=32'h4000,REG=32'h400c2100;
    always @(negedge clk) begin
        random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        itf_awready=random_state[2] || random_state[8];
        itf_arready=!pending && !itf_rvalid && (random_state[5] || random_state[11]);
    end
    always @(posedge clk) begin
        if(!rst_n) begin pending<=0;itf_rvalid<=0;end
        else begin
            watchdog=watchdog+1;
            if(watchdog>500000) $fatal(1,"DMA watchdog");
            if(stalled_read && (!itf_arvalid || itf_araddr!==held_read)) $fatal(1,"AR changed under stall");
            if(stalled_write && (!itf_awvalid || {itf_awaddr,itf_awdata,itf_awinfo[70:7]}!==held_write)) $fatal(1,"AW changed under stall");
            stalled_read=itf_arvalid && !itf_arready;held_read=itf_araddr;
            stalled_write=itf_awvalid && !itf_awready;held_write={itf_awaddr,itf_awdata,itf_awinfo[70:7]};
            if(itf_arvalid && itf_arready) begin
                if(itf_arinfo!==1 || itf_araddr[5:0]!==0 || itf_araddr<SRC || itf_araddr+64>SRC+input_bytes)
                    $fatal(1,"out-of-bounds/invalid DDR read %h",itf_araddr);
                if(pending || itf_rvalid) $fatal(1,"overlapping native read");
                pending<=1;pending_address<=itf_araddr;delay_count<=random_state[17:14];reads=reads+1;
            end
            if(pending && !itf_rvalid) begin
                if(delay_count>0) delay_count<=delay_count-1;
                else begin
                    for(j=0;j<64;j=j+1) itf_rdata[j*8 +: 8]<=memory[pending_address+j];
                    itf_rvalid<=1;pending<=0;
                end
            end
            if(itf_rvalid && itf_rready) itf_rvalid<=0;
            if(itf_awvalid && itf_awready) begin
                if(itf_awinfo[6:0]!==1 || itf_awinfo[71]!==0 || itf_awaddr[5:0]!==0)
                    $fatal(1,"invalid native write");
                for(j=0;j<64;j=j+1) if(itf_awinfo[7+j]) begin
                    if(itf_awaddr+j<DST || itf_awaddr+j>=DST+capacity) $fatal(1,"write outside capacity");
                    memory[itf_awaddr+j]<=itf_awdata[j*8 +: 8];
                end
                writes=writes+1;
            end
        end
    end
    task wr(input [31:0] address,input [31:0] data);
        begin
            @(negedge ra_clk);itf_ra_awaddr=address;itf_ra_awdata=data;itf_ra_awvalid=1;
            do @(posedge ra_clk);while(!itf_ra_awready);
            @(negedge ra_clk);itf_ra_awvalid=0;
        end
    endtask
    task rd(input [31:0] address,output [31:0] data);
        begin
            @(negedge ra_clk);itf_ra_araddr=address;itf_ra_arvalid=1;
            do @(posedge ra_clk);while(!itf_ra_arready);
            @(negedge ra_clk);itf_ra_arvalid=0;
            while(!itf_ra_rvalid) @(negedge ra_clk);
            data=itf_ra_rdata;
            repeat(2) begin @(negedge ra_clk);if(!itf_ra_rvalid || itf_ra_rdata!==data) $fatal(1,"CSR response changed");end
            itf_ra_rready=1;@(negedge ra_clk);itf_ra_rready=0;
        end
    endtask
    task finish_job;
        begin
            status=0;
            while(!(status&2)) begin
                rd(REG+4,status);
                rd(32'h400c2000,value);
                if(value!==32'h46414331) $fatal(1,"FAC1 lost during JPEG");
            end
            if(status[0]) $fatal(1,"done while busy");
        end
    endtask
    task reject_descriptor;
        begin
            wr(REG,1);finish_job();
            if(status[7:4]!==1 || reads || writes) $fatal(1,"invalid descriptor touched memory");
        end
    endtask
    initial begin
        if(!$value$plusargs("vectors=%s",directory)) $fatal(1,"missing vectors");
        if(!$value$plusargs("format=%d",format)) format=0;
        input_bytes=W*H*(format ? 4:2);
        for(i=0;i<65536;i=i+1) memory[i]=8'ha5;
        $readmemh({directory,"/source0.hex"},memory,SRC,SRC+input_bytes-1);
        repeat(8) @(negedge ra_clk);rst_n=1;ra_rst_n=1;
        repeat(8) @(negedge ra_clk);
        rd(REG,value);if(value!==32'h4a504731) $fatal(1,"JPG1 missing");
        rd(32'h400c2000,value);if(value!==32'h46414331) $fatal(1,"FAC1 missing");
        rd(32'h400c00c0,value);if(value!==32'h20230628) $fatal(1,"adder ID missing");
        wr(REG+16,100);wr(REG+20,SRC);wr(REG+24,DST);wr(REG+28,capacity);wr(REG+32,format);
        wr(REG+20,SRC+1);reject_descriptor();wr(REG+20,SRC);
        wr(REG+24,SRC);reject_descriptor();wr(REG+24,DST);
        wr(REG+24,32'h07ffffc0);reject_descriptor();wr(REG+24,DST);
        capacity=64;wr(REG+28,capacity);wr(REG,1);finish_job();
        if(status[7:4]!==3) $fatal(1,"capacity overflow not reported: %h",status);
        for(frame=0;frame<2;frame=frame+1) begin
            $readmemh($sformatf("%s/source%0d.hex",directory,frame),memory,SRC,SRC+input_bytes-1);
            for(i=DST-64;i<DST+8192+64;i=i+1) memory[i]=8'ha5;
            capacity=8192;reads=0;writes=0;
            wr(REG+16,101+frame);wr(REG+28,capacity);wr(REG,1);
            // In-flight reconfiguration must be rejected and must not change input.
            wr(REG+20,SRC+64);
            finish_job();
            if(status[7:4]!==0 || !status[3]) $fatal(1,"JPEG failed or busy write not rejected %h",status);
            rd(REG+20,value);if(value!==SRC) $fatal(1,"busy reconfiguration changed descriptor");
            rd(REG+8,value);if(value!==101+frame) $fatal(1,"frame ID mismatch");
            rd(REG+12,length);
            if(length<100 || length>=capacity) $fatal(1,"invalid JPEG length");
            if(reads!=input_bytes/64 || writes!=(length+63)/64) $fatal(1,"DMA transaction count mismatch");
            for(i=DST-64;i<DST;i=i+1) if(memory[i]!==8'ha5) $fatal(1,"prefix guard changed");
            for(i=DST+length;i<DST+capacity+64;i=i+1) if(memory[i]!==8'ha5) $fatal(1,"tail mask/capacity guard changed");
            f=$fopen($sformatf("frame%0d.jpg",frame),"wb");
            for(i=0;i<length;i=i+1) $fwrite(f,"%c",memory[DST+i]);
            $fclose(f);
            rd(REG+48,value);
            $display("FRAME index=%0d bytes=%0d cycles=%0d reads=%0d writes=%0d",frame,length,value,reads,writes);
        end
        $display("PASS jpeg_customop format=%0d",format);
        $finish;
    end
endmodule
