# Reuse the last deployed reference for unchanged logic. No synthesis reset.
source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl
set task_root D:/renlianshibie/fpga_project
set task_out D:/yzd/tmp/pl-jpeg-bram-chunk-20261025
if {[info exists ::env(WCIS_PREVIEW_TASK)]} {set task_out [file normalize $::env(WCIS_PREVIEW_TASK)]}
set task_ref D:/yzd/tmp/sdi-refclk-fix-20261020/refclk-final.dcp
set_param general.maxThreads 4
open_project $task_out/case/fpai_demo_vivado.xpr
if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {error "Completed full-source synthesis required"}
if {![file exists $task_ref]} {error "Deployed layout reference missing"}
set task_layout_ref $task_ref
if {[info exists ::env(WCIS_PREVIEW_LAYOUT_REF)]} {
    set task_layout_ref [file normalize $::env(WCIS_PREVIEW_LAYOUT_REF)]
    if {![file exists $task_layout_ref]} {error "Requested layout guide missing"}
}
# Reuse the completed placement of the previous preview attempt. Its routing
# failed, so this is only a placement guide, never a deployable reference.
# The deployed f6 checkpoint remains the independent pin/NPU audit baseline.
set task_previous $task_out/implementation-r3-failed
if {[file exists $task_previous/ai7030_edif_top_physopt.dcp]} {
    set f [open $task_previous/runme.log r];set history [read $f];close $f
    set run_start [string last {****** Vivado v} $history]
    set history [string range $history $run_start end]
    foreach step {place_design phys_opt_design} {
        if {![string match "*$step completed successfully*" $history]} {error "Previous placement guide is incomplete: $step"}
    }
    set task_layout_ref $task_previous/ai7030_edif_top_physopt.dcp
}
set f [open $task_out/preview-layout-guide.txt w]
puts $f "LAYOUT_GUIDE=$task_layout_ref\nDEPLOYED_AUDIT_REFERENCE=$task_ref\nLAYOUT_GUIDE_IS_NOT_BOARD_ACCEPTANCE"
close $f
set task_xdc $task_root/constraints/fmql30tai_pl_ethernet_tx.xdc
if {![llength [get_files -quiet $task_xdc]]} {add_files -fileset constrs_1 -norecurse $task_xdc}
set_property USED_IN_SYNTHESIS false [get_files $task_xdc]
set_property PROCESSING_ORDER LATE [get_files $task_xdc]
# Keep all supplied vendor hooks. Chain our CDC constraints after their
# netlist patch, and replace only task-specific stale JPEG layout hooks.
set task_postopt $task_out/preview-postopt.tcl
set task_f [open $task_postopt w]
puts $task_f "source {$task_out/case/ip_patch/process_control/implementation_opt_post.tcl}"
puts $task_f "source {$task_root/constraints/pl_jpeg_preview_cdc.tcl}"
puts $task_f {wcis_constrain_preview U_pl_preview}
puts $task_f {set frame_crossing U0_ps_ai_peripheral/frame_to_ps_inst0/frame_read_write_m0/write_error_crossing}
puts $task_f {if {[llength [get_cells -quiet $frame_crossing]]} {wcis_constrain_preview $frame_crossing}}
puts $task_f {set pll [get_cells U_pl_preview/clocks]}
puts $task_f {if {[llength $pll]!=1 || [get_property REF_NAME $pll] ne "PLLE2_ADV"} {error "Preview PLL missing"}}
puts $task_f {set_property LOC PLLE2_ADV_X1Y1 $pll}
puts $task_f "source {$task_root/scripts/assert_pl_preview_constraints.tcl}"
close $task_f
set task_f [open $task_root/scripts/preserve_jpeg_shell.tcl r];set task_preserve [read $task_f];close $task_f
set task_preserve [string map [list D:/yzd/tmp/face-emmc-store-20261015/case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top_routed.dcp $task_layout_ref D:/yzd/tmp/pl-jpeg-board-20261016 $task_out] $task_preserve]
set task_preserve [string map [list { -reuse_objects $task_shell} {}] $task_preserve]
set task_f [open $task_out/preview-preserve-shell.tcl w];puts $task_f $task_preserve;close $task_f
set task_f [open $task_out/preview-release-routes.tcl w]
puts $task_f "set task_out {$task_out}"
puts $task_f "source {$task_root/scripts/release_pl_preview_routes.tcl}"
close $task_f
if {[info exists ::env(WCIS_PREVIEW_RESUME_PLACE)] && $::env(WCIS_PREVIEW_RESUME_PLACE) eq "1"} {
    set opt $task_out/case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top_opt.dcp
    if {![file exists $opt] || [file mtime $opt]<[file mtime $task_out/preview-full-synthesis.dcp]} {error "Fresh completed opt checkpoint required to resume placement"}
    reset_runs -from_step place_design [get_runs impl_1]
} else {
    reset_run impl_1
}
# Vivado 2018.3 High Reuse Default targets the reference WNS. The prior
# placement has negative WNS, so explicitly target 0 ns with Explore.
set_property STEPS.PLACE_DESIGN.ARGS.DIRECTIVE Explore [get_runs impl_1]
set_property STEPS.ROUTE_DESIGN.ARGS.DIRECTIVE Explore [get_runs impl_1]
set_property STEPS.OPT_DESIGN.TCL.POST $task_postopt [get_runs impl_1]
set_property STEPS.PLACE_DESIGN.TCL.PRE $task_out/preview-preserve-shell.tcl [get_runs impl_1]
set_property STEPS.PLACE_DESIGN.TCL.POST $task_root/scripts/gate_pl_preview_placement.tcl [get_runs impl_1]
set_property STEPS.ROUTE_DESIGN.TCL.PRE $task_out/preview-release-routes.tcl [get_runs impl_1]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED false [get_runs impl_1]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.TCL.PRE {} [get_runs impl_1]
# The placement hook reads the reference once, then fixes the DDR PHY LOCs.
# Do not also ask launch_runs to import it a second time.
set_property INCREMENTAL_CHECKPOINT {} [get_runs impl_1]
launch_runs impl_1 -to_step route_design -jobs 4
wait_on_run impl_1
if {![string match {route_design Complete*} [get_property STATUS [get_runs impl_1]]]} {error "Preview implementation failed"}
open_run impl_1
report_timing_summary -delay_type min_max -max_paths 30 -file $task_out/preview-timing.rpt
report_utilization -file $task_out/preview-utilization.rpt
report_route_status -file $task_out/preview-route-status.rpt
report_bus_skew -file $task_out/preview-bus-skew.rpt
report_cdc -details -file $task_out/preview-cdc.rpt
report_drc -file $task_out/preview-drc.rpt
report_incremental_reuse -file $task_out/preview-incremental-reuse.rpt
write_checkpoint -force $task_out/preview-routed.dcp
puts "PREVIEW ROUTED; TIMING REVIEW, BITSTREAM, BOOT AND BOARD ACCEPTANCE PENDING"
close_project
exit
