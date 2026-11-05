source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl
set task_out D:/yzd/tmp/pl-jpeg-bram-chunk-20261025
if {[info exists ::env(WCIS_PREVIEW_TASK)]} {set task_out [file normalize $::env(WCIS_PREVIEW_TASK)]}
open_checkpoint $task_out/preview-full-synthesis.dcp
set task_f [open $task_out/preview-clock-pins.txt w]
foreach task_p [get_pins -hier -filter {NAME =~ *U_pl_preview*serializer/CLK || NAME =~ *U_pl_preview*management*mdc_reg/C}] {puts $task_f $task_p}
close $task_f
read_xdc D:/renlianshibie/fpga_project/constraints/fmql30tai_pl_ethernet_tx.xdc
source D:/renlianshibie/fpga_project/constraints/pl_jpeg_preview_cdc.tcl
wcis_constrain_preview U_pl_preview
set frame_crossing U0_ps_ai_peripheral/frame_to_ps_inst0/frame_read_write_m0/write_error_crossing
if {[llength [get_cells -quiet $frame_crossing]]} {wcis_constrain_preview $frame_crossing}
source D:/renlianshibie/fpga_project/scripts/assert_pl_preview_constraints.tcl
report_clocks -file $task_out/preview-full-clocks.rpt
report_timing -to [get_ports pl_eth_mdio] -delay_type min_max -max_paths 4 -file $task_out/preview-mdio-timing.rpt
report_timing -to [get_ports {pl_eth_txd[*] pl_eth_tx_ctl}] -delay_type min_max -max_paths 4 -file $task_out/preview-rgmii-timing.rpt
write_checkpoint -force $task_out/preview-constrained-synthesis.dcp
puts "PREVIEW CONSTRAINTS LOADED; PLACEMENT AND ROUTING PENDING"
exit
