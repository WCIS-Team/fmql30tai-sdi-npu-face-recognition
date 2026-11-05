# Restore the accepted routed implementation without synthesis/place/route.
set source_root [file normalize [file dirname [info script]]]
set baseline [file join $source_root .. fpga_restore refclk-final.dcp]
set output [file normalize [file join $source_root .. build-restored]]
file mkdir $output
set_param general.maxThreads 2
open_checkpoint $baseline
# Existing FMQL proxy-device DRC policy from the accepted build.
foreach rule {REQP-44 REQP-46 REQP-52 REQP-56} {
    set_property SEVERITY Warning [get_drc_checks $rule]
}
report_timing_summary -delay_type min_max -file [file join $output timing.rpt]
report_route_status -file [file join $output route-status.rpt]
write_bitstream -force [file join $output refclk.bit]
close_design
puts "Restored bitstream: [file join $output refclk.bit]"
set f [open [file join $output procise-command.txt] w]
puts $f [list set ::wcis_source_root $source_root]
puts $f [list source [file join $source_root package_restored.tcl]]
close $f
puts "Copy the two lines in [file join $output procise-command.txt] into Procise Tcl Console."
