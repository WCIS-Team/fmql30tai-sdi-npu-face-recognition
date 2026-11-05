source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl
set task_dir D:/yzd/tmp/npu-min-period-20261022
open_checkpoint D:/yzd/tmp/pl-command-validation-20261022/preserved-routed.dcp
set out [open $task_dir/core-clock-topology.txt w]
set prefix U0_ps_ai_peripheral/ZGolo/u_AI_Mate_top/clkrst_wrapper_u0
foreach cell [get_cells -hier -filter "NAME =~ $prefix/AI_CORE_CLK/inst/* || NAME =~ $prefix/ai_core_clk_locked_reg*"] {
    puts $out "CELL $cell"
    foreach prop {REF_NAME LOC BEL CLKIN1_PERIOD CLKIN2_PERIOD CLKFBOUT_MULT DIVCLK_DIVIDE CLKOUT0_DIVIDE CLKOUT1_DIVIDE COMPENSATION IS_LOC_FIXED IS_BEL_FIXED} {
        if {![catch {get_property $prop $cell} value]} {puts $out "  PROPERTY $prop=$value"}
    }
    foreach pin [get_pins -of_objects $cell] {
        puts $out "  PIN $pin DIR=[get_property DIRECTION $pin]"
        foreach net [get_nets -of_objects $pin] {
            puts $out "    NET $net"
            foreach other [get_pins -leaf -of_objects [get_nets -segments $net]] {
                puts $out "      LEAF $other DIR=[get_property DIRECTION $other]"
            }
        }
    }
}
foreach suffix {AI_CORE_CLK/inst/clkout1_buf/O ai_core_clk_locked_reg/Q} {
    set pin [get_pins $prefix/$suffix]
    puts $out "FANOUT $pin"
    foreach endpoint [all_fanout -flat -endpoints_only -from $pin] {puts $out "  ENDPOINT $endpoint"}
}
close $out
report_clocks -file $task_dir/clocks.rpt
report_property -all [get_cells $prefix/AI_CORE_CLK/inst/plle2_adv_inst] -file $task_dir/pll-properties.rpt
puts "PASS read-only frozen checkpoint clock topology audit"
close_design
exit
