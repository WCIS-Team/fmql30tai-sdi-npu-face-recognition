`timescale 1ns/1ps
module tb_sdi_jpeg_stream;
    parameter integer W=64,H=16;
    reg cam_clk=0;always #6.734 cam_clk=~cam_clk;
    reg clk=0;always #2.5 clk=~clk;
    reg reset=0,enable=1,cam_locked=1,cam_vsync=0,cam_de=0;
    reg [23:0] cam_rgb=0;
    wire [7:0] m_data;wire m_valid,m_sof,m_last,abort_frame,idle;
    wire [31:0] m_frame_id,frames_encoded,frames_rejected;
    reg m_ready=0;wire downstream_idle=1;
    integer descriptor=0,completed=0,aborted=0;
    string filename;
    reg [31:0] random_state=32'h31415926;
    wcis_sdi_jpeg_stream #(.IMAGE_WIDTH(W),.IMAGE_HEIGHT(H),.PIXEL_FIFO_DEPTH(256)) dut(.*);
    always @(negedge clk)begin
        random_state=random_state^(random_state<<13);random_state=random_state^(random_state>>17);random_state=random_state^(random_state<<5);
        m_ready=random_state[0]|random_state[1];
    end
    always @(posedge clk)if(!reset)begin
        if(abort_frame)begin
            aborted=aborted+1;
            if(descriptor)begin $fclose(descriptor);descriptor=0;end
        end
        if(m_valid&&m_ready)begin
            if(m_sof)begin
                if(descriptor)$fatal(1,"Overlapping JPEGs");
                filename=$sformatf("source_frame_%0d.jpg",m_frame_id);descriptor=$fopen(filename,"wb");
            end
            if(!descriptor)$fatal(1,"No JPEG SOF");
            $fwrite(descriptor,"%c",m_data);
            if(m_last)begin
                if(cam_vsync)$fatal(1,"JPEG EOF escaped before source validation");
                $fclose(descriptor);descriptor=0;completed=completed+1;
            end
        end
    end
    task frame(input integer columns,input integer rows);
        integer x,y;
        begin
            wait(idle);repeat(12)@(negedge cam_clk);
            cam_vsync=1;repeat(5)@(negedge cam_clk);
            for(y=0;y<rows;y=y+1)begin
                for(x=0;x<columns;x=x+1)begin
                    cam_de=1;cam_rgb={8'(x*255/(W-1)),8'(y*255/(H-1)),8'((x*3+y*7)%256)};
                    @(negedge cam_clk);
                end
                cam_de=0;repeat(12)@(negedge cam_clk);
            end
            cam_vsync=0;cam_de=0;repeat(12)@(negedge cam_clk);
        end
    endtask
    initial begin
        #20;reset=1;#100;reset=0;
        frame(W,H);wait(completed==1);wait(idle);
        frame(W-1,H);wait(aborted==1);wait(idle);
        if(completed!=1||frames_rejected!=1)$fatal(1,"Malformed source committed");
        frame(W,H);wait(completed==2);wait(idle);
        if(frames_encoded!=2||frames_rejected!=1)$fatal(1,"Source did not recover");
        $display("PASS sdi_jpeg_stream full-view malformed-frame rejection and recovery");$finish;
    end
    initial begin #3000000;$fatal(1,"Stream deadline state=%0d encoded=%0d rejected=%0d",dut.state,frames_encoded,frames_rejected);end
endmodule
