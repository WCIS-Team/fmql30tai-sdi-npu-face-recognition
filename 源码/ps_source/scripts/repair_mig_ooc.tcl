# Run this inside the user's current Vivado 2018.3 Tcl Console.
# Do not concurrently open the same project from a second batch process.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_case [file join $task_root case]
if {[llength [get_projects -quiet]] != 1} { error "Open the copied case project first" }
if {[file normalize [get_property DIRECTORY [current_project]]] ne $task_case} {
    error "This repair is limited to $task_case"
}
if {[get_property PART [current_project]] ne "xc7z030ffg676-2"} { error "Unexpected target part" }
source [file join $task_root scripts ooc_helpers.tcl]
wcis_rebuild_ooc_ip mig_7series_0
source [file join $task_case ip_patch run.tcl]
pre_patch_check
puts "WCIS PROJECT PRECHECK PASSED"
# A failed top-level synthesis run must be reset before retrying Generate Bitstream.
set task_top_run [get_runs -quiet synth_1]
if {[llength $task_top_run] == 1} {
    if {[regexp -nocase {error|fail} [get_property STATUS $task_top_run]]} { reset_run $task_top_run }
}
puts "WCIS: MIG OOC is complete. Retry Generate Bitstream using the tutorial's normal workflow."
puts "This repair does not generate/deploy BOOT.bin or replace installed timing databases."
