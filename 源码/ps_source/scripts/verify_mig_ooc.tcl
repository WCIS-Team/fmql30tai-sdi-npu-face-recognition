# Isolated project: never opens or modifies the user's GUI project.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_check [file join $task_root outputs mig_check]
create_project mig_check [file join $task_check project] -part xc7z030ffg676-2
read_ip [file join $task_check ip mig_7series_0.xci]
source [file join $task_root scripts ooc_helpers.tcl]
wcis_rebuild_ooc_ip mig_7series_0
close_project
