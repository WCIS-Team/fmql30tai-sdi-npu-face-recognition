# Source as Tcl (never read_xdc): fail before placement if 2018.3 dropped any
# XDC commands or hierarchy assumptions. No severity downgrades.
foreach {name ball standard} {
    pl_eth_tx_clk AD23 LVCMOS18 pl_eth_tx_ctl AD26 LVCMOS18
    pl_eth_txd[0] AF24 LVCMOS18 pl_eth_txd[1] AF25 LVCMOS18
    pl_eth_txd[2] AA24 LVCMOS18 pl_eth_txd[3] AB24 LVCMOS18
    pl_eth_mdc AE22 LVCMOS18 pl_eth_mdio AF22 LVCMOS18
    pl_eth_reset_n AA13 LVCMOS33
} {
    set p [get_ports $name]
    if {[llength $p]!=1 || [get_property PACKAGE_PIN $p] ne $ball || [get_property IOSTANDARD $p] ne $standard} {
        error "Incomplete PL Ethernet pin constraint: $name / $ball / $standard"
    }
}
foreach name {pl_rgmii_tx pl_mdc} {
    if {[llength [get_clocks -quiet $name]]!=1} {error "Missing PL Ethernet clock: $name"}
}
foreach p [get_ports {pl_eth_txd[*] pl_eth_tx_ctl}] {
    foreach delay {min max} {
        set path [get_timing_paths -quiet -to $p -delay_type $delay -max_paths 1]
        if {![llength $path] || [get_property SLACK $path] in {inf -inf}} {error "Untimed preview output: $p / $delay"}
    }
}
set task_serializers [get_cells -hier -filter {NAME =~ U_pl_preview/network/* && REF_NAME == OSERDESE2}]
if {[llength $task_serializers]!=6} {error "Six shared-clock serializers required"}
set task_clock_pin [get_pins -of_objects [filter $task_serializers {NAME =~ *clock_serializer*}] -filter {REF_PIN_NAME == CLK}]
if {[llength $task_clock_pin]!=1} {error "Forwarded-clock serializer missing"}
set task_clock [get_clocks -of_objects $task_clock_pin]
if {[llength $task_clock]!=1 || abs([get_property PERIOD $task_clock]-4.0)>0.001} {error "Serializer requires 250 MHz shared master"}
puts "PREVIEW_CONSTRAINT_GATE_PASS: 9 exact pins/standards, TX/MDC clocks, finite TX setup/hold, six serializers"
source D:/renlianshibie/fpga_project/scripts/assert_pl_udp_payload_cut.tcl
source D:/renlianshibie/fpga_project/scripts/assert_pl_chunk_ram.tcl
