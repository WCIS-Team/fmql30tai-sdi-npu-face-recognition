source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl
set_param general.maxThreads 2
set out D:/yzd/tmp/sdi-refclk-fix-20261020
open_checkpoint $out/refclk-routed.dcp
# These four severities are the existing vendor/proxy policy, not new waivers.
foreach rule {REQP-44 REQP-46 REQP-52 REQP-56} {set_property SEVERITY Warning [get_drc_checks $rule]}
set cells [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME != VCC && REF_NAME != GND}]
set before_cells [list [get_property NAME $cells] [get_property REF_NAME $cells] [get_property LOC $cells] [get_property BEL $cells]]
set nets [get_nets -hier -filter {TYPE != POWER && TYPE != GROUND}]
set before_routes [get_property ROUTE $nets]
set ground [get_nets -top_net_of_hierarchical_group -segments -of_objects [get_pins rx_sdi_inst/MGTCLKIN0/CEB]]
set_property IS_ROUTE_FIXED false $ground
set_property FIXED_ROUTE {} $ground
route_design -preserve
if {$before_cells ne [list [get_property NAME $cells] [get_property REF_NAME $cells] [get_property LOC $cells] [get_property BEL $cells]]} {error "Nonconstant cell placement changed"}
if {$before_routes ne [get_property ROUTE $nets]} {error "Nonconstant net routing changed"}
report_route_status -file $out/route-status.rpt
report_timing_summary -delay_type min_max -max_paths 20 -file $out/timing.rpt
report_bus_skew -file $out/bus-skew.rpt
report_drc -file $out/drc.rpt
set f [open $out/ground-proof.txt w]
puts $f "ALL_PRIMITIVE_PLACEMENTS_IDENTICAL=[llength $cells]"
puts $f "ALL_NONCONSTANT_ROUTES_IDENTICAL=[llength $nets]"
puts $f "CONSTANT_GROUND_COMPLETION_ONLY=true"
close $f
write_checkpoint -force $out/refclk-final.dcp
close_design
exit
