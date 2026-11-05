# Recover the known-good board's placement/routing instead of moving all of
# the vendor DDR PHY when adding an unrelated client. No RTL/IO/clock changes.
set task_out D:/yzd/tmp/pl-jpeg-board-20261016
set task_reference D:/yzd/tmp/face-emmc-store-20261015/case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top_routed.dcp
source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl
open_project $task_out/case/fpai_demo_vivado.xpr
if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {error "Existing JPEG synthesis is required"}
if {![file exists $task_reference]} {error "Verified eMMC reference missing"}
reset_run impl_1
set_property INCREMENTAL_CHECKPOINT $task_reference [get_runs impl_1]
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {![string match {route_design Complete*} [get_property STATUS [get_runs impl_1]]]} {error "Incremental JPEG route failed"}
open_run impl_1
report_timing_summary -delay_type min_max -max_paths 20 -file $task_out/timing.rpt
report_utilization -file $task_out/utilization.rpt
report_route_status -file $task_out/route-status.rpt
report_bus_skew -file $task_out/bus-skew.rpt
report_cdc -details -file $task_out/cdc.rpt
report_drc -file $task_out/drc.rpt
report_incremental_reuse -file $task_out/incremental-reuse.rpt
write_checkpoint -force $task_out/jpeg-board-routed.dcp
puts "INCREMENTAL JPEG BOARD ROUTED; fresh audit and board proof required"
close_project
exit
