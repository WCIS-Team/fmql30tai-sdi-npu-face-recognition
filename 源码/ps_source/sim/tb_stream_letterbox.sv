`timescale 1ns/1ps
module letterbox_case #(
    parameter CW=3, CH=2, OW=5, OH=4, LEFT=0, TOP=0, FRAMES=3, RESET_MID=0
)(output reg done=0);
    reg clk=0; always #5 clk=~clk;
    reg rst=1;
    wire sv, sr, mv, sof, eol, eof;
    wire [23:0] sd, md;
    reg mr=0, offer=0;
    integer si=0, oi=0, cycle=0;
    reg [31:0] lfsr=32'h94ab813f;
    reg stalled=0;
    reg [26:0] held;
    assign sv=offer && (si<CW*CH*FRAMES);
    assign sd=24'h100000+si;
    wcis_stream_letterbox #(.CONTENT_W(CW),.CONTENT_H(CH),
        .CANVAS_W(OW),.CANVAS_H(OH),.PAD_LEFT(LEFT),.PAD_TOP(TOP)) dut(
        .clk(clk),.reset(rst),.s_valid(sv),.s_ready(sr),.s_data(sd),
        .m_valid(mv),.m_ready(mr),.m_data(md),.m_sof(sof),.m_eol(eol),.m_eof(eof));
    integer x,y,fi;
    reg [23:0] want;
    always @(negedge clk) begin
        lfsr={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
        mr=lfsr[0] || lfsr[3];
        // Input valid can bubble, but cannot withdraw a stalled offered pixel.
        if(!sv || sr) offer=lfsr[2] || lfsr[5];
    end
    always @(posedge clk) begin
        if(rst) begin
            si=0; oi=0; cycle=0; stalled=0;
        end else if(!done) begin
            cycle=cycle+1;
            if(stalled && (!mv || {md,sof,eol,eof}!==held))
                $fatal(1,"Output changed under backpressure (%d,%d)",OW,OH);
            stalled=mv && !mr;
            held={md,sof,eol,eof};
            if(mv && mr) begin
                x=oi%OW; y=(oi/OW)%OH; fi=oi/(OW*OH);
                if(x>=LEFT && x<LEFT+CW && y>=TOP && y<TOP+CH)
                    want=24'h100000+fi*CW*CH+(y-TOP)*CW+(x-LEFT);
                else want=24'h727272;
                if(md!==want || sof!==(x==0 && y==0) ||
                    eol!==(x==OW-1) || eof!==(x==OW-1 && y==OH-1))
                    $fatal(1,"Letterbox pixel/marker mismatch at %d: got %h want %h",oi,md,want);
                oi=oi+1;
            end
            if(sv && sr) si=si+1;
            if(oi==OW*OH*FRAMES) begin
                if(si!=CW*CH*FRAMES) $fatal(1,"Wrong input consumption");
                done=1;
            end
            if(cycle>OW*OH*FRAMES*12+100) $fatal(1,"Letterbox stalled forever");
        end
    end
    initial begin
        repeat(4) @(negedge clk); rst=0;
        if(RESET_MID) begin
            wait(oi>=OW);
            @(negedge clk); rst=1;
            repeat(3) @(negedge clk); rst=0;
        end
    end
endmodule
module tb_stream_letterbox;
    wire a,b,c,d,e;
    letterbox_case u_small(.done(a));
    letterbox_case #(.LEFT(1),.TOP(1)) centered(.done(b));
    letterbox_case #(.CW(1),.CH(1),.OW(1),.OH(1)) single(.done(c));
    letterbox_case #(.CW(640),.CH(360),.OW(640),.OH(640),.FRAMES(2)) full(.done(d));
    letterbox_case #(.LEFT(1),.TOP(1),.RESET_MID(1)) reset_during_frame(.done(e));
    initial begin
        wait(a && b && c && d && e);
        $display("PASS letterbox: small/centered/one-pixel/full-640 canvas, random stalls/bubbles, all pixels/markers, mid-frame reset");
        $finish;
    end
    initial begin #20000000; $fatal(1,"Suite timed out"); end
endmodule
