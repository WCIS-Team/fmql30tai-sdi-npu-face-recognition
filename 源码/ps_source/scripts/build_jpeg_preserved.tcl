set task_out D:/yzd/tmp/pl-jpeg-board-20261016
source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl
open_project $task_out/case/fpai_demo_vivado.xpr
if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {error "Existing JPEG synthesis required"}
reset_property STEPS.ROUTE_DESIGN.TCL.PRE [get_runs impl_1]
if {[info exists ::env(WCIS_JPEG_RESUME_ROUTE)] && $::env(WCIS_JPEG_RESUME_ROUTE) eq "1"} {
    if {![file exists $task_out/case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top_physopt.dcp]} {error "Physical optimization checkpoint required for route resume"}
    reset_runs -from_step route_design [get_runs impl_1]
    set_property STEPS.ROUTE_DESIGN.TCL.PRE D:/renlianshibie/fpga_project/scripts/release_jpeg_conflicts.tcl [get_runs impl_1]
} elseif {[info exists ::env(WCIS_JPEG_RESUME_PLACE)] && $::env(WCIS_JPEG_RESUME_PLACE) eq "1"} {
    if {![file exists $task_out/case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top_opt.dcp]} {error "Optimized checkpoint required for placement resume"}
    reset_runs -from_step place_design [get_runs impl_1]
} else {
    reset_run impl_1
    reset_property STEPS.ROUTE_DESIGN.TCL.PRE [get_runs impl_1]
}
reset_property INCREMENTAL_CHECKPOINT [get_runs impl_1]
set_property STEPS.PLACE_DESIGN.TCL.PRE D:/renlianshibie/fpga_project/scripts/preserve_jpeg_shell.tcl [get_runs impl_1]
set_property STEPS.ROUTE_DESIGN.TCL.PRE D:/renlianshibie/fpga_project/scripts/release_jpeg_conflicts.tcl [get_runs impl_1]
set_property STEPS.PLACE_DESIGN.ARGS.DIRECTIVE Default [get_runs impl_1]
if {[info exists ::env(WCIS_JPEG_FRESH_ROUTING)] && $::env(WCIS_JPEG_FRESH_ROUTING) eq "1"} {
    set_property STEPS.ROUTE_DESIGN.ARGS.DIRECTIVE Default [get_runs impl_1]
} else {
    set_property STEPS.ROUTE_DESIGN.ARGS.DIRECTIVE Explore [get_runs impl_1]
}
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {![string match {route_design Complete*} [get_property STATUS [get_runs impl_1]]]} {error "Preserved-shell route failed"}
open_run impl_1
report_timing_summary -delay_type min_max -max_paths 20 -file $task_out/timing.rpt
report_utilization -file $task_out/utilization.rpt
report_route_status -file $task_out/route-status.rpt
report_bus_skew -file $task_out/bus-skew.rpt
report_cdc -details -file $task_out/cdc.rpt
report_drc -file $task_out/drc.rpt
report_incremental_reuse -file $task_out/incremental-reuse.rpt
write_checkpoint -force $task_out/jpeg-board-routed.dcp
puts "PRESERVED-SHELL JPEG BOARD ROUTED; FRESH GATES/BOARD TEST REQUIRED"
close_project
exit
