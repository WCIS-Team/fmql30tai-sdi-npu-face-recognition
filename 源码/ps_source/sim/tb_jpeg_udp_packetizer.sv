`timescale 1ns/1ps
module tb_jpeg_udp_packetizer;
    parameter integer BYTES=4001;
    reg clk=0;always #5 clk=~clk;
    reg reset=1;
    reg [31:0] session_id=32'h12345678,s_frame_id=0;
    reg [7:0] s_data=0;
    reg s_valid=0,s_sof=0,s_last=0,abort_frame=0;
    wire s_ready,hvalid,valid,last,busy,protocol_error;
    wire [15:0] udp_length;
    wire [7:0] data;
    wire [31:0] frames_done,frames_aborted,packets_sent;
    reg hready=0,ready=0;
    reg [31:0] random_state=32'hbadc0ffe;
    reg [7:0] input_data[0:BYTES-1];
    integer descriptor=0,packet_count=0,received=0,expected=0;
    reg held=0;reg [8:0] held_word;
    reg header_held=0;reg [15:0] held_length;
    string hexfile,filename;
    wcis_jpeg_udp_packetizer dut(.*,.m_hdr_valid(hvalid),.m_hdr_ready(hready),
        .m_udp_length(udp_length),.m_data(data),.m_valid(valid),.m_ready(ready),.m_last(last));
    always @(negedge clk) begin
        random_state=random_state^(random_state<<13);
        random_state=random_state^(random_state>>17);
        random_state=random_state^(random_state<<5);
        hready=random_state[0]|random_state[3];ready=random_state[1]|random_state[7];
    end
    always @(posedge clk) if(!reset) begin
        if(held && (!valid || held_word!={last,data})) $fatal(1,"Payload changed under backpressure");
        held<=valid&&!ready;held_word<={last,data};
        if(header_held && (!hvalid || held_length!=udp_length)) $fatal(1,"UDP length changed under backpressure");
        header_held<=hvalid&&!hready;held_length<=udp_length;
        if(hvalid&&hready) begin
            if(descriptor!=0) $fatal(1,"Overlapping packet headers");
            filename=$sformatf("packet_%0d.bin",packet_count);
            descriptor=$fopen(filename,"wb");if(!descriptor)$fatal(1,"Cannot write packet");
            received=0;expected=udp_length-8;
        end
        if(valid&&ready) begin
            if(!descriptor)$fatal(1,"Payload without UDP header");
            $fwrite(descriptor,"%c",data);received=received+1;
            if(last) begin
                if(received!=expected)$fatal(1,"UDP length mismatch");
                $fclose(descriptor);descriptor=0;packet_count=packet_count+1;
            end
        end
    end
    task send(input integer fid,input integer count,input bit complete);
        integer i;
        begin
            for(i=0;i<count;i=i+1) begin
                @(negedge clk);s_frame_id=fid;s_data=input_data[i%BYTES];
                s_valid=1;s_sof=(i==0);s_last=complete&&(i==count-1);
                @(posedge clk);while(!s_ready)@(posedge clk);
            end
            @(negedge clk);s_valid=0;s_sof=0;s_last=0;
        end
    endtask
    initial begin
        if(!$value$plusargs("HEX=%s",hexfile))$fatal(1,"Missing HEX");
        $readmemh(hexfile,input_data);
        repeat(5)@(negedge clk);reset=0;
        send(100,BYTES,1);wait(!busy);
        send(101,BYTES,1);wait(!busy);
        send(102,BYTES>1473 ? 1473 : 1,0);
        @(negedge clk);abort_frame=1;@(negedge clk);abort_frame=0;
        wait(!busy);
        send(103,BYTES,1);wait(!busy);
        // Abort after a whole chunk was admitted: its advertised UDP length
        // must survive, then an empty ABORT packet cancels the frame.
        send(104,1400,0);
        @(negedge clk);abort_frame=1;@(negedge clk);abort_frame=0;
        wait(!busy);
        // Abort while the payload is actually draining under backpressure.
        send(105,1400,0);
        wait(descriptor!=0 && received>60 && received<expected);
        @(negedge clk);abort_frame=1;@(negedge clk);abort_frame=0;
        wait(!busy);
        send(106,BYTES,1);wait(!busy);repeat(5)@(negedge clk);
        if(frames_done!=4||frames_aborted!=3||protocol_error)$fatal(1,"Wrong completion/abort counts");
        $display("PASS jpeg_udp_packetizer bytes=%0d packets=%0d",BYTES,packet_count);$finish;
    end
    initial begin #100000000;$fatal(1,"Simulation deadline");end
endmodule
