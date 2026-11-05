# Run the vendor's original OOC precheck on the isolated verification project.
set task_root [file normalize [file join [file dirname [info script]] ..]]
open_project [file join $task_root outputs mig_check project mig_check.xpr]
if {![info exists ::env(JFM_PATH)]} { error "JFM_PATH is required" }
source [file join $::env(JFM_PATH) ip_patch run.tcl]
pre_patch_check
puts "WCIS ISOLATED JFM PRECHECK PASSED"
close_project
