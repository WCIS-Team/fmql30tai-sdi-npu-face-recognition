# Full FMQL30TAI manual, section PL Ethernet, pins 219-235 in the extracted
# board manual. These are NEW port assignments; existing ports are untouched.
# Vivado 2018.3 read_xdc does not execute foreach/if. Keep these declarative.
set_property PACKAGE_PIN AD23 [get_ports pl_eth_tx_clk]
set_property PACKAGE_PIN AD26 [get_ports pl_eth_tx_ctl]
set_property PACKAGE_PIN AF24 [get_ports {pl_eth_txd[0]}]
set_property PACKAGE_PIN AF25 [get_ports {pl_eth_txd[1]}]
set_property PACKAGE_PIN AA24 [get_ports {pl_eth_txd[2]}]
set_property PACKAGE_PIN AB24 [get_ports {pl_eth_txd[3]}]
set_property PACKAGE_PIN AC23 [get_ports pl_eth_rx_clk]
set_property PACKAGE_PIN AA25 [get_ports pl_eth_rx_ctl]
set_property PACKAGE_PIN AB26 [get_ports {pl_eth_rxd[0]}]
set_property PACKAGE_PIN AC26 [get_ports {pl_eth_rxd[1]}]
set_property PACKAGE_PIN AE25 [get_ports {pl_eth_rxd[2]}]
set_property PACKAGE_PIN AE26 [get_ports {pl_eth_rxd[3]}]
set_property PACKAGE_PIN AE22 [get_ports pl_eth_mdc]
set_property PACKAGE_PIN AF22 [get_ports pl_eth_mdio]
set_property IOSTANDARD LVCMOS18 [get_ports {pl_eth_tx_clk pl_eth_tx_ctl pl_eth_txd[*] pl_eth_rx_clk pl_eth_rx_ctl pl_eth_rxd[*] pl_eth_mdc pl_eth_mdio}]
set_property PACKAGE_PIN AA13 [get_ports pl_eth_reset_n]
set_property IOSTANDARD LVCMOS33 [get_ports pl_eth_reset_n]
set_property DRIVE 8 [get_ports {pl_eth_tx_clk pl_eth_tx_ctl pl_eth_txd[*] pl_eth_mdc pl_eth_mdio pl_eth_reset_n}]
set_property SLEW FAST [get_ports {pl_eth_tx_clk pl_eth_tx_ctl pl_eth_txd[*]}]
set_property SLEW SLOW [get_ports {pl_eth_mdc pl_eth_mdio pl_eth_reset_n}]
set_property PULLUP true [get_ports pl_eth_mdio]

# YT8521S Tables 137/138 guarantee >=1 ns setup/hold with the 1.95 ns
# reference delay. Budget 0.2 ns PCB skew (ASSUMPTION, not measured).
# Describe the NEXT DDR data transition: +0.8..+3.2 ns, rather than the
# preceding -3.2..-0.8 ns, so Vivado selects the correct hold relationship.
# Candidate PHY delay is 8*150 ps = 1.20 ns, 0.75 ns earlier than reference.
# Accordingly shift BOTH data bounds by +0.75 ns; do not widen the data eye.
# This candidate still requires positive routed setup AND hold timing.
create_clock -name pl_rgmii_rx -period 8.000 [get_ports pl_eth_rx_clk]
set task_rx_data [get_ports {pl_eth_rxd[*] pl_eth_rx_ctl}]
set_input_delay -clock pl_rgmii_rx -max 3.95 $task_rx_data
set_input_delay -clock pl_rgmii_rx -min 1.55 $task_rx_data
set_input_delay -clock pl_rgmii_rx -clock_fall -add_delay -max 3.95 $task_rx_data
set_input_delay -clock pl_rgmii_rx -clock_fall -add_delay -min 1.55 $task_rx_data
set_clock_uncertainty 0.100 [get_clocks pl_rgmii_rx]

# Forwarded TX_CLK is already shifted +90 degrees in the MAC clock PLL;
# PHY TX delay stays zero. Model the receiver's setup/hold plus PCB budget.
set task_tx_clock_pin [get_pins -hier -filter {NAME =~ U_pl_preview/network/mac/eth_mac_1g_rgmii_inst/rgmii_phy_if_inst/clk_oddr_inst/*oddr_inst/C}]
create_generated_clock -name pl_rgmii_tx -source $task_tx_clock_pin -divide_by 1 [get_ports pl_eth_tx_clk]
set task_tx_data [get_ports {pl_eth_txd[*] pl_eth_tx_ctl}]
set_output_delay -clock pl_rgmii_tx -max 1.2 $task_tx_data
set_output_delay -clock pl_rgmii_tx -min -1.2 $task_tx_data
set_output_delay -clock pl_rgmii_tx -clock_fall -add_delay -max 1.2 $task_tx_data
set_output_delay -clock pl_rgmii_tx -clock_fall -add_delay -min -1.2 $task_tx_data

# MDIO is deliberately slow (2 MHz), data synchronizes into GP100 and is
# sampled 120 ns after MDC rises. Only its first synchronizer stage is cut in
# pl_jpeg_preview_cdc.tcl. Table139 max PHY data delay is 20 ns.
set task_mdc_pin [get_pins -hier -filter {NAME == U_pl_preview/registers/management/mdc_reg/C}]
create_generated_clock -name pl_mdc -source $task_mdc_pin -divide_by 50 [get_ports pl_eth_mdc]
set_input_delay -clock pl_mdc -max 20.2 [get_ports pl_eth_mdio]
set_input_delay -clock pl_mdc -min -0.2 [get_ports pl_eth_mdio]
# MDC and MDIO are clock-enable outputs of GP100, not clocks driving the
# MDIO registers. Their enabled transitions share a GP edge at MDC falling;
# the PHY samples 25 GP cycles later. A conventional output-delay constraint
# would invent MDIO transitions on every GP edge, including MDC rising.
# Bound BOTH physical paths to 200 ns, with nonnegative minimum delay.
# Of the 250 ns half-period this leaves >=50 ns, exceeding the PHY 10 ns
# setup/hold + 0.2 ns board allowance. The MDIO simulation checks that driven
# data/output-enable cannot change while MDC is high. Idle command loading
# also precedes the first rising edge by a complete half-period.
set task_mdio_launch [get_cells -hier -filter {NAME =~ U_pl_preview/registers/management/bits_reg* || NAME =~ U_pl_preview/registers/management/position_reg* || NAME == U_pl_preview/registers/management/busy_reg || NAME == U_pl_preview/registers/management/read_mode_reg}]
set_max_delay -datapath_only 200.0 -from $task_mdio_launch -to [get_ports pl_eth_mdio]
set_min_delay 0.0 -from $task_mdio_launch -to [get_ports pl_eth_mdio]
set task_mdc_launch [get_cells U_pl_preview/registers/management/mdc_reg]
set_max_delay -datapath_only 200.0 -from $task_mdc_launch -to [get_ports pl_eth_mdc]
set_min_delay 0.0 -from $task_mdc_launch -to [get_ports pl_eth_mdc]
# PHY reset has no clocked receiver; external reset pulse is managed in ms.
set_false_path -to [get_ports pl_eth_reset_n]
