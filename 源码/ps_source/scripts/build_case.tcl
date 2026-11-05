# Rebuild copied project after reviewed source changes; no board writes.
set task_root [file normalize [file join [file dirname [info script]] ..]]
source [file join $task_root scripts prepare_case.tcl]
foreach task_run {synth_1 impl_1} {
    if {[get_property PROGRESS [get_runs $task_run]] ne "100%" &&
        [string match {*Running*} [get_property STATUS [get_runs $task_run]]]} {
        error "A run is already active: $task_run"
    }
}
reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {
    error "Top synthesis failed"
}
open_run synth_1
source [file join $task_root scripts validate_sdi_constraints.tcl]
close_design
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {![string match {*Complete*} [get_property STATUS [get_runs impl_1]]]} {
    error "Implementation/bitstream failed"
}
puts "WCIS BUILD COMPLETE. Timing must be reviewed separately before deployment."
close_project
