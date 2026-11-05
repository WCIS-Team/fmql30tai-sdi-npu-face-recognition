# One post-route physical optimization attempt on the saved rewritten design.
# No timing exceptions, clock changes, RTL changes, bitstream or board access.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_out [file join $task_root outputs rtl-rewrite-20261013]
open_checkpoint [file join $task_out rewritten_routed.dcp]
phys_opt_design -directive AggressiveExplore
route_design -directive NoTimingRelaxation
report_timing_summary -delay_type min_max -max_paths 20 -file [file join $task_out refined_timing.rpt]
report_route_status -file [file join $task_out refined_route_status.rpt]
report_timing -from [get_cells -hier -filter {NAME =~ */u_vtc/*}] -max_paths 20 -file [file join $task_out refined_vtc_paths.rpt]
report_timing -to [get_cells -hier -filter {NAME =~ */rate_gate/*}] -max_paths 20 -file [file join $task_out refined_gate_paths.rpt]
report_utilization -file [file join $task_out refined_utilization.rpt]
write_checkpoint -force [file join $task_out refined_routed.dcp]
puts "WCIS POST-ROUTE REFINEMENT FINISHED; accept only according to saved timing reports."
close_design
