set task_root [file normalize [file dirname [info script]]]
source [file join $task_root readonly_tool_guard.tcl]
open_project [file join $task_root new-project-3 source_check.xpr]
set_param general.maxThreads 2
set source_root [file join $task_root source-test]
set f [open [file join $source_root design-files.txt] r]
set names [split [string trim [read $f]] "\n"]
close $f
foreach name $names {
    if {[file extension $name] in {".xci" ".bd"}} {
        create_ip_run [get_files [file join $source_root $name]]
    }
}
set ip_runs [get_runs -filter {IS_SYNTHESIS && NAME != "synth_1"}]
puts "OOC_RUNS: $ip_runs"
set pending {}
foreach run $ip_runs {
    if {![string match {*Complete*} [get_property STATUS $run]]} {lappend pending $run}
}
if {[llength $pending]} {
    launch_runs $pending -jobs 2
    foreach run $pending {wait_on_run $run}
}
foreach run $ip_runs {
    if {![string match {*Complete*} [get_property STATUS $run]]} {error "IP synthesis failed: $run"}
}
puts ALL_IP_SYNTHESIS_COMPLETE
source $::env(JFM_PATH)/ip_patch/run.tcl
add_hook_tcl_to_prj
set guard [file join $task_root readonly_tool_guard.tcl]
foreach hook [glob [file join $task_root new-project-3 ip_patch process_control *.tcl]] {
    set f [open $hook r]; set contents [read $f]; close $f
    set f [open $hook w]; puts $f [list source $guard]; puts -nonewline $f $contents; close $f
}
launch_runs impl_1 -to_step write_bitstream -jobs 2
wait_on_run impl_1
puts "FINAL_STATUS: [get_property STATUS [get_runs impl_1]]"
if {![string match {*Complete*} [get_property STATUS [get_runs impl_1]]]} {error "Bitstream run failed"}
open_run impl_1
file mkdir [file join $task_root final-build]
report_timing_summary -delay_type min_max -file [file join $task_root final-build timing.rpt]
report_route_status -file [file join $task_root final-build route-status.rpt]
report_drc -file [file join $task_root final-build drc.rpt]
report_utilization -file [file join $task_root final-build utilization.rpt]
puts SOURCE_TO_BITSTREAM_COMPLETE
close_project
