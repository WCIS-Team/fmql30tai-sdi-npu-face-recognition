source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl
set out D:/yzd/tmp/sdi-refclk-fix-20261020
set_param general.maxThreads 2
open_checkpoint D:/yzd/tmp/face-cache-resume-20261020/preserved-routed.dcp
set f [open $out/refclk-plan.txt w]
foreach name {R5 R6 U5 U6} {
 set p [get_package_pins $name]
 puts $f "BALL=$name SITE=[get_sites -of_objects $p] FUNCTION=[get_property PIN_FUNC $p]"
}
set c [get_cells rx_sdi_inst/MGTCLKIN0]
puts $f "REFCLK_CELL=$c LOC=[get_property LOC $c] BEL=[get_property BEL $c]"
foreach p [get_pins -of_objects $c] {
 set nets [get_nets -segments -of_objects $p]
 puts $f "PIN=$p"
 foreach n $nets {puts $f "NET=$n FIXED=[get_property IS_ROUTE_FIXED $n] ROUTE=[get_property ROUTE $n]"}
 foreach x [get_cells -of_objects [get_pins -leaf -of_objects $nets]] {
  puts $f "CELL=$x REF=[get_property REF_NAME $x] LOC=[get_property LOC $x] BEL=[get_property BEL $x] FIXED=[get_property IS_LOC_FIXED $x]"
 }
}
close $f
close_design
exit
