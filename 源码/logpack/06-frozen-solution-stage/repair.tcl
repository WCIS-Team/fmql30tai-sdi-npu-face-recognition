source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl
set out D:/yzd/tmp/sdi-refclk-fix-20261020
set_param general.maxThreads 2
open_checkpoint D:/yzd/tmp/face-cache-resume-20261020/preserved-routed.dcp
set gt [get_cells rx_sdi_inst/MGTCLKIN0]
set pbuf [get_cells FMC_HPC_GBTCLK0_M2C_C_P_IBUF_inst]
set nbuf [get_cells FMC_HPC_GBTCLK0_M2C_C_N_IBUF_inst]
if {[get_property LOC $gt] ne "IBUFDS_GTE2_X0Y0"} {error "Unexpected reference buffer"}
if {[get_property PACKAGE_PIN [get_ports FMC_HPC_GBTCLK0_M2C_C_P]] ne "R6"} {error "Unexpected original pin"}
if {[llength [get_cells -quiet -of_objects [get_sites IBUFDS_GTE2_X0Y1]]]} {error "Target reference buffer occupied"}
set targets [list $gt $pbuf $nbuf]
set protected_cells [lsort [get_cells -hier -filter {IS_PRIMITIVE && REF_NAME != VCC && REF_NAME != GND && NAME != rx_sdi_inst/MGTCLKIN0 && NAME != FMC_HPC_GBTCLK0_M2C_C_P_IBUF_inst && NAME != FMC_HPC_GBTCLK0_M2C_C_N_IBUF_inst}]]
set cell_before [list [get_property NAME $protected_cells] [get_property REF_NAME $protected_cells] [get_property LOC $protected_cells] [get_property BEL $protected_cells]]
set pins [get_pins [list $gt/I $gt/IB $gt/O]]
set roots [get_nets -top_net_of_hierarchical_group -segments -of_objects $pins]
set segments [get_nets -segments -of_objects $pins]
set excluded [dict create]
foreach n [get_property NAME $segments] {dict set excluded $n 1}
set protected_net_names {}
foreach n [get_property NAME [get_nets -hier -filter {TYPE != POWER && TYPE != GROUND}]] {
 if {![dict exists $excluded $n]} {lappend protected_net_names $n}
}
set protected_nets [get_nets $protected_net_names]
set routes_before [get_property ROUTE $protected_nets]
puts "PROTECTED_CELLS=[llength $protected_cells] PROTECTED_NONCONSTANT_NETS=[llength $protected_nets]"
set ground [get_nets -top_net_of_hierarchical_group -segments -of_objects [get_pins $gt/CEB]]
set ground [lindex $ground 0]
set ground_before [get_property ROUTE $ground]
set f [open $out/changed-nets.txt w]
foreach n $roots {puts $f $n}
close $f
set_property IS_ROUTE_FIXED false $roots
set_property FIXED_ROUTE {} $roots
route_design -unroute -nets $roots
set_property IS_LOC_FIXED false $targets
set_property IS_BEL_FIXED false $targets
unplace_cell $targets
source D:/renlianshibie/fpga_project/constraints/fmql30tai_full_sdi_refclk.xdc
place_cell [list $gt IBUFDS_GTE2_X0Y1/IBUFDS_GTE2 $pbuf IPAD_X1Y10/IPAD $nbuf IPAD_X1Y11/IPAD]
set now_ground [get_property ROUTE $ground]
if {$ground_before ne $now_ground} {
 puts "RESTORING_ORIGINAL_GROUND_ROUTE=true"
 set_property FIXED_ROUTE $ground_before $ground
 set_property IS_ROUTE_FIXED true $ground
}
route_design -nets $roots
set cell_after [list [get_property NAME $protected_cells] [get_property REF_NAME $protected_cells] [get_property LOC $protected_cells] [get_property BEL $protected_cells]]
if {$cell_before ne $cell_after} {error "Non-target cell changed"}
if {$routes_before ne [get_property ROUTE $protected_nets]} {error "Non-target nonconstant routing changed"}
if {[get_property LOC $gt] ne "IBUFDS_GTE2_X0Y1"} {error "Wrong reference input site"}
foreach {port ball} {FMC_HPC_GBTCLK0_M2C_C_P U6 FMC_HPC_GBTCLK0_M2C_C_N U5} {
 if {[get_property PACKAGE_PIN [get_ports $port]] ne $ball} {error "Reference pin mismatch"}
}
report_route_status -file $out/route-status.rpt
report_timing_summary -delay_type min_max -max_paths 20 -file $out/timing.rpt
report_drc -file $out/drc.rpt
set setup [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
if {$setup<0 || $hold<0} {error "Setup/hold timing failed"}
set f [open $out/preservation-proof.txt w]
puts $f "PROTECTED_CELLS_IDENTICAL=[llength $protected_cells]"
puts $f "PROTECTED_NONCONSTANT_ROUTES_IDENTICAL=[llength $protected_nets]"
puts $f "REFCLK_P=U6 REFCLK_N=U5 REFCLK_BUFFER=IBUFDS_GTE2_X0Y1"
puts $f "SETUP_WNS=$setup HOLD_WHS=$hold"
close $f
set_property BITSTREAM.CONFIG.USERID 32'h53201021 [current_design]
write_checkpoint -force $out/refclk-routed.dcp
close_design
exit
