# Shared by the GUI repair and the isolated verification project.
# Regenerates the selected IP in the project being operated on.
proc wcis_rebuild_ooc_ip {ip_name} {
    if {[llength [get_projects -quiet]] != 1} { error "Open exactly one project first" }
    set task_ip [get_ips -quiet $ip_name]
    if {[llength $task_ip] != 1} { error "Expected exactly one IP named $ip_name" }
    set task_xci [get_files -all -quiet *${ip_name}.xci]
    if {[llength $task_xci] != 1} { error "Expected exactly one XCI for $ip_name" }
    foreach task_run [get_runs -quiet] {
        if {[regexp -nocase {running|queued} [get_property STATUS $task_run]]} {
            error "A build run is active; let it finish before repairing IP: $task_run"
        }
    }
    config_ip_cache -disable_cache
    # The copied XPR initially retained an absolute cache path in Downloads.
    # Keep any regenerated artifacts in this project's own directory.
    set task_project_dir [get_property DIRECTORY [current_project]]
    set_property ip_output_repo [file join $task_project_dir ip_cache] [current_project]
    set_property GENERATE_SYNTH_CHECKPOINT true $task_xci
    if {[lsearch -exact [list_property $task_xci] SYNTH_CHECKPOINT_MODE] >= 0} {
        set_property SYNTH_CHECKPOINT_MODE Singular $task_xci
    }
    puts "WCIS: resetting/regenerating $ip_name with cache disabled and OOC checkpoint enabled"
    reset_target all $task_xci
    generate_target all $task_xci
    create_ip_run $task_xci
    set task_ooc [get_runs -quiet ${ip_name}_synth_1]
    if {[llength $task_ooc] != 1} { error "OOC synthesis run was not created for $ip_name" }
    reset_run $task_ooc
    launch_runs $task_ooc -jobs 4
    wait_on_run $task_ooc
    set task_status [get_property STATUS $task_ooc]
    if {![string match "*Complete*" $task_status]} {
        error "$ip_name OOC synthesis did not complete: $task_status"
    }
    puts "WCIS OOC REPAIR PASSED: $ip_name -> $task_status"
}
