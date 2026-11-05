set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_file [open [file join $task_root outputs procise_boot_help.txt] w]
foreach task_pattern {*boot* *image* *bif* *fmql*} {
    puts $task_file "$task_pattern: [info commands $task_pattern]"
}
foreach task_cmd {create_boot_image generate_boot_file dump_boot_image} {
    puts $task_file "HELP $task_cmd"
    if {[catch {$task_cmd -help} task_help]} { puts $task_file $task_help }
    puts $task_file $task_help
}
close $task_file
exit
