`timescale 1ns/1ps
module tb_pad_preprocess;
    reg clk=0; always #5 clk=~clk;
    reg reset=1,cmd_valid=0,m_ready=0;
    wire cmd_ready,busy,done; wire [1:0] error;
    reg [31:0] cmd_frame_id,cmd_base_addr,cmd_pitch_bytes;
    reg [15:0] cmd_src_w,cmd_src_h,cmd_roi_x,cmd_roi_y,cmd_roi_w,cmd_roi_h;
    wire [31:0] frame_id; wire m_valid,m_sof,m_eol,m_eof; wire [23:0] m_rgb;
    wire [31:0] araddr; wire [7:0] arlen; wire [2:0] arsize; wire [1:0] arburst;
    wire arvalid,rready; reg arready=0,rvalid=0,rlast=1;
    reg [63:0] rdata=0; reg [1:0] rresp=0;
    wcis_pad_preprocess dut(.*,
        .m_axi_araddr(araddr),.m_axi_arlen(arlen),.m_axi_arsize(arsize),.m_axi_arburst(arburst),
        .m_axi_arvalid(arvalid),.m_axi_arready(arready),.m_axi_rdata(rdata),
        .m_axi_rresp(rresp),.m_axi_rlast(rlast),.m_axi_rvalid(rvalid),.m_axi_rready(rready));
    reg [31:0] config_words[0:21];
    reg [63:0] memory[0:2097151];
    reg [23:0] expected[0:409599];
    string directory;
    integer memory_words,pixels,index=0,cycles=0,total_cycles=0,reads=0;
    integer delay_count=0,read_index=0,pass,active_fault=0,pending=0;
    integer output_file;
    reg [31:0] random_state=32'h20fca763;
    reg output_stalled=0,address_stalled=0;
    reg [26:0] held_output;
    reg [31:0] held_address;
    reg collect=0;
    // Deterministic random backpressure, variable memory latency, and AXI
    // response retention. The memory model resets with the AXI client.
    always @(posedge clk) begin
        if(reset) begin rvalid<=0; pending<=0; delay_count<=0; end
        else begin
            if(arvalid && arready) begin
                if(pending || rvalid) $fatal(1,"multiple outstanding reads");
                if(arlen!==0 || arsize!==3 || arburst!==1 || araddr[2:0]!==0)
                    $fatal(1,"invalid AXI read attributes");
                if(araddr < config_words[1] || (araddr-config_words[1])/8 >= memory_words)
                    $fatal(1,"read outside immutable frame allocation: %h",araddr);
                read_index <= (araddr-config_words[1])/8;
                pending<=1; delay_count<=1+random_state[5:3]; reads<=reads+1;
            end
            if(pending && !rvalid) begin
                if(delay_count!=0) delay_count<=delay_count-1;
                else begin
                    rdata<=memory[read_index]; rvalid<=1;
                    rresp<=(active_fault==1 || (pass==0 && config_words[21]==9 && reads==3)) ? 2 : 0;
                    rlast<=active_fault!=2; pending<=0;
                end
            end
            if(rvalid && rready) begin
                if(!rlast) begin rdata<=64'hbad; rresp<=0; rlast<=1; end
                else begin rvalid<=0; active_fault<=0; end
            end
        end
    end
    always @(negedge clk) begin
        random_state = {random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        arready = random_state[0] || random_state[7];
        m_ready = random_state[3] || random_state[9];
    end
    always @(posedge clk) if(!reset) begin
        total_cycles=total_cycles+1;
        if(total_cycles>25000000) $fatal(1,"watchdog");
        if(output_stalled && (!m_valid || {m_sof,m_eol,m_eof,m_rgb}!==held_output))
            $fatal(1,"output changed under backpressure");
        if(address_stalled && (!arvalid || araddr!==held_address)) $fatal(1,"AR changed under backpressure");
        output_stalled=m_valid && !m_ready; held_output={m_sof,m_eol,m_eof,m_rgb};
        address_stalled=arvalid && !arready; held_address=araddr;
        if(dut.rd_valid && dut.rd_ready) begin
            if(dut.reader.s_x < config_words[10] || dut.reader.s_x >= config_words[10]+config_words[12] ||
               dut.reader.s_y < config_words[11] || dut.reader.s_y >= config_words[11]+config_words[13])
                $fatal(1,"pixel request outside accepted crop");
        end
        if(collect) begin
            cycles=cycles+1;
            if(m_valid && m_ready) begin
                if(index>=pixels || m_rgb!==expected[index])
                    $fatal(1,"pixel %0d actual=%h expected=%h",index,m_rgb,expected[index]);
                if(m_sof!==(index==0) || m_eol!==((index%config_words[8])==config_words[8]-1) || m_eof!==(index==pixels-1))
                    $fatal(1,"pixel boundary mismatch at %0d",index);
                if(frame_id!==config_words[0]) $fatal(1,"frame id changed");
                if(pass==0 && output_file) $fdisplay(output_file,"%06h",m_rgb);
                index=index+1;
            end
        end
    end
    task load_command;
        begin
            cmd_frame_id=config_words[0];cmd_base_addr=config_words[1];cmd_pitch_bytes=config_words[2];
            cmd_src_w=config_words[4];cmd_src_h=config_words[5];
            cmd_roi_x=config_words[10];cmd_roi_y=config_words[11];
            cmd_roi_w=config_words[12];cmd_roi_h=config_words[13];
        end
    endtask
    initial begin
        if(!$value$plusargs("vectors=%s",directory)) $fatal(1,"missing +vectors");
        $readmemh({directory,"/command.hex"},config_words);
        memory_words=config_words[20];pixels=config_words[19];
        $readmemh({directory,"/source.hex"},memory,0,memory_words-1);
        $readmemh({directory,"/expected.hex"},expected,0,pixels-1);
        output_file=$fopen({directory,"/actual.hex"},"w");
        repeat(4) @(negedge clk);reset=0;
        // Fault cases are followed by a clean command without a reset. This
        // proves response draining/rejection does not poison the next frame.
        for(pass=0;pass<(config_words[21]!=0 ? 2:1);pass=pass+1) begin
            if(pass==1 && config_words[21]==8) begin
                // Same address, changed frame: a stale cache would return the
                // previous image even though the new command was accepted.
                memory[0]=memory[0]^64'h0000000000ffffff;
                for(integer k=0;k<pixels;k=k+1) expected[k]=expected[k]^24'hffffff;
                config_words[0]=config_words[0]+1;
            end
            @(negedge clk);load_command();
            if(pass==0) begin
                if(config_words[21]==3) cmd_src_w=0;
                if(config_words[21]==4) cmd_pitch_bytes=7;
                if(config_words[21]==5) cmd_base_addr=32'hfffffff8;
                if(config_words[21]==6) cmd_roi_x=cmd_src_w;
                active_fault=config_words[21]<=2 ? config_words[21] : 0;
            end
            while(!cmd_ready) @(negedge clk);
            cmd_valid=1;index=0;cycles=0;reads=0;collect=1;
            @(negedge clk);cmd_valid=0;
            // Deliberately mutate all live config while busy: the accepted
            // descriptor, frame id and storage location must remain frozen.
            cmd_roi_x=65535;cmd_roi_w=0;cmd_roi_y=65535;cmd_roi_h=0;cmd_frame_id=32'hdeadbeef;cmd_src_w=1;cmd_base_addr=0;
            if(pass==0 && config_words[21]==7) begin
                while(!pending) @(negedge clk);
                collect=0;reset=1;
                repeat(3) @(negedge clk);
                reset=0;output_stalled=0;address_stalled=0;
                if(busy || m_valid || arvalid) $fatal(1,"shared reset did not abort frame");
            end else while(!done) @(negedge clk);
            collect=0;
            if(pass==0 && config_words[21]==9) begin
                if(error!==2 || index==0 || index>=pixels) $fatal(1,"late read error did not invalidate partial frame");
            end else if(pass==0 && config_words[21]>=1 && config_words[21]<=6) begin
                if(error!==config_words[18][1:0] || index!=0) $fatal(1,"fault not rejected cleanly");
                if(config_words[21]>=3 && reads!=0) $fatal(1,"rejected descriptor issued reads");
            end else if(!(pass==0 && config_words[21]==7)) begin
                if(error!==0 || index!=pixels || busy) $fatal(1,"incomplete frame: error %d pixels %d",error,index);
            end
            $display("FRAME pass=%0d pixels=%0d cycles=%0d AXI_reads=%0d error=%0d",pass,index,cycles,reads,error);
        end
        $fclose(output_file);
        $display("PASS pad_preprocess %s",directory);
        $finish;
    end
endmodule
