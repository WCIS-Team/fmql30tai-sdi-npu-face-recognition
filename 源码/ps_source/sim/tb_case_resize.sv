`timescale 1ns/1ps
// Independent coordinate-coded pixels verify the reused vendor sampler.
module resize_case #(
    parameter X0=0,Y0=12,X1=1919,Y1=1067,STRIDE=3,OW=640,OH=352
)(output reg done=0);
    reg clk=0; always #5 clk=~clk;
    reg reset=1, vs=0, de=0;
    reg [23:0] data=0;
    wire ov,od;
    wire [23:0] out;
    integer x,y,n=0;
    integer want_x,want_y;
    cmos_resize_24bit dut(
        .reset_cmos1_pclk(reset),.cmos1_pclk(clk),.dvp_href(de),.dvp_vsync(vs),.dvp_data(data),
        .x0_pos(16'(X0)),.y0_pos(16'(Y0)),.x1_pos(16'(X1)),.y1_pos(16'(Y1)),
        .x_leng(16'd1920),.y_leng(16'd1080),.hstride(4'(STRIDE)),.vstride(4'(STRIDE)),
        .resize_href(od),.resize_vsync(ov),.resize_data(out));
    always @(posedge clk) begin
        #1;
        if(!reset && od) begin
            want_x=X0+STRIDE-1+(n%OW)*STRIDE;
            want_y=Y0+STRIDE-1+(n/OW)*STRIDE;
            if(out!=={12'(want_y),12'(want_x)})
                $fatal(1,"Vendor resize %dx%d pixel %d got y=%d x=%d want y=%d x=%d",OW,OH,n,out[23:12],out[11:0],want_y,want_x);
            n=n+1;
            if(n>OW*OH) $fatal(1,"Too many output pixels");
        end
    end
    initial begin
        repeat(4) @(negedge clk); reset=0; vs=1;
        repeat(4) @(negedge clk); vs=0;
        repeat(4) @(negedge clk);
        for(y=0;y<1080;y=y+1) begin
            for(x=0;x<1920;x=x+1) begin
                @(negedge clk); de=1; data={12'(y),12'(x)};
            end
            @(negedge clk); de=0;
            repeat(12) @(negedge clk);
        end
        repeat(10) @(negedge clk);
        if(n!=OW*OH) $fatal(1,"Wrong frame size: got %d want %d",n,OW*OH);
        done=1;
    end
endmodule
module tb_case_resize;
    wire a,b;
    resize_case legacy(.done(a));
    resize_case #(.Y0(28),.Y1(1051),.STRIDE(2),.OW(960),.OH(512)) rectangular(.done(b));
    initial begin
        wait(a&&b);
        $display("PASS case_resize: every valid pixel of 1080p -> 640x352 and center-crop 960x512 preserved after payload timing fix");
        $finish;
    end
    initial begin #25000000; $fatal(1,"Resize suite timed out"); end
endmodule
