set root D:/yuanma/submission
source $root/restore/open_source_project.tcl
set f [open [file join [pwd] vivado_source_compile_order.txt] w]
foreach obj [get_files -compile_order sources -used_in synthesis] {puts $f [get_property NAME $obj]}
close $f
puts "SUBMISSION_SOURCE_OPEN_OK"
close_project
source $root/restore/open_implemented.tcl
puts "SUBMISSION_CHECKPOINT_OPEN_OK"
report_route_status -file [file join [pwd] reopened_route_status.rpt]
report_utilization -file [file join [pwd] reopened_utilization.rpt]
close_design
exit
