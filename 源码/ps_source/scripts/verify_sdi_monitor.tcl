# Isolated logic synthesis/route. No vendor hooks, pin changes or BOOT writes.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_out [file join $task_root outputs sdi-diagnostics-20261014]
file mkdir $task_out
create_project -in_memory -part xc7z030ffg676-2
read_verilog [file join $task_root rtl wcis_sdi_monitor.v]
synth_design -top wcis_sdi_monitor -part xc7z030ffg676-2 -mode out_of_context
create_clock -period 20.0 [get_ports cfg_clk]
create_clock -period 6.734 [get_ports rx_clk]
set_input_delay -clock rx_clk 0.5 [get_ports {rx_flags[*] rx_vs rx_de}]
set_output_delay -clock cfg_clk 0.5 [get_ports words[*]]
foreach task_name {request_sync ack_sync ref_sync gt_sync} {
    set task_first [get_cells -regexp [format {%s_reg\[0\]} $task_name]]
    if {[llength $task_first] != 1} {error "Missing first-stage synchronizer: $task_name"}
    set_false_path -to [get_pins -of_objects $task_first -filter {REF_PIN_NAME == D}]
}
set task_hold [get_cells -regexp {payload_hold_reg\[[0-9]+\]}]
set task_snap [get_cells -regexp {snapshot_reg\[[0-9]+\]}]
if {![llength $task_hold] || ![llength $task_snap]} {error "Missing snapshot payload"}
set_max_delay -datapath_only 20.0 -from $task_hold -to $task_snap
set_bus_skew 20.0 -from $task_hold -to $task_snap
opt_design
place_design
route_design
report_utilization -file [file join $task_out monitor_utilization.rpt]
report_timing_summary -delay_type min_max -file [file join $task_out monitor_timing.rpt]
report_bus_skew -file [file join $task_out monitor_bus_skew.rpt]
report_cdc -details -file [file join $task_out monitor_cdc.rpt]
write_checkpoint -force [file join $task_out monitor_routed.dcp]
puts "SDI2 MONITOR ISOLATED CHECK COMPLETE; not a full-board timing or deployment result."
close_project
