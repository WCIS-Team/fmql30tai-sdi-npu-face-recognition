set task_scripts [file dirname [info script]]
source [file join $task_scripts prepare_case.tcl]
# RTL elaboration only: no synthesis/implementation run hooks are executed.
synth_design -rtl -name wcis_rtl -top ai7030_edif_top -part xc7z030ffg676-2
source [file join $task_scripts validate_sdi_constraints.tcl]
puts "WCIS FULL CASE RTL ELABORATION PASSED"
close_project
