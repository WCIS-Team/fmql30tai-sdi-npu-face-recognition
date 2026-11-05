`timescale 1ns/1ps
module tb_mdio_clause22;
    reg clk=0;always #5 clk=~clk;
    reg reset=1,command_valid=0,command_read=0;
    reg [4:0] phy_address=3,register_address=9;
    reg [15:0] write_data=16'hace1;
    wire command_ready,done,error,mdc,mdio_out,mdio_tristate;
    wire [15:0] read_data;
    tri1 mdio;
    assign mdio=mdio_tristate?1'bz:mdio_out;
    reg phy_read=0,missing=0;integer sample=0;
    reg phy_output=1,phy_drive=0;
    // Model data changing AFTER the MDC rising edge. The datasheet specifies
    // 20 ns maximum; also test a deliberately larger 62 ns settling margin.
    integer phy_delay=20;
    assign mdio=phy_drive ? phy_output : 1'bz;
    always @(posedge mdc)begin
        if(phy_read&&!missing&&sample>=47&&sample<64)begin
            #(phy_delay);phy_drive=1;
            phy_output=(sample==47 ? 1'b0 : ((16'ha55a>>(63-sample))&1));
        end
    end
    wcis_mdio_clause22 #(.HALF_PERIOD(25)) dut(.*,.mdio_in(mdio));
    reg [63:0] observed=0;
    realtime drive_changed=0;
    always @(mdio_out or mdio_tristate)begin
        if(!reset)begin
            drive_changed=$realtime;
            #0.001;
            if(mdc)$fatal(1,"MDIO driven data/enable changed during MDC high");
        end
    end
    always @(posedge mdc)begin
        if(!reset&&$realtime-drive_changed<249.0)
            $fatal(1,"MDIO output did not have the full half-period setup window");
    end
    always @(posedge mdc)observed={observed[62:0],mdio};
    always @(negedge mdc)if(!reset)sample=sample+1;
    task transaction(input bit reading,input bit absent);
        begin
            wait(command_ready);@(negedge clk);sample=0;observed=0;
            phy_read=reading;phy_drive=0;phy_output=1;missing=absent;command_read=reading;command_valid=1;
            @(negedge clk);command_valid=0;wait(done);@(negedge clk);
            if(observed[63:32]!=32'hffffffff||observed[31:30]!=1||
               observed[29:28]!=(reading?2:1)||observed[27:23]!=3||observed[22:18]!=9)
                $fatal(1,"Malformed MDIO transaction %h",observed);
            if(!reading&&(observed[17:16]!=2||observed[15:0]!=16'hace1))$fatal(1,"MDIO write bits");
            if(reading&&!absent&&(error||read_data!=16'ha55a))$fatal(1,"MDIO read %h error=%b",read_data,error);
            if(absent&&!error)$fatal(1,"Missing PHY was accepted");
        end
    endtask
    initial begin
        repeat(5)@(negedge clk);reset=0;
        transaction(0,0);transaction(1,0);phy_delay=62;transaction(1,0);transaction(1,1);
        $display("PASS mdio_clause22 write, delayed PHY read (20/62 ns), missing-PHY turnaround, half-period output windows");$finish;
    end
    initial begin #200000;$fatal(1,"MDIO deadline");end
endmodule
