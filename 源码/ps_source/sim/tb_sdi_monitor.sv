`timescale 1ns/1ps
module tb_sdi_monitor;
    reg cfg=0, rx=0, run_rx=1, rstn=0;
    always #7 cfg=~cfg;
    always #5 if(run_rx) rx=~rx;
    reg [11:0] flags=0;
    reg vs=0, de=0, refok=1, released=1;
    wire [415:0] words;
    wcis_sdi_monitor #(.CFG_HZ(71428571),.SAMPLE_CYCLES(8),.STALE_CYCLES(30)) dut(
        .cfg_clk(cfg),.reset_n(rstn),.rx_clk(rx),.rx_flags(flags),
        .rx_vs(vs),.rx_de(de),.ref_stable(refok),.gt_reset_released(released),.words(words));
    function [31:0] word(input integer i); word=words[i*32+:32]; endfunction
    task wait_commit;
        reg [31:0] previous;
        begin previous=word(3); while(word(3)==previous) @(negedge cfg); end
    endtask
    task boundary;
        begin @(negedge rx);vs=1; repeat(2) @(negedge rx); vs=0; end
    endtask
    task line(input integer n);
        begin @(negedge rx);de=1; repeat(n) @(negedge rx);de=0; repeat(2) @(negedge rx); end
    endtask
    reg [31:0] previous_seq, previous_cycles;
    reg [191:0] previous_data;
    initial begin
        #32; rstn=1; flags=12'h5a1;
        wait_commit();
        if(word(0)!=32'h53444932 || word(1)!=1 || word(12)!=71428571 ||
           (word(2)&3)!=3 || word(6)!=32'h5a1) $fatal(1,"initial snapshot");
        boundary(); line(4); line(4); line(4); boundary();
        wait_commit(); wait_commit();
        if(word(11)!={16'd3,16'd4} || word(8)!=2 || word(9)!=3 || word(10)!=12)
            $fatal(1,"geometry/counters %h %d %d %d",word(11),word(8),word(9),word(10));
        // Stop exactly with the source clock low. Outstanding requests remain
        // pending but the running CFG domain and register bank do not stall.
        @(negedge rx); run_rx=0;
        repeat(8) @(negedge cfg); // drain any ACK already in flight
        previous_seq=word(3); previous_data=words[383:192];
        repeat(40) @(negedge cfg);
        if(word(3)!=previous_seq || words[383:192]!=previous_data ||
           (word(2)&6)!=4) $fatal(1,"stopped clock must keep snapshot and mark stale/pending");
        // A late ACK must complete the same request after source resumes.
        run_rx=1; wait_commit();
        if((word(2)&3)!=3) $fatal(1,"resumed clock not fresh");
        previous_cycles=word(7); wait_commit();
        if(word(7)<=previous_cycles) $fatal(1,"RX cycle counter not progressing");
        // Lock loss must discard dimensions without retaining a false format.
        @(negedge rx); flags=0; wait_commit(); wait_commit();
        if(word(6)!=0 || word(11)!=0) $fatal(1,"lock loss retains stale geometry");
        // CFG reset while RX clock is stopped must clear both toggle domains.
        @(negedge rx); run_rx=0; repeat(12) @(negedge cfg);
        rstn=0; #21;
        if(word(3)!=0 || (word(2)&3)!=0) $fatal(1,"shared async reset failed");
        rstn=1; repeat(40) @(negedge cfg);
        if(word(3)!=0 || (word(2)&3)!=0) $fatal(1,"stopped RX produces false reset ACK");
        run_rx=1; flags=1; wait_commit();
        if((word(2)&3)!=3) $fatal(1,"reset/resume failed");
        $display("PASS sdi_monitor: raw counters/geometry, asynchronous snapshots, stopped clock, late ACK, lock loss, reset while stopped");
        $finish;
    end
    initial begin #50000; $fatal(1,"monitor timeout"); end
endmodule
