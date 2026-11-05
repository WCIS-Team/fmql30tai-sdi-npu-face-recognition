# Read/elaborate project metadata, without running vendor hooks or changing
# installed device timing files. Use before opening the full implementation.
set task_root [file normalize [file join [file dirname [info script]] ..]]
open_project [file join $task_root case fpai_demo_vivado.xpr]
config_ip_cache -disable_cache
add_files -norecurse [file join $task_root case rtl wcis wcis_frame_rate_gate.v]
set_property ip_repo_paths [list [file join $task_root case "PS_AI IP"]] [current_project]
update_ip_catalog
update_compile_order -fileset sources_1
set task_out [file join $task_root outputs]
file mkdir $task_out
report_ip_status -file [file join $task_out case_ip_status.rpt]
puts "WCIS CASE INSPECTION COMPLETE"
close_project
