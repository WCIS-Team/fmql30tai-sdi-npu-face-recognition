`timescale 1ps/1ps
module tb_status_sync;
    parameter integer SRC_HALF=4000,DST_HALF=3333,PHASE=0;
    reg src_clk=0,dst_clk=0,reset=0,event_pulse=0,source_sticky=0;
    initial forever #SRC_HALF src_clk=~src_clk;
    initial begin #PHASE;forever #DST_HALF dst_clk=~dst_clk;end
    always @(posedge src_clk or posedge reset)
        if(reset)source_sticky<=0;
        else if(event_pulse)source_sticky<=1;
    wire status;
    wcis_status_sync dut(.clk(dst_clk),.reset(reset),.s_status(source_sticky),.m_status(status));
    task settle(input bit expected);
        integer cycles;
        begin
            cycles=0;
            while(status!==expected && cycles<12)begin @(posedge dst_clk);#1;cycles=cycles+1;end
            if(status!==expected)$fatal(1,"Status did not reach %0d",expected);
        end
    endtask
    task clear_session;
        begin
            #137;reset=1;
            repeat(6)@(negedge dst_clk);
            reset=0;
            repeat(7)@(posedge dst_clk);
            #1;if(status!==0)$fatal(1,"Previous session error survived reset");
        end
    endtask
    initial begin
        clear_session();
        for(integer n=0;n<16;n=n+1)begin
            // One source-cycle event must survive arbitrary destination phase.
            @(negedge src_clk);event_pulse=1;
            @(negedge src_clk);event_pulse=0;
            settle(1);
            repeat(9)begin @(posedge dst_clk);#1;if(status!==1)$fatal(1,"Sticky error was lost");end
            clear_session();
        end
        // A producer level that clears must also clear at the destination.
        @(negedge src_clk);event_pulse=1;
        @(negedge src_clk);event_pulse=0;
        settle(1);
        reset=1;repeat(8)@(negedge dst_clk);reset=0;settle(0);
        $display("PASS status CDC src_half=%0d dst_half=%0d phase=%0d",SRC_HALF,DST_HALF,PHASE);
        $finish;
    end
    initial begin #100000000;$fatal(1,"CDC timeout");end
endmodule
