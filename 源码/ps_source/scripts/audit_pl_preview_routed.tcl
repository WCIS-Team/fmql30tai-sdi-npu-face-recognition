source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl
set task_out D:/yzd/tmp/pl-jpeg-ethernet-1080p-20261023
open_checkpoint $task_out/preview-routed.dcp
source D:/renlianshibie/fpga_project/scripts/assert_pl_preview_constraints.tcl
set task_report [open $task_out/preview-routed-audit.txt w]
# Hold-to-capture payload paths must still be timed despite inherited clock
# exclusions. Inspect both legacy clients and all three new preview mailboxes.
set task_mailboxes {}
foreach client {face jpeg} {
    foreach box {read_request write_request read_response} {lappend task_mailboxes U_adder_top/$client/$box}
}
foreach box {configuration registers/status_mailbox stream/validation} {lappend task_mailboxes U_pl_preview/$box}
foreach box $task_mailboxes {
    set held [get_cells -hier -regexp "^$box/payload_hold_reg.*"]
    set capture [get_cells -hier -regexp "^$box/m_data_reg.*"]
    if {![llength $held] || ![llength $capture]} {error "Missing mailbox endpoints: $box"}
    set paths [get_timing_paths -from $held -to $capture -max_paths 1]
    if {![llength $paths]} {error "Mailbox hidden by false path: $box"}
    set slack [get_property SLACK $paths]
    if {$slack in {inf -inf} || $slack<0} {error "Mailbox timing failed: $box / $slack"}
    puts $task_report "MAILBOX=$box PAYLOAD=[llength $held] CAPTURE=[llength $capture] SLACK=$slack"
}
# Every DDR calibration replica must retain driven RST/REFCLK after placement.
set task_idcs [get_cells -hier -filter {REF_NAME == IDELAYCTRL}]
if {![llength $task_idcs]} {error "DDR calibration controllers missing"}
foreach idc $task_idcs {
    foreach pin {RST REFCLK} {
        set nets [get_nets -segments -of_objects [get_pins $idc/$pin]]
        set drivers [get_pins -leaf -of_objects $nets -filter {DIRECTION == OUT}]
        if {![llength $drivers]} {error "Disconnected DDR calibration: $idc/$pin"}
    }
}
puts $task_report "DDR_CALIBRATION_CONNECTED=[llength $task_idcs]"
foreach {name period} {pll_150 6.667 pll_125 8.0 pll_125_90 8.0 pl_rgmii_rx 8.0} {
    set clk [get_clocks $name]
    if {[llength $clk]!=1 || abs([get_property PERIOD $clk]-$period)>0.0011} {error "Wrong preview clock: $name"}
    puts $task_report "CLOCK=$name PERIOD=[get_property PERIOD $clk]"
}
set rxglobal [get_cells -hier -filter {NAME =~ U_pl_preview/network/*rx_ssio_ddr_inst/*clk_bufg && REF_NAME == BUFG}]
set rxio [get_cells -hier -filter {NAME =~ U_pl_preview/network/*rx_ssio_ddr_inst/*clk_bufio && REF_NAME == BUFIO}]
if {[llength $rxglobal]!=1 || [llength $rxio]!=1} {error "Preview RX requires dedicated BUFIO and global MAC clock"}
puts $task_report "RX_CLOCKS=$rxglobal / $rxio"
foreach p [get_ports {pl_eth_rxd[*] pl_eth_rx_ctl}] {
    foreach type {min max} {
        set paths [get_timing_paths -from $p -delay_type $type -max_paths 1]
        if {![llength $paths]} {error "Untimed routed RGMII input: $p / $type"}
        set slack [get_property SLACK $paths]
        if {$slack in {inf -inf} || $slack<0} {error "RGMII input timing failed: $p / $type / $slack"}
        puts $task_report "RX_INPUT=$p TYPE=$type SLACK=$slack"
    }
}
set task_jpeg_pin [get_pins -hier -regexp {.*U_adder_top/jpeg/job_cycles_reg\[0\]/C}]
set task_jpeg_clock [get_clocks -of_objects $task_jpeg_pin]
if {[llength $task_jpeg_pin]!=1 || [llength $task_jpeg_clock]!=1 || [get_property PERIOD $task_jpeg_clock]!=10.0} {error "Legacy JPEG counter clock changed"}
puts $task_report "JPEG_COUNTER_PERIOD=[get_property PERIOD $task_jpeg_clock]"
report_timing -from [get_ports {pl_eth_rxd[*] pl_eth_rx_ctl}] -delay_type min_max -max_paths 10 -file $task_out/preview-rx-io-routed.rpt
report_timing -to [get_ports {pl_eth_txd[*] pl_eth_tx_ctl pl_eth_mdio pl_eth_mdc}] -delay_type min_max -max_paths 14 -file $task_out/preview-tx-io-routed.rpt
set task_pinmap [dict create]
foreach p [get_ports] {dict set task_pinmap [get_property NAME $p] [list [get_property PACKAGE_PIN $p] [get_property IOSTANDARD $p]]}
set task_npu_path U0_ps_ai_peripheral/ZGolo/u_AI_Mate_top/clkrst_wrapper_u0/AI_CORE_CLK/inst/plle2_adv_inst
set task_npu [get_cells $task_npu_path]
if {[llength $task_npu]!=1} {error "NPU PLL missing"}
set task_npu_properties {CLKIN1_PERIOD DIVCLK_DIVIDE CLKFBOUT_MULT CLKOUT0_DIVIDE CLKOUT0_PHASE LOC}
set task_npu_values {}
foreach key $task_npu_properties {lappend task_npu_values [get_property $key $task_npu]}
# Reopening a checkpoint loses session-only severity policy. Restore exactly
# the four original vendor declarations, after checking the staged copy.
set task_heads {}
foreach path [list D:/yzd/tmp/face-emmc-store-20261015/case/constrs_1/ai7030.xdc $task_out/case/constrs_1/ai7030.xdc] {
    set f [open $path r];lappend task_heads [lrange [split [read $f] "\n"] 0 3];close $f
}
if {[lindex $task_heads 0] ne [lindex $task_heads 1]} {error "Original vendor DRC policy differs"}
foreach rule {REQP-44 REQP-46 REQP-52 REQP-56} line [lindex $task_heads 0] {
    set expected "set_property SEVERITY \{Warning\} \[get_drc_checks \{$rule\}\]"
    if {[string trim $line] ne $expected} {error "Unexpected vendor DRC declaration"}
    set_property SEVERITY Warning [get_drc_checks $rule]
    puts $task_report "INHERITED_VENDOR_DRC_WARNING=$rule"
}
report_drc -file $task_out/preview-drc-audited.rpt
close $task_report
close_design
open_checkpoint D:/yzd/tmp/sdi-refclk-fix-20261020/refclk-final.dcp
set task_count 0
foreach p [get_ports] {
    set name [get_property NAME $p]
    set value [list [get_property PACKAGE_PIN $p] [get_property IOSTANDARD $p]]
    if {![dict exists $task_pinmap $name] || [dict get $task_pinmap $name] ne $value} {error "Existing board pin changed: $name"}
    incr task_count
}
set task_reference_values {}
foreach key $task_npu_properties {lappend task_reference_values [get_property $key [get_cells $task_npu_path]]}
if {$task_reference_values ne $task_npu_values} {error "Existing NPU clock configuration or placement changed"}
set task_report [open $task_out/preview-routed-audit.txt a]
puts $task_report "EXISTING_PORT_PIN_STANDARDS_UNCHANGED=$task_count"
puts $task_report "NPU_PLL_CONFIG_AND_LOC_UNCHANGED=$task_npu_values"
puts $task_report "ROUTED_STRUCTURAL_AUDIT_PASS"
close $task_report
puts "PREVIEW ROUTED MAILBOX, PIN, CLOCK AND DDR CALIBRATION AUDIT COMPLETE"
close_design
exit
