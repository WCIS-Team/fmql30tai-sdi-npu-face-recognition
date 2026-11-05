`timescale 1ns/1ps
// Actual rewritten VTC -> frame gate (default bypass) -> vendor crop/sampler.
// Check output pixels against the documented crop coordinates, not DUT state.
module tb_vtc_resize_chain;
    reg clk=0; always #2.5 clk=~clk;
    reg cfg_clk=0; always #7 cfg_clk=~cfg_clk;
    reg reset=1;
    wire vtc_vs,vtc_hs,vtc_de,gate_vs,gate_de,out_vs,out_de;
    wire [23:0] vtc_rgb,gate_rgb,out_rgb;
    wire ready;
    wire [1:0] applied;
    wire [31:0] seen,selected,dropped;
    vtc source(.clk(clk),.rst_n(!reset),
        .H_SYNC(32'd44),.H_BACK_PORCH(32'd148),.H_ACTIVE(32'd1920),.H_FRONT_PORCH(32'd88),
        .V_SYNC(32'd5),.V_BACK_PORCH(32'd36),.V_ACTIVE(32'd1080),.V_FRONT_PORCH(32'd4),
        .vs(vtc_vs),.hs(vtc_hs),.de(vtc_de),.data(vtc_rgb));
    wcis_frame_rate_gate gate(.cfg_clk(cfg_clk),.cam_clk(clk),.reset(reset),
        .cfg_valid(1'b0),.cfg_word(2'b01),.cfg_ready(ready),.cfg_applied(applied),
        .s_vsync(vtc_vs),.s_href(vtc_de),.s_data(vtc_rgb),
        .m_vsync(gate_vs),.m_href(gate_de),.m_data(gate_rgb),
        .seen_frames(seen),.selected_frames(selected),.dropped_frames(dropped));
    cmos_resize_24bit sampler(.reset_cmos1_pclk(reset),.cmos1_pclk(clk),
        .dvp_vsync(gate_vs),.dvp_href(gate_de),.dvp_data(gate_rgb),
        .x0_pos(16'd0),.y0_pos(16'd12),.x1_pos(16'd1919),.y1_pos(16'd1067),
        .x_leng(16'd1920),.y_leng(16'd1080),.hstride(4'd3),.vstride(4'd3),
        .resize_vsync(out_vs),.resize_href(out_de),.resize_data(out_rgb));
    integer n=0;
    reg [7:0] want_gray;
    always @(posedge clk) begin
        #0.1;
        if (!reset && out_de) begin
            // Active x=2+3*i, absolute hcnt=44+148+x, first frame_cnt=1.
            want_gray=(44+148+2+3*(n%640)+1)%256;
            if (out_rgb !== {3{want_gray}})
                $fatal(1,"VTC/gate/resize pixel %0d: %h != %h",n,out_rgb,{3{want_gray}});
            n=n+1;
            if (n>640*352) $fatal(1,"Chain emitted too many pixels");
        end
    end
    initial begin
        repeat(12) @(negedge clk); reset=0;
        repeat(2200*1125+20) @(negedge clk);
        if (n!=640*352) $fatal(1,"Chain frame size %0d != 225280",n);
        if (seen!=2 || selected!=2 || dropped!=0)
            $fatal(1,"Frame gate did not detect two VTC frame boundaries");
        $display("PASS vtc_resize_chain: actual VTC/gate/vendor resize, 225280 grayscale pixels, 640x352, frame boundaries");
        $finish;
    end
    initial begin #15000000; $fatal(1,"VTC chain timed out"); end
endmodule
