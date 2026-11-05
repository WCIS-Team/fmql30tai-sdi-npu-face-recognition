# Full-board timing verification only. Does not generate/package/deploy BOOT.
# Retain prior evidence and reuse placement/routing where the tool allows it.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_out [file join $task_root outputs rtl-rewrite-20261013]
file mkdir $task_out
source [file join $task_root scripts prepare_case.tcl]
foreach task_run {synth_1 impl_1} {
    if {[string match {*Running*} [get_property STATUS [get_runs $task_run]]]} {
        error "Another build is already active: $task_run"
    }
}
set task_impl [file join $task_root case fpai_demo_vivado.runs impl_1]
foreach task_file [glob -nocomplain [file join $task_impl *.rpt]] {
    set task_saved [file join $task_out before_[file tail $task_file]]
    if {![file exists $task_saved]} {file copy $task_file $task_saved}
}
set task_old_dcp [file join $task_impl ai7030_edif_top_routed.dcp]
set task_reference [file join $task_out before_routed.dcp]
if {[file exists $task_old_dcp] && ![file exists $task_reference]} {file copy $task_old_dcp $task_reference}
reset_run synth_1
if {[file exists $task_reference]} {
    set_property incremental_checkpoint $task_reference [get_runs impl_1]
}
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {
    error "Rewritten top synthesis failed"
}
open_run synth_1
source [file join $task_root scripts validate_sdi_constraints.tcl]
close_design
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {![string match {*Complete*} [get_property STATUS [get_runs impl_1]]]} {
    error "Rewritten implementation failed"
}
open_run impl_1
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $task_out timing.rpt]
report_utilization -file [file join $task_out utilization.rpt]
report_route_status -file [file join $task_out route_status.rpt]
report_timing -from [get_cells -hier -filter {NAME =~ */u_vtc/*}] -max_paths 20 -file [file join $task_out vtc_paths.rpt]
report_timing -to [get_cells -hier -filter {NAME =~ */rate_gate/*}] -max_paths 20 -file [file join $task_out gate_paths.rpt]
write_checkpoint -force [file join $task_out rewritten_routed.dcp]
puts "WCIS REWRITTEN CASE ROUTED; inspect setup/hold/pulse-width reports before acceptance."
close_project
