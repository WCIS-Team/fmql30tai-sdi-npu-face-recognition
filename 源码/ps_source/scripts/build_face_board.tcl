# Fresh isolated full-board route, never generate/deploy a bitstream before
# reviewing the actual complete-design timing, CDC, DRC and model evidence.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_out D:/yzd/tmp/face-pl-integration-20261015/board-build
file mkdir $task_out
set ::env(WCIS_CASE_DIR) [file join $task_out case]
source [file join $task_root scripts prepare_case.tcl]
# Vendor hooks may request an installed speed-library replacement. Enforce the
# repository's prohibition in child Vivado processes as well as this process.
set task_guard [file join $task_root scripts readonly_tool_guard.tcl]
foreach task_hook [glob [file join $::env(WCIS_CASE_DIR) ip_patch process_control *.tcl]] {
    set task_f [open $task_hook r];set task_text [read $task_f];close $task_f
    if {![string match {*WCIS_TOOL_GUARD_HOOK*} $task_text]} {
        set task_f [open $task_hook w]
        puts $task_f "# WCIS_TOOL_GUARD_HOOK\nsource {$task_guard}"
        puts -nonewline $task_f $task_text;close $task_f
    }
}
source $task_guard
foreach task_run {synth_1 impl_1} {
    if {[string match {*Running*} [get_property STATUS [get_runs $task_run]]]} {error "Run already active"}
}
reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {error "FACE full-board synthesis failed"}
open_run synth_1
foreach task_box {read_request write_request read_response} {
    set task_sync [get_cells -hier -regexp [format {.*U_adder_top/%s/(request_sync|ack_sync)_reg\[0\]} $task_box]]
    set task_hold [get_cells -hier -regexp [format {.*U_adder_top/%s/payload_hold_reg\[[0-9]+\]} $task_box]]
    set task_capture [get_cells -hier -regexp [format {.*U_adder_top/%s/m_data_reg\[[0-9]+\]} $task_box]]
    if {[llength $task_sync]!=2 || ![llength $task_hold] || ![llength $task_capture]} {error "Missing FACE mailbox cells: $task_box"}
    puts "FACE mailbox $task_box: [llength $task_hold] payload and [llength $task_capture] capture cells"
}
report_utilization -file [file join $task_out synthesis_utilization.rpt]
close_design
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {![string match {*Complete*} [get_property STATUS [get_runs impl_1]]]} {error "FACE full-board route failed"}
open_run impl_1
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $task_out timing.rpt]
report_utilization -file [file join $task_out utilization.rpt]
report_route_status -file [file join $task_out route_status.rpt]
report_bus_skew -file [file join $task_out bus_skew.rpt]
report_cdc -details -file [file join $task_out cdc.rpt]
report_drc -file [file join $task_out drc.rpt]
write_checkpoint -force [file join $task_out face_routed.dcp]
puts "FACE FULL BOARD ROUTED; review gates before bitstream/package/deployment."
close_project
