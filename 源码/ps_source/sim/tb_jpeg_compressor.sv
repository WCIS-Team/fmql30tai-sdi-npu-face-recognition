`timescale 1ns/1ps
module tb_jpeg_compressor;
    parameter W=64, H=16, Q=75, FAW=12, PF=0;
    reg clk=0;
    always #5 clk=~clk;
    reg reset=1, cmd_valid=0, s_valid=0, abort_frame=0, m_ready=0;
    reg [31:0] cmd_frame_id=0;
    reg [23:0] s_rgb=0;
    wire cmd_ready, s_ready, m_valid, m_sof, m_last, frame_abort, busy, overflow_sticky;
    wire [7:0] m_data;
    wire [31:0] frame_id, frames_done, frames_aborted, fifo_overflows;
    wire [31:0] last_frame_bytes, last_frame_cycles;
    wcis_jpeg_compressor #(.IMG_WIDTH(W),.IMG_HEIGHT(H),.QUALITY(Q),.FIFO_AW(FAW),.PIPELINED_FIFO(PF)) dut (.*);
    reg [23:0] pixels[0:W*H*2-1];
    reg [1023:0] hex_path;
    integer mode=0, cycles=0, completed=0, aborted=0, file_handle=0, bytes=0;
    integer i, frame_start_cycle, seed=32'h462789ab;
    reg stalled=0;
    reg [9:0] held;
    reg [31:0] held_id;
    reg expect_overflow=0;
    integer partial_bytes=0;

    always @(posedge clk) begin
        cycles <= cycles+1;
        if (!reset) begin
            if (stalled && !abort_frame && !frame_abort && !dut.overflow_now) begin
                if (!m_valid || {m_sof,m_last,m_data} !== held || frame_id !== held_id)
                    $fatal(1,"output changed while stalled");
            end
            stalled <= m_valid && !m_ready;
            held <= {m_sof,m_last,m_data}; held_id <= frame_id;
            if (frame_abort) begin
                if (mode==0 || mode==3 || aborted!=0) $fatal(1,"unexpected frame abort");
                aborted=aborted+1;
                partial_bytes=bytes;
                if (file_handle) $fclose(file_handle);
                file_handle=0; bytes=0; stalled<=0;
                $display("ABORT id=%0d partial_bytes=%0d",frame_id,partial_bytes);
            end
            if (m_valid && m_ready) begin
                if (m_sof) begin
                    if (file_handle) $fatal(1,"second SOF before EOF/abort");
                    file_handle=$fopen($sformatf("frame_%0d.jpg",frame_id),"wb");
                    if (!file_handle) $fatal(1,"output file open failed");
                    bytes=0;
                end
                if (!file_handle) $fatal(1,"byte before SOF");
                if ((bytes==0) != m_sof) $fatal(1,"bad SOF position");
                $fwrite(file_handle,"%c",m_data); bytes=bytes+1;
                if (m_last) begin
                    $fclose(file_handle); file_handle=0;
                    completed=completed+1;
                    $display("FRAME id=%0d bytes=%0d cycles=%0d",frame_id,bytes,cycles-frame_start_cycle);
                    bytes=0;
                end
            end
        end else begin
            stalled<=0;
            if (file_handle) $fclose(file_handle);
            file_handle=0; bytes=0;
        end
        if (cycles > W*H*20+100000) begin
            $display("STATE id=%0d inflight=%b feeding=%b initialized=%b used=%0d pixels=%0d core_ready=%b core_state=%0d",frame_id,dut.inflight,dut.feeding,dut.initialized,dut.used,dut.pixel_index,dut.core_ready,dut.encoder.fstate);
            $fatal(1,"watchdog");
        end
    end

    // Downstream periodic stalls, including long enough to exercise FIFO wrap.
    always @(negedge clk) begin
        if (expect_overflow) m_ready=(bytes < 50 && !overflow_sticky);
        else if (mode==1) m_ready=1;
        else m_ready=(cycles%29 != 0 && cycles%29 != 1 && cycles%29 != 2);
    end

    task command(input integer id);
        begin
            @(negedge clk);
            cmd_frame_id=id; cmd_valid=1;
            do @(posedge clk); while (!cmd_ready);
            frame_start_cycle=cycles;
            $display("COMMAND id=%0d cycle=%0d",id,cycles);
            @(negedge clk); cmd_valid=0;
        end
    endtask

    task feed(input integer offset, input integer count);
        integer n, abort_mark;
        begin : feeding_block
            abort_mark=frames_aborted;
            for(n=0;n<count;n=n+1) begin
                @(negedge clk);
                // Gaps in the producer are legal. Data holds during backpressure.
                if (n%17==3) begin s_valid=0; @(negedge clk); end
                s_rgb=pixels[offset+n]; s_valid=1;
                begin : wait_accept
                    forever begin
                        @(posedge clk);
                        if (frame_abort || frames_aborted!=abort_mark) begin
                            @(negedge clk); s_valid=0;
                            disable feeding_block;
                        end
                        if (s_ready) disable wait_accept;
                    end
                end
            end
            @(negedge clk); s_valid=0;
        end
    endtask

    initial begin
        if (!$value$plusargs("HEX=%s",hex_path)) $fatal(1,"HEX missing");
        if (!$value$plusargs("MODE=%d",mode)) mode=0;
        $readmemh(hex_path,pixels);
        repeat(8) @(negedge clk);
        reset=0;
        if (mode==0) begin
            command(101); feed(0,W*H);
            wait(frames_done==1);
            if(last_frame_bytes==0 || last_frame_cycles==0) $fatal(1,"no frame stats");
            command(102); feed(W*H,W*H);
            wait(frames_done==2);
            if (frames_aborted || fifo_overflows || overflow_sticky) $fatal(1,"unexpected abort");
        end else if (mode==1) begin
            expect_overflow=1;
            command(201); feed(0,W*H);
            wait(frames_aborted==1);
            if (!overflow_sticky || fifo_overflows!=1) $fatal(1,"overflow not counted");
            expect_overflow=0;
            command(202); feed(W*H,W*H);
            wait(frames_done==1);
            if (frames_aborted!=1 || fifo_overflows!=1) $fatal(1,"bad recovery stats");
        end else if (mode==2) begin
            command(301); feed(0, W*H/3);
            @(negedge clk); abort_frame=1;
            @(negedge clk); abort_frame=0;
            wait(frames_aborted==1);
            command(302); feed(W*H,W*H);
            wait(frames_done==1);
            if (fifo_overflows || overflow_sticky) $fatal(1,"manual abort marked overflow");
        end else if (mode==3) begin
            command(401); feed(0, W*H/3);
            @(negedge clk); reset=1;
            repeat(8) @(negedge clk);
            reset=0;
            command(402); feed(W*H,W*H);
            wait(frames_done==1);
            if (frames_aborted || fifo_overflows) $fatal(1,"reset counters incorrect");
        end
        repeat(10) @(negedge clk);
        if (busy || !cmd_ready || s_ready || m_valid) $fatal(1,"not idle after drain");
        if (mode==0 && completed!=2) $fatal(1,"missing frames");
        if ((mode==1 || mode==2) && (completed!=1 || aborted!=1)) $fatal(1,"recovery failed");
        $display("PASS jpeg_compressor mode=%0d completed=%0d aborted=%0d",mode,completed,aborted);
        $finish;
    end
endmodule
