# Continue the routed task with standard post-route physical optimization.
# The remaining path is an existing resize-data to frame-FIFO path, not a
# clock-frequency or I/O-constraint change.
set task_out D:/yzd/tmp/pl-jpeg-board-20261016
source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl
open_project $task_out/case/fpai_demo_vivado.xpr
puts "POST_ROUTE_INPUT_STATUS=[get_property STATUS [get_runs impl_1]]"
if {![file exists $task_out/postroute-input.json] || ![file exists $task_out/case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top_routed.dcp]} {error "Bound completed routing proof required"}
set task_pre [open $task_out/postroute-pre.tcl w]
puts $task_pre {source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl}
puts $task_pre {set_param general.maxThreads 4}
close $task_pre
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED true [get_runs impl_1]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.ARGS.DIRECTIVE Explore [get_runs impl_1]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.TCL.PRE $task_out/postroute-pre.tcl [get_runs impl_1]
reset_runs -from_step {phys_opt_design (Post-Route)} [get_runs impl_1]
launch_runs impl_1 -to_step {phys_opt_design (Post-Route)} -scripts_only
# Vivado 2018.3's generated standalone post-route script queries the current
# project before opening its checkpoint. This task is a Vivado flow, so only
# replace that status-message query in the isolated generated script.
set task_generated $task_out/case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top.tcl
set task_handle [open $task_generated r]
set task_text [read $task_handle]
close $task_handle
set task_query {set tool_flow [get_property TOOL_FLOW [current_project]]}
if {[llength [split [string map [list $task_query "\u0001"] $task_text] "\u0001"]]!=3} {error "Unexpected generated flow-query count"}
file copy -force $task_generated $task_out/postroute-generated-before.tcl
set task_handle [open $task_generated w]
puts -nonewline $task_handle [string map [list $task_query {set tool_flow Vivado}] $task_text]
close $task_handle
set task_cwd [pwd]
cd $task_out/case/fpai_demo_vivado.runs/impl_1
exec cmd.exe /c runme.bat > $task_out/postroute-child-console.txt 2>@1
cd $task_cwd
close_project
open_project $task_out/case/fpai_demo_vivado.xpr
wait_on_run impl_1
if {![string match {phys_opt_design (Post-Route) Complete*} [get_property STATUS [get_runs impl_1]]]} {error "Post-route physical optimization failed"}
open_run impl_1
report_timing_summary -delay_type min_max -max_paths 20 -file $task_out/timing.rpt
report_utilization -file $task_out/utilization.rpt
report_route_status -file $task_out/route-status.rpt
report_bus_skew -file $task_out/bus-skew.rpt
report_cdc -details -file $task_out/cdc.rpt
report_drc -file $task_out/drc.rpt
write_checkpoint -force $task_out/jpeg-board-routed.dcp
puts "POST-ROUTE REPORTS WRITTEN; FRESH GATES/BOARD TEST REQUIRED"
close_project
exit
