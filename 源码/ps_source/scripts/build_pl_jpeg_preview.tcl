# Full source integration is required: the old routed netlist merged native
# CSR signals with other controllers. Never intercept their optimized aliases.
source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl
set task_root D:/renlianshibie/fpga_project
set task_out D:/yzd/tmp/pl-jpeg-bram-chunk-20261025
if {[info exists ::env(WCIS_PREVIEW_TASK)]} {set task_out [file normalize $::env(WCIS_PREVIEW_TASK)]}
set ::env(WCIS_CASE_DIR) $task_out/case
set_param general.maxThreads 4
source $task_root/scripts/prepare_case.tcl
foreach file [glob $::env(WCIS_CASE_DIR)/rtl/wcis/*.v] {
    if {![llength [get_files -quiet $file]]} {add_files -norecurse $file}
}
foreach file [concat [glob $::env(WCIS_CASE_DIR)/rtl/wcis/vendor/verilog_ethernet/rtl/*.v] [glob $::env(WCIS_CASE_DIR)/rtl/wcis/vendor/verilog_ethernet/axis/rtl/*.v]] {
    if {![llength [get_files -quiet $file]]} {add_files -norecurse $file}
}
foreach file [glob $::env(WCIS_CASE_DIR)/ip_patch/process_control/*.tcl] {
    set f [open $file r];set text [read $f];close $f
    if {![string match {*WCIS_TOOL_GUARD_HOOK*} $text]} {
        set f [open $file w];puts $f "# WCIS_TOOL_GUARD_HOOK\nsource {$task_root/scripts/readonly_tool_guard.tcl}";puts -nonewline $f $text;close $f
    }
}
set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY rebuilt [get_runs synth_1]
update_compile_order -fileset sources_1
reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {![string match {*Complete*} [get_property STATUS [get_runs synth_1]]]} {error "Full preview synthesis failed"}
open_run synth_1
report_utilization -file $task_out/preview-full-synthesis-utilization.rpt
write_checkpoint -force $task_out/preview-full-synthesis.dcp
source $task_root/scripts/assert_pl_chunk_ram.tcl
puts "FULL PREVIEW SYNTHESIS COMPLETE; IMPLEMENTATION AND BOARD ACCEPTANCE PENDING"
close_project
exit
