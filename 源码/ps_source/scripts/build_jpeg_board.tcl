set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_out D:/yzd/tmp/pl-jpeg-board-20261016
set ::env(WCIS_CASE_DIR) $task_out/case
source $task_root/scripts/prepare_case.tcl
foreach f {wcis_recording_customop.v wcis_jpeg_customop.v wcis_jpeg_compressor.v} {
    add_files -norecurse $::env(WCIS_CASE_DIR)/rtl/wcis/$f
}
add_files -norecurse [glob $::env(WCIS_CASE_DIR)/rtl/wcis/jpeg_vendor/*.v]
add_files -fileset constrs_1 -norecurse $::env(WCIS_CASE_DIR)/constrs_1/emmc_timing.xdc
update_compile_order -fileset sources_1
set task_guard $task_root/scripts/readonly_tool_guard.tcl
foreach hook [glob $::env(WCIS_CASE_DIR)/ip_patch/process_control/*.tcl] {
    set f [open $hook r];set text [read $f];close $f
    if {![string match {*WCIS_TOOL_GUARD_HOOK*} $text]} {
        set f [open $hook w];puts $f "# WCIS_TOOL_GUARD_HOOK\nsource {$task_guard}";puts -nonewline $f $text;close $f
    }
}
source $task_guard
reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {error "JPEG synthesis failed"}
open_run synth_1
foreach client {face jpeg} {
    foreach box {read_request write_request read_response} {
        set prefix ".*U_adder_top/$client/$box/"
        set sync [get_cells -hier -regexp [format {%s(request_sync|ack_sync)_reg\[0\]} $prefix]]
        set hold [get_cells -hier -regexp [format {%spayload_hold_reg\[[0-9]+\]} $prefix]]
        set capture [get_cells -hier -regexp [format {%sm_data_reg\[[0-9]+\]} $prefix]]
        if {[llength $sync]!=2 || ![llength $hold] || ![llength $capture]} {error "Mailbox missing: $client/$box"}
        puts "MAILBOX $client/$box payload=[llength $hold] capture=[llength $capture]"
    }
}
report_utilization -file $task_out/synthesis-utilization.rpt
close_design
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {![string match {*Complete*} [get_property STATUS [get_runs impl_1]]]} {error "JPEG route failed"}
open_run impl_1
report_timing_summary -delay_type min_max -max_paths 20 -file $task_out/timing.rpt
report_utilization -file $task_out/utilization.rpt
report_route_status -file $task_out/route-status.rpt
report_bus_skew -file $task_out/bus-skew.rpt
report_cdc -details -file $task_out/cdc.rpt
report_drc -file $task_out/drc.rpt
write_checkpoint -force $task_out/jpeg-board-routed.dcp
puts "JPEG BOARD ROUTED; review timing/CDC/DRC before packaging"
close_project
exit
