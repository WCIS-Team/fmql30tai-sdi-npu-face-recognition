`timescale 1ns/1ps
module tb_face_customop;
    reg clk=0,ra_clk=0;
    always #2.5 clk=~clk;
    // Actual board GP=100 MHz, HP=200 MHz. Offset the phase to exercise CDC.
    initial begin #1;forever #5 ra_clk=~ra_clk;end
    reg rst_n=0,ra_rst_n=0;
    reg [31:0] itf_ra_awaddr=0,itf_ra_awdata=0,itf_ra_araddr=0;
    reg itf_ra_awvalid=0,itf_ra_arvalid=0,itf_ra_rready=0;
    wire itf_ra_awready,itf_ra_arready,itf_ra_rvalid;
    wire [31:0] itf_ra_rdata;
    wire [31:0] itf_awaddr,itf_araddr,itf_arinfo;
    wire [511:0] itf_awdata;
    wire [71:0] itf_awinfo;
    wire itf_awvalid,itf_arvalid,itf_rready;
    wire native_write_is_face;
    reg itf_awready=0,itf_arready=0,itf_rvalid=0;
    reg [511:0] itf_rdata=0;
    reg [31:0] itf_rinfo=1;
    wcis_face_customop dut(.*);
    reg [31:0] config_words[0:21];
    reg [63:0] memory[0:2097151];
    reg [23:0] expected[0:409599];
    reg [31:0] random_state=32'ha2cd8761;
    string directory;
    integer memory_words,pixels,out_word,words_total,i,j,cycles=0,delay_count=0,pending_index=0;
    reg pending=0;
    reg [31:0] status,readback,output_base;
    reg [607:0] held_write;
    reg [31:0] held_read;
    reg stalled_write=0,stalled_read=0;
    integer reads=0,writes=0,watchdog=0;
    integer poll_gap=0,progress_every=0;
    // One update per 64-bit word preserves byte strobes while avoiding eight
    // separate array notifications for the same word in large event simulations.
    function automatic [63:0] masked_word(input [63:0] old_word,new_word,input [7:0] enables);
        integer lane;
        begin
            masked_word=old_word;
            for(lane=0;lane<8;lane=lane+1)
                if(enables[lane])masked_word[lane*8 +:8]=new_word[lane*8 +:8];
        end
    endfunction
    always @(negedge clk) begin
        random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        itf_awready=random_state[2] || random_state[8];
        itf_arready=!pending && !itf_rvalid && (random_state[5] || random_state[11]);
    end
    always @(posedge clk) begin
        if(!rst_n) begin pending<=0;itf_rvalid<=0;delay_count<=0;end
        else begin
            watchdog=watchdog+1;
            if(progress_every>0 && watchdog%progress_every==0)
                $display("PROGRESS hp_cycles=%0d reads=%0d writes=%0d",watchdog,reads,writes);
            if(watchdog>100000000) $fatal(1,"watchdog");
            if(stalled_write && (!itf_awvalid || {itf_awaddr,itf_awdata,itf_awinfo[70:7]}!==held_write))
                $fatal(1,"native write changed under stall");
            if(stalled_read && (!itf_arvalid || itf_araddr!==held_read)) $fatal(1,"native AR changed under stall");
            stalled_write=itf_awvalid && !itf_awready;held_write={itf_awaddr,itf_awdata,itf_awinfo[70:7]};
            stalled_read=itf_arvalid && !itf_arready;held_read=itf_araddr;
            if(itf_arvalid && itf_arready) begin
                if(itf_arinfo!==1 || itf_araddr[5:0]!==0) $fatal(1,"invalid native read");
                if(pending || itf_rvalid) $fatal(1,"native read overlap");
                if(itf_araddr<config_words[1] || (itf_araddr-config_words[1])/8+7>=words_total)
                    $fatal(1,"native read outside allocation %h",itf_araddr);
                pending_index<=(itf_araddr-config_words[1])/8;pending<=1;
                delay_count<=random_state[17:14]+1;reads=reads+1;
            end
            if(pending && !itf_rvalid) begin
                if(delay_count>0) delay_count<=delay_count-1;
                else begin
                    for(j=0;j<8;j=j+1) itf_rdata[j*64 +: 64]<=memory[pending_index+j];
                    itf_rvalid<=1;pending<=0;
                end
            end
            if(itf_rvalid && itf_rready) itf_rvalid<=0;
            if(itf_awvalid && itf_awready) begin
                if(itf_awinfo[6:0]!==1 || itf_awinfo[71]!==0 || itf_awaddr[5:0]!==0)
                    $fatal(1,"invalid native write info/address");
                for(j=0;j<8;j=j+1) if(|itf_awinfo[7+j*8 +:8]) begin
                    if((itf_awaddr-config_words[1])/8+j>=words_total) $fatal(1,"write out of range");
                    memory[(itf_awaddr-config_words[1])/8+j]<=masked_word(memory[(itf_awaddr-config_words[1])/8+j],itf_awdata[j*64 +:64],itf_awinfo[7+j*8 +:8]);
                end
                writes=writes+1;
            end
        end
    end
    task write_reg(input [31:0] address,input [31:0] data);
        begin
            @(negedge ra_clk);itf_ra_awaddr=address;itf_ra_awdata=data;itf_ra_awvalid=1;
            do @(posedge ra_clk);while(!itf_ra_awready);
            @(negedge ra_clk);itf_ra_awvalid=0;
        end
    endtask
    task read_reg(input [31:0] address,output [31:0] value);
        begin
            @(negedge ra_clk);itf_ra_araddr=address;itf_ra_arvalid=1;itf_ra_rready=0;
            do @(posedge ra_clk);while(!itf_ra_arready);
            @(negedge ra_clk);itf_ra_arvalid=0;
            while(!itf_ra_rvalid) @(negedge ra_clk);
            // Exercise GP response retention as well as DDR backpressure.
            value=itf_ra_rdata;
            repeat(2) begin @(negedge ra_clk);if(!itf_ra_rvalid || itf_ra_rdata!==value) $fatal(1,"GP response changed");end
            itf_ra_rready=1;@(negedge ra_clk);itf_ra_rready=0;
        end
    endtask
    task wait_face;
        begin
            status=0;
            while(!(status & 2)) begin
                read_reg(32'h400c2004,status);
                if(!(status & 2))repeat(poll_gap)@(negedge ra_clk);
            end
        end
    endtask
    task reject_face;
        begin
            write_reg(32'h400c2000,1);wait_face();
            if(status[7:4]!==1 || reads || writes) $fatal(1,"unsafe descriptor touched DDR or was not rejected");
        end
    endtask
    initial begin
        if(!$value$plusargs("vectors=%s",directory)) $fatal(1,"missing vectors");
        if($value$plusargs("poll_gap=%d",poll_gap))begin end
        if($value$plusargs("progress_every=%d",progress_every))begin end
        $readmemh({directory,"/command.hex"},config_words);
        memory_words=config_words[20];pixels=config_words[19];
        out_word=((memory_words+7)/8)*8+8;
        output_base=config_words[1]+out_word*8;
        words_total=out_word+((pixels*4+63)/64)*8+1024;
        if(words_total>2097152) $fatal(1,"TB RAM limit");
        for(i=0;i<words_total;i=i+1) memory[i]=64'hcafebabecafebabe;
        $readmemh({directory,"/source.hex"},memory,0,memory_words-1);
        $readmemh({directory,"/expected.hex"},expected,0,pixels-1);
        repeat(4) @(negedge ra_clk);rst_n=1;ra_rst_n=1;
        repeat(6) @(negedge ra_clk);
        read_reg(32'h400c00c0,readback);
        if(readback!==32'h20230628) $fatal(1,"legacy adder ID lost");
        read_reg(32'h400c2000,readback);
        if(readback!==32'h46414331) $fatal(1,"FACE ID missing");
        // Run the actual vendor adder through the shared DDR arbiter, then
        // restore the immutable photo vector before testing preprocessing.
        for(i=0;i<16;i=i+1) begin
            for(j=0;j<8;j=j+1) memory[i*8+j]=0;
            memory[i*8]=i;
        end
        write_reg(32'h400c0004,32'h00101000);
        write_reg(32'h400c0008,32'h00101800);
        write_reg(32'h400c0000,1);
        readback=0;
        while(readback==0) read_reg(32'h400c0080,readback);
        // The original completion is from the arithmetic stage; allow its
        // existing output skid register to finish the final accepted write.
        repeat(20) @(negedge ra_clk);
        for(i=0;i<16;i=i+1) if(memory[256+i*8][31:0]!==i+1) $fatal(1,"legacy adder result %0d incorrect",i);
        for(i=0;i<words_total;i=i+1) memory[i]=64'hcafebabecafebabe;
        $readmemh({directory,"/source.hex"},memory,0,memory_words-1);
        reads=0;writes=0;
        write_reg(32'h400c2010,config_words[0]);
        write_reg(32'h400c2014,config_words[1]);write_reg(32'h400c2018,config_words[2]);
        write_reg(32'h400c201c,output_base+1); // invalid output alignment: no DDR side effect
        write_reg(32'h400c2020,{config_words[5][15:0],config_words[4][15:0]});
        write_reg(32'h400c2024,{config_words[7][15:0],config_words[6][15:0]});
        write_reg(32'h400c2028,{config_words[9][15:0],config_words[8][15:0]});
        write_reg(32'h400c202c,{30'd0,config_words[3][0],config_words[17][0]});
        write_reg(32'h400c2030,config_words[16]);
        for(i=0;i<6;i=i+1) write_reg(32'h400c2034+i*4,config_words[10+i]);
        reject_face();
        write_reg(32'h400c201c,config_words[1]); // input/output overlap
        reject_face();
        write_reg(32'h400c201c,32'h08000000); // even one output pixel crosses native window
        reject_face();
        write_reg(32'h400c201c,output_base);
        write_reg(32'h400c2014,32'h08000000); // even one input pixel crosses native window
        reject_face();
        write_reg(32'h400c2014,config_words[1]);
        write_reg(32'h400c2018,32'hfffffff8); // pitch*height must not wrap at 32 bits
        reject_face();
        write_reg(32'h400c2018,config_words[2]);
        write_reg(32'h400c2000,1);
        write_reg(32'h400c2014,32'hbad); // reject mutation of immutable source while busy
        read_reg(32'h400c2014,readback);
        if(readback!==config_words[1]) $fatal(1,"busy config overwritten");
        wait_face();
        if(status[7:4]!==0 || !status[3]) $fatal(1,"job status error %h",status);
        read_reg(32'h400c2008,readback);if(readback!==config_words[0]) $fatal(1,"wrong frame id");
        read_reg(32'h400c200c,readback);if(readback!==pixels) $fatal(1,"wrong pixel count");
        for(i=0;i<pixels;i=i+1) begin
            if(memory[out_word+i/2][(i%2)*32 +: 32]!=={8'd0,expected[i]})
                $fatal(1,"DDR output pixel %0d mismatch: %h expected %h",i,memory[out_word+i/2][(i%2)*32 +:32],expected[i]);
        end
        if(pixels%2 && memory[out_word+pixels/2][63:32]!==32'hcafebabe) $fatal(1,"partial write clobbered adjacent bytes");
        if(writes!=(pixels+15)/16) $fatal(1,"wrong write beat count");
        if(pixels==1) begin
            memory[0]=memory[0]^64'h0000000000ffffff;
            expected[0]=expected[0]^24'hffffff;
            write_reg(32'h400c2010,config_words[0]+1);
            write_reg(32'h400c2000,1);wait_face();
            if(status[7:4]!==0 || status[3]) $fatal(1,"second frame status invalid");
            if(memory[out_word][23:0]!==expected[0]) $fatal(1,"native line cache stale across frame");
            read_reg(32'h400c2008,readback);
            if(readback!==config_words[0]+1) $fatal(1,"second frame id mismatch");
        end
        $display("PASS face_customop pixels=%0d native_reads=%0d writes=%0d CDC, GP, immutable descriptor, DDR outputs checked",pixels,reads,writes);
        $finish;
    end
endmodule
