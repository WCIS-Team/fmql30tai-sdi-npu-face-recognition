`timescale 1ns/1ps
module tb_frame_rate_gate;
    reg cfg_clk=0, cam_clk=0;
    always #7 cfg_clk=~cfg_clk;
    always #5 cam_clk=~cam_clk;
    reg reset=1, cfg_valid=0;
    reg [1:0] cfg_word=1;
    wire cfg_ready;
    wire [1:0] cfg_applied;
    reg vs=0, de=0;
    reg [23:0] data=0;
    wire ov, od;
    wire [23:0] op;
    wire [31:0] seen, selected, dropped;
    wcis_frame_rate_gate dut(
        .cfg_clk(cfg_clk), .cam_clk(cam_clk), .reset(reset),
        .cfg_valid(cfg_valid), .cfg_word(cfg_word), .cfg_ready(cfg_ready),
        .cfg_applied(cfg_applied), .s_vsync(vs), .s_href(de), .s_data(data),
        .m_vsync(ov), .m_href(od), .m_data(op),
        .seen_frames(seen), .selected_frames(selected), .dropped_frames(dropped));

    integer observed_frames=0, observed_pixels=0;
    integer frame_id=0, k, before_frames, before_pixels;
    reg admitted;
    task tick(input bit v, input bit d, input [23:0] p);
        begin
            @(negedge cam_clk); vs=v; de=d; data=p;
            @(posedge cam_clk); #1;
        end
    endtask
    task submit(input [1:0] word);
        begin
            wait(cfg_ready); @(negedge cfg_clk);
            cfg_word=word; cfg_valid=1;
            @(negedge cfg_clk); cfg_valid=0;
            // Configuration must wait for a frame; no frame here.
            repeat(6) @(posedge cam_clk);
            if(cfg_ready) $fatal(1,"Commit acknowledged before frame boundary");
        end
    endtask
    task frame;
        integer i;
        begin
            frame_id=frame_id+1;
            tick(1,0,0);
            admitted=ov;
            if(admitted) observed_frames=observed_frames+1;
            // Multiple VS cycles must not count as multiple frames.
            tick(1,0,0);
            if(ov!==admitted) $fatal(1,"VS changed inside sync pulse");
            tick(0,0,0);
            for(i=0;i<12;i=i+1) begin
                tick(0,1,{frame_id[15:0],i[7:0]});
                if(od!==admitted) $fatal(1,"Partial frame passed");
                if(od && op!=={frame_id[15:0],i[7:0]}) $fatal(1,"Pixel corrupted");
                if(od) observed_pixels=observed_pixels+1;
                if(i%4==3) tick(0,0,0);
            end
            tick(0,0,0);
        end
    endtask
    initial begin
        #31 reset=0; repeat(8) @(posedge cam_clk);
        before_frames=observed_frames;
        repeat(30) frame();
        if(observed_frames-before_frames!=30) $fatal(1,"Default bypass changed demo");
        submit(3); before_frames=observed_frames; before_pixels=observed_pixels;
        repeat(300) frame();
        if(observed_frames-before_frames!=200 || observed_pixels-before_pixels!=2400)
            $fatal(1,"30 to 20 rate incorrect");
        repeat(6) @(posedge cfg_clk);
        if(cfg_applied!=3 || !cfg_ready) $fatal(1,"Active commit not acknowledged");
        submit(2); before_frames=observed_frames;
        repeat(300) frame();
        if(observed_frames-before_frames!=10) $fatal(1,"Standby rate incorrect");
        submit(1); before_frames=observed_frames;
        repeat(30) frame();
        if(observed_frames-before_frames!=30) $fatal(1,"Return to bypass failed");
        if(seen!=660 || selected!=270 || dropped!=390)
            $fatal(1,"Accounting inconsistent: %d %d %d",seen,selected,dropped);
        // Mid-frame commit must not truncate the current frame.
        fork
            begin frame(); end
            begin repeat(5) @(posedge cam_clk); submit(2); end
        join
        if(!admitted) $fatal(1,"Mode change truncated bypass frame");
        frame(); repeat(6) @(posedge cfg_clk);
        if(cfg_applied!=2) $fatal(1,"Next frame did not apply standby");
        // A busy request must not replace the payload in flight.
        submit(3);
        @(negedge cfg_clk); cfg_word=1; cfg_valid=1;
        @(negedge cfg_clk); cfg_valid=0;
        frame(); repeat(6) @(posedge cfg_clk);
        if(cfg_applied!=3) $fatal(1,"Busy write replaced held config");
        // Common reset while a request is pending must recover to bypass.
        submit(2); #3 reset=1; #29 reset=0;
        repeat(8) @(posedge cam_clk);
        frame(); repeat(6) @(posedge cfg_clk);
        if(!admitted || cfg_applied!=1 || !cfg_ready) $fatal(1,"Reset recovery failed");
        $display("PASS frame_rate_gate: bypass, 300-frame active/standby, whole frames, CDC commit, busy, reset");
        $finish;
    end
    initial begin #2000000; $fatal(1,"Test timed out"); end
endmodule
