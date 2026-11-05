`timescale 1ps/1ps
module tb_frame_error_cdc;
    parameter integer SRC_HALF=3367,PHASE=0;
    reg src_clk=0,mem_clk=0,reset=0;
    initial forever #SRC_HALF src_clk=~src_clk;
    initial begin #PHASE;forever #2500 mem_clk=~mem_clk;end
    reg source_request=0,overflow=0;
    wire request_mem,ack_mem,ack_src;
    level_cross request_cross(.clk1(src_clk),.rst1(reset),.a1(source_request),
        .clk2(mem_clk),.rst2(reset),.a2(request_mem));
    level_cross ack_cross(.clk1(mem_clk),.rst1(reset),.a1(ack_mem),
        .clk2(src_clk),.rst2(reset),.a2(ack_src));
    // Same producer request/error equations as frame_read_write_largebuf.v.
    reg req_d0=0,req_d1=0,source_error=0;
    always @(posedge src_clk)begin
        if(reset)begin req_d0<=0;req_d1<=0;end
        else begin req_d0<=request_mem;req_d1<=req_d0;end
    end
    always @(posedge src_clk or posedge reset)
        if(reset)source_error<=0;
        else if(!req_d1 && req_d0)source_error<=0;
        else if(overflow)source_error<=1;
    wire error_mem;
    wcis_status_sync error_cross(.clk(mem_clk),.reset(reset),.s_status(source_error),.m_status(error_mem));
    reg [15:0] used=0;
    wire burst_req,fifo_clear,finished;
    wire [9:0] burst_len;
    wire [26:0] burst_addr;
    reg burst_finish=0,bus_active=0;
    integer bus_count=0,bursts=0,base_bursts=0,completions=0;
    reg clean_active=0;
    frame_fifo_write #(.ADDR_BITS(27),.BUSRT_BITS(10),.BURST_SIZE(4)) writer(
        .rst(reset),.mem_clk(mem_clk),.wr_burst_req(burst_req),.wr_burst_len(burst_len),
        .wr_burst_addr(burst_addr),.wr_burst_data_req(1'b0),.wr_burst_finish(burst_finish),
        .write_req(request_mem),.write_req_ack(ack_mem),.write_finish(finished),
        .write_addr_0(27'h100),.write_addr_1(27'h100),.write_addr_2(27'h100),.write_addr_3(27'h100),
        .write_addr_index(2'd0),.write_len(27'd8),.fifo_aclr(fifo_clear),
        .wr_wfifo_err(error_mem),.rdusedw(used));
    always @(posedge mem_clk)begin
        if(reset)begin bus_active<=0;bus_count<=0;burst_finish<=0;end
        else begin
            burst_finish<=0;
            if(!bus_active && burst_req && !burst_finish)begin
                bus_active<=1;bus_count<=3;bursts=bursts+1;
                if(burst_len!=4)$fatal(1,"Burst length changed");
            end else if(bus_active)begin
                if(bus_count==0)begin burst_finish<=1;bus_active<=0;end
                else bus_count<=bus_count-1;
            end
            if(finished)begin
                completions=completions+1;
                if(clean_active && (source_error || bursts-base_bursts!=2))
                    $fatal(1,"Stale error aborted the next clean frame");
            end
        end
    end
    task request_frame;
        begin
            @(negedge src_clk);source_request=1;
            wait(ack_src);@(negedge src_clk);source_request=0;
            wait(!ack_src);
        end
    endtask
    task clean_frame;
        integer previous;
        begin
            previous=completions;base_bursts=bursts;used=0;clean_active=1;
            request_frame();
            @(negedge mem_clk);used=8;
            wait(completions>previous);
            @(negedge mem_clk);used=0;clean_active=0;
            repeat(5)@(negedge mem_clk);
        end
    endtask
    task failed_frame;
        integer previous,old_bursts;
        begin
            previous=completions;old_bursts=bursts;used=0;request_frame();
            repeat(6)@(negedge mem_clk);
            @(negedge src_clk);overflow=1;
            @(negedge src_clk);overflow=0;
            wait(completions>previous);
            if(!source_error || !error_mem || bursts!=old_bursts)$fatal(1,"Overflow failed to stop empty-frame writer");
            repeat(6)@(negedge mem_clk);
        end
    endtask
    initial begin
        #173;reset=1;repeat(8)@(negedge src_clk);reset=0;
        repeat(12)@(negedge mem_clk);
        clean_frame();failed_frame();clean_frame();failed_frame();clean_frame();
        if(completions!=5)$fatal(1,"Unexpected frame completion count");
        $display("PASS frame error CDC src_half=%0d phase=%0d",SRC_HALF,PHASE);$finish;
    end
    initial begin #100000000;$fatal(1,"Frame error CDC timeout");end
endmodule
