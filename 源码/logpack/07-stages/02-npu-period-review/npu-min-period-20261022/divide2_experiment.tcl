# Isolated design change, not a timing override. Never writes the original DCP.
source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl
set task_dir D:/yzd/tmp/npu-min-period-20261022
open_checkpoint D:/yzd/tmp/pl-command-validation-20261022/preserved-routed.dcp
set prefix U0_ps_ai_peripheral/ZGolo/u_AI_Mate_top/clkrst_wrapper_u0/AI_CORE_CLK/inst
set pll [get_cells $prefix/plle2_adv_inst]
if {[llength $pll] != 1 || [get_property REF_NAME $pll] ne "PLLE2_ADV"} {error "PLL identity mismatch"}
foreach {key expected} {CLKFBOUT_MULT 5 DIVCLK_DIVIDE 1 CLKOUT0_DIVIDE 1 CLKIN1_PERIOD 5.000} {
    if {[get_property $key $pll] != $expected} {error "Unexpected original PLL property $key"}
}
set before [open $task_dir/divide2-before.txt w]
foreach key {CLKFBOUT_MULT DIVCLK_DIVIDE CLKOUT0_DIVIDE CLKIN1_PERIOD LOC BEL} {puts $before "$key=[get_property $key $pll]"}
foreach clock [get_clocks -of_objects [get_pins $prefix/clkout1_buf/O]] {puts $before "CLOCK $clock PERIOD=[get_property PERIOD $clock]"}
close $before
# Leaves the 1GHz VCO unchanged, halves only the connected CLKOUT0 output.
set_property CLKOUT0_DIVIDE 2 $pll
update_timing
set clock [get_clocks -of_objects [get_pins $prefix/clkout1_buf/O]]
if {[llength $clock] != 1 || abs([get_property PERIOD $clock]-2.0)>0.000001} {
    error "Auto-derived clock did not reflect real divide-by-two hardware; no override allowed"
}
set after [open $task_dir/divide2-after.txt w]
foreach key {CLKFBOUT_MULT DIVCLK_DIVIDE CLKOUT0_DIVIDE CLKIN1_PERIOD LOC BEL} {puts $after "$key=[get_property $key $pll]"}
puts $after "CLOCK $clock PERIOD=[get_property PERIOD $clock]"
close $after
report_timing_summary -delay_type min_max -max_paths 5 -file $task_dir/divide2-timing.rpt
report_drc -file $task_dir/divide2-drc.rpt
report_route_status -file $task_dir/divide2-route.rpt
report_bus_skew -file $task_dir/divide2-bus-skew.rpt
write_checkpoint $task_dir/divide2-experimental-routed.dcp
puts "PASS isolated real PLL divider experiment; no routing or timing waiver performed"
close_design
exit
