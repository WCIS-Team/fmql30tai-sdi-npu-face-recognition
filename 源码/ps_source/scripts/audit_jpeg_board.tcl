# Verify real routed bundled-data paths weren't hidden by inherited clock cuts.
set task_out D:/yzd/tmp/pl-jpeg-board-20261016
open_checkpoint $task_out/jpeg-board-routed.dcp
set report [open $task_out/mailbox-audit.txt w]
foreach client {face jpeg} {
    foreach box {read_request write_request read_response} {
        set prefix ".*U_adder_top/$client/$box/"
        set hold [get_cells -hier -regexp [format {%spayload_hold_reg\[[0-9]+\]} $prefix]]
        set capture [get_cells -hier -regexp [format {%sm_data_reg\[[0-9]+\]} $prefix]]
        if {![llength $hold] || ![llength $capture]} {error "Missing mailbox endpoints: $client/$box"}
        set paths [get_timing_paths -from $hold -to $capture -max_paths 1]
        if {![llength $paths]} {error "Mailbox payload path hidden by false-path: $client/$box"}
        set slack [get_property SLACK $paths]
        if {$slack < 0} {error "Mailbox max-delay failed: $client/$box, $slack"}
        puts $report "$client/$box payload=[llength $hold] capture=[llength $capture] SLACK=$slack"
        report_timing -from $hold -to $capture -max_paths 1 -file $task_out/mailbox-${client}-${box}.rpt
    }
}
set clock_pins [get_pins -hier -regexp {.*U_adder_top/jpeg/job_cycles_reg\[0\]/C}]
if {[llength $clock_pins]!=1} {error "JPEG cycle-counter clock pin missing"}
set clocks [get_clocks -of_objects $clock_pins]
if {[llength $clocks]!=1 || [get_property PERIOD $clocks]!=10.0} {error "JPEG counter requires a verified 100 MHz clock"}
puts $report "JPEG_COUNTER_CLOCK=$clocks PERIOD=[get_property PERIOD $clocks] ns"
set task_idcs [get_cells -hier -filter {REF_NAME == IDELAYCTRL}]
if {![llength $task_idcs]} {error "DDR calibration controller missing after route"}
foreach task_idc $task_idcs {
    foreach task_input {RST REFCLK} {
        set task_pin [get_pins $task_idc/$task_input]
        set task_nets [get_nets -segments -of_objects $task_pin]
        set task_drivers [get_pins -leaf -of_objects $task_nets -filter {DIRECTION == OUT}]
        if {![llength $task_nets] || ![llength $task_drivers]} {
            error "DDR calibration input has no driver: $task_idc/$task_input"
        }
        puts $report "CALIBRATION_INPUT=$task_idc/$task_input DRIVER=$task_drivers"
    }
}
puts $report "CALIBRATION_INPUTS_CONNECTED=[llength $task_idcs] controllers"
# DRC severity settings are session state in this tool version. Restore only
# the four existing vendor declarations after reopening the routed checkpoint.
# Do not reread the whole XDC or change any clock/pin constraint.
set task_policy_reference D:/yzd/tmp/face-emmc-store-20261015/case/constrs_1/ai7030.xdc
set task_policy_staged $task_out/case/constrs_1/ai7030.xdc
set task_heads {}
foreach task_policy [list $task_policy_reference $task_policy_staged] {
    set task_file [open $task_policy r]
    lappend task_heads [lrange [split [read $task_file] "\n"] 0 3]
    close $task_file
}
if {[lindex $task_heads 0] ne [lindex $task_heads 1]} {error "Original vendor DRC policy differs"}
foreach task_rule {REQP-44 REQP-46 REQP-52 REQP-56} task_line [lindex $task_heads 0] {
    set task_expected "set_property SEVERITY \{Warning\} \[get_drc_checks \{$task_rule\}\]"
    if {[string trim $task_line] ne $task_expected} {error "Unexpected vendor DRC declaration"}
    set_property SEVERITY Warning [get_drc_checks $task_rule]
    puts $report "INHERITED_VENDOR_DRC_WARNING=$task_rule"
}
report_drc -file $task_out/drc.rpt
close $report
puts "JPEG MAILBOX AND CLOCK AUDIT PASSED"
close_design
exit
