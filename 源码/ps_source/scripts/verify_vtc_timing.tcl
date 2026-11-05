# Local placed-and-routed check at the actual VTC clock (200 MHz).
# No JFM hooks, bitstream, board accesses or changes to clock constraints.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_out [file join $task_root outputs vtc-rewrite]
file mkdir $task_out
create_project -in_memory -part xc7z030ffg676-2
read_verilog [file join $task_root rtl wcis_vtc.v]
synth_design -top vtc -part xc7z030ffg676-2 -mode out_of_context
create_clock -name vtc_clk -period 5.000 [get_ports clk]
# The controls must be stable before source selection. Keep their paths
# timed here; no false path is used to make the isolated result pass.
set_input_delay -clock vtc_clk 0.5 [get_ports -filter {DIRECTION == IN && NAME != clk}]
set_output_delay -clock vtc_clk 0.5 [get_ports -filter {DIRECTION == OUT}]
opt_design
place_design
route_design
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $task_out timing.rpt]
report_utilization -file [file join $task_out utilization.rpt]
write_checkpoint -force [file join $task_out vtc_routed.dcp]
set task_worst [get_timing_paths -delay_type max -max_paths 1]
set task_hold [get_timing_paths -delay_type min -max_paths 1]
if {![llength $task_worst] || ![llength $task_hold]} {error "No timed VTC paths"}
set task_wns [get_property SLACK $task_worst]
set task_whs [get_property SLACK $task_hold]
puts "WCIS VTC routed WNS=$task_wns WHS=$task_whs"
if {$task_wns < 0 || $task_whs < 0} {error "VTC isolated timing failed; see timing.rpt"}
puts "WCIS VTC ISOLATED TIMING PASSED; full-board acceptance is separate."
close_project
