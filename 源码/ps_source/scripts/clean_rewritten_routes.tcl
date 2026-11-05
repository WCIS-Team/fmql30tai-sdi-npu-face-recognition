# Remove disconnected routing remnants on the two explicitly reported nets.
# Preserve RTL, pins, clocks and timing constraints; no bitstream/board work.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_out [file join $task_root outputs rtl-rewrite-20261013]
open_checkpoint [file join $task_out refined_routed.dcp]
set task_names [list \
    {U0_ps_ai_peripheral/ZGolo/s_valid_i_2__8_n_0} \
    {U0_ps_ai_peripheral/frame_to_ps_inst0/frame_read_write_m0/write_buf/U0/inst_fifo_gen/gconvfifo.rf/grf.rf/gntv_or_sync_fifo.gl0.wr/wpntr/ENA_I_2}]
set task_nets [list]
foreach task_name $task_names {
    set task_net [get_nets -quiet $task_name]
    if {[llength $task_net] != 1} {error "Expected exactly one reported net: $task_name"}
    route_design -unroute -nets $task_net
    lappend task_nets $task_net
}
# Limit the router to these nets and retain every other existing route.
route_design -nets $task_nets
report_route_status -file [file join $task_out cleaned_route_status.rpt]
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $task_out cleaned_timing.rpt]
report_bus_skew -file [file join $task_out cleaned_bus_skew.rpt]
report_drc -file [file join $task_out cleaned_drc.rpt]
report_timing -from [get_cells -hier -filter {NAME =~ */u_vtc/*}] -max_paths 20 -file [file join $task_out cleaned_vtc_paths.rpt]
report_timing -to [get_cells -hier -filter {NAME =~ */rate_gate/*}] -max_paths 20 -file [file join $task_out cleaned_gate_paths.rpt]
write_checkpoint -force [file join $task_out cleaned_routed.dcp]
puts "WCIS TARGETED ROUTE CLEANUP FINISHED; check routing and timing reports."
close_design
