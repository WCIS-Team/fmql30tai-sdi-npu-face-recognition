`timescale 1ns/1ps
module tb_vtc_pipeline;
    reg clk=0;
    always #2.5 clk=~clk;
    reg rst_n=0;
    reg [31:0] hsync=1, hback=1, hactive=6, hfront=2;
    reg [31:0] vsync=1, vback=1, vactive=4, vfront=2;
    wire [23:0] rgb, ref_rgb;
    wire vs, hs, de, ref_vs, ref_hs, ref_de;
    vtc dut(.clk(clk),.rst_n(rst_n),
        .H_SYNC(hsync),.H_BACK_PORCH(hback),.H_ACTIVE(hactive),.H_FRONT_PORCH(hfront),
        .V_SYNC(vsync),.V_BACK_PORCH(vback),.V_ACTIVE(vactive),.V_FRONT_PORCH(vfront),
        .data(rgb),.vs(vs),.hs(hs),.de(de));
    vtc_vendor_reference reference(.clk(clk),.rst_n(rst_n),
        .H_SYNC(hsync),.H_BACK_PORCH(hback),.H_ACTIVE(hactive),.H_FRONT_PORCH(hfront),
        .V_SYNC(vsync),.V_BACK_PORCH(vback),.V_ACTIVE(vactive),.V_FRONT_PORCH(vfront),
        .data(ref_rgb),.vs(ref_vs),.hs(ref_hs),.de(ref_de));
    reg q_valid=0, q_vs, q_hs, q_de;
    reg [23:0] q_rgb;
    reg sample_vs, sample_hs, sample_de;
    reg [23:0] sample_rgb;
    integer pixels=0, checked=0;
    // Capture the original combinational output BEFORE its counter NBA.
    // DUT stage 1 captures that same sample; stage 2 emits it next edge.
    always @(posedge clk) begin
        sample_vs=ref_vs; sample_hs=ref_hs;
        sample_de=ref_de; sample_rgb=ref_rgb;
        if (!rst_n) begin
            q_valid=0;
            #0.1;
            if ({vs,hs,de,rgb} !== 27'd0) $fatal(1,"Reset did not suppress output");
        end else begin
            #0.1;
            if (q_valid) begin
                checked=checked+1;
                if ({vs,hs,de} !== {q_vs,q_hs,q_de})
                    $fatal(1,"Sync/valid pipeline mismatch at check %0d",checked);
                if (de) begin
                    pixels=pixels+1;
                    if (rgb !== q_rgb) $fatal(1,"Valid RGB mismatch %h != %h",rgb,q_rgb);
                end
            end
            q_vs=sample_vs; q_hs=sample_hs; q_de=sample_de; q_rgb=sample_rgb;
            q_valid=1;
        end
    end
    task run_geometry(input integer hw, vh, frames);
        integer cycles;
        begin
            @(negedge clk); rst_n=0;
            hactive=hw; vactive=vh;
            // Settle timing pipeline while reset and source is deselected.
            repeat(8) @(negedge clk);
            pixels=0;
            rst_n=1;
            cycles=(hsync+hback+hactive+hfront)*(vsync+vback+vactive+vfront)*frames+2;
            repeat(cycles) @(negedge clk);
            if (pixels != hw*vh*frames)
                $fatal(1,"Wrong pixel count %0d, expected %0d",pixels,hw*vh*frames);
            $display("VTC checked %0dx%0d, %0d frames, %0d valid pixels",hw,vh,frames,pixels);
            rst_n=0;
        end
    endtask
    initial begin
        run_geometry(6,4,300); // includes frame counter wrap
        run_geometry(1,1,4);
        run_geometry(70000,1,1); // prove no 16-bit timing truncation
        @(negedge clk);
        hsync=44; hback=148; hfront=88;
        vsync=5; vback=36; vfront=4;
        run_geometry(1920,1080,1);
        // Reset/reconfigure in the middle of a live frame.
        @(negedge clk); rst_n=1;
        repeat(10000) @(negedge clk);
        hsync=1; hback=1; hfront=2;
        vsync=1; vback=1; vfront=2;
        run_geometry(8,3,5);
        $display("PASS vtc_pipeline: vendor oracle, aligned VS/HS/DE/RGB, 1080p, 1x1, 32-bit geometry, frame wrap, mid-frame reset");
        $finish;
    end
    initial begin #30000000; $fatal(1,"VTC test timed out"); end
endmodule
