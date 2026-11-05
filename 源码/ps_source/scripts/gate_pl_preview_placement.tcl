# Stop large NEW timing failures before spending time in full-board routing.
# The existing NPU pulse-width issue is reported independently, never waived.
if {![info exists task_out]} {
    if {![info exists ::env(WCIS_PREVIEW_TASK)]} {error "Preview task directory required"}
    set task_out [file normalize $::env(WCIS_PREVIEW_TASK)]
}
# Retain the placed netlist even if the admission checks below stop the run.
write_checkpoint -force $task_out/preview-placed.dcp
report_timing_summary -delay_type min_max -max_paths 20 -file $task_out/preview-placed-timing.rpt
set preview_registers [get_cells -hier -filter {NAME =~ U_pl_preview/* && IS_SEQUENTIAL}]
if {![llength $preview_registers]} {error "Preview sequential logic missing"}
set report [open $task_out/preview-placement-gate.txt w]
foreach type {max min} {
    foreach direction {from to} {
        set args [list get_timing_paths -delay_type $type -max_paths 1 -$direction $preview_registers]
        set paths [eval $args]
        if {![llength $paths]} {error "Preview paths missing: $type $direction"}
        set slack [get_property SLACK $paths]
        puts $report "PREVIEW_$direction/$type=$slack"
        if {$slack in {inf -inf} || $slack < -0.5} {
            close $report
            error "Large new preview placed timing violation; route stopped: $direction $type $slack"
        }
    }
}
check_timing -verbose -file $task_out/preview-clock-admission.rpt
set f [open $task_out/preview-clock-admission.rpt r];set checks [read $f];close $f
if {![regexp {There are 0 generated clocks that are not connected to a clock source} $checks]} {
    close $report
    error "Generated-clock source latency is not established; route stopped"
}
puts $report "PLACEMENT_GATE_PASS; routed nonnegative timing remains required"
close $report
