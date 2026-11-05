#####################  hdmi ############################
set_property PACKAGE_PIN AC17 [get_ports HDMI_CLK_P]
set_property PACKAGE_PIN AA15 [get_ports {HDMI_TX_P[0]}]
set_property PACKAGE_PIN Y16 [get_ports {HDMI_TX_P[1]}]
set_property PACKAGE_PIN W16 [get_ports {HDMI_TX_P[2]}]
set_property IOSTANDARD TMDS_33 [get_ports HDMI_CLK_P]
set_property IOSTANDARD TMDS_33 [get_ports {HDMI_TX_P[*]}] ; ####################  hdmi ############################

set_property PACKAGE_PIN F8 [get_ports sys_rst]
set_property IOSTANDARD LVCMOS15 [get_ports sys_rst]
set_property PACKAGE_PIN E7 [get_ports rx_gtx_full_reset]
set_property IOSTANDARD LVCMOS15 [get_ports rx_gtx_full_reset]

#LED1, BANK13
set_property IOSTANDARD LVCMOS15 [get_ports {led[0]}]
set_property PACKAGE_PIN J1 [get_ports {led[0]}]
#LED2, BANK13
set_property IOSTANDARD LVCMOS15 [get_ports {led[1]}]
set_property PACKAGE_PIN M6 [get_ports {led[1]}]

create_clock -period 5.000 [get_ports sys_clk_p]
set_property IOSTANDARD DIFF_SSTL15 [get_ports sys_clk_p]
set_property IOSTANDARD DIFF_SSTL15 [get_ports sys_clk_n]
set_property PACKAGE_PIN C8 [get_ports sys_clk_p]
set_property PACKAGE_PIN C7 [get_ports sys_clk_n]

set_property PACKAGE_PIN AB3 [get_ports FMC_HPC_DP0_M2C_N]
set_property PACKAGE_PIN AB4 [get_ports FMC_HPC_DP0_M2C_P]
create_clock -period 6.734 [get_ports FMC_HPC_GBTCLK0_M2C_C_P]
##set_property PACKAGE_PIN U6 [get_ports FMC_HPC_GBTCLK0_M2C_C_P]  ## WUJING BOARD
##set_property PACKAGE_PIN U5 [get_ports FMC_HPC_GBTCLK0_M2C_C_N]
set_property PACKAGE_PIN R6 [get_ports FMC_HPC_GBTCLK0_M2C_C_P] ; # WUJING LITE BOARD
set_property PACKAGE_PIN R5 [get_ports FMC_HPC_GBTCLK0_M2C_C_N]

#pjtag:7030 Demo
set_property PACKAGE_PIN AD16 [get_ports PJTAG_TDO]
set_property PACKAGE_PIN AB14 [get_ports PJTAG_TMS]
set_property PACKAGE_PIN AB15 [get_ports PJTAG_TCK]
set_property PACKAGE_PIN AD15 [get_ports PJTAG_TDI]
set_property IOSTANDARD LVCMOS33 [get_ports PJTAG_TCK]
set_property IOSTANDARD LVCMOS33 [get_ports PJTAG_TMS]
set_property IOSTANDARD LVCMOS33 [get_ports PJTAG_TDI]
set_property IOSTANDARD LVCMOS33 [get_ports PJTAG_TDO]

set_property PULLUP true [get_ports PJTAG_TDO]
create_clock -period 20.000 -name jtag_clk -waveform {0.000 10.000} [get_ports PJTAG_TCK]

########################
#set_property SEVERITY {Warning} [get_drc_checks {REQP-44}]
#set_property SEVERITY {Warning} [get_drc_checks {REQP-46}]
#set_property SEVERITY {Warning} [get_drc_checks {REQP-52}]
#set_property SEVERITY {Warning} [get_drc_checks {REQP-56}]


# SDI2 passive snapshot CDC. Only asynchronous control FIRST stages are cut.
# Bundled snapshot data must settle within one 50 MHz CFG period; ACK crosses
# two stages and is consumed on a later edge. These bounds need routed proof.
set task_sdi_first [get_cells -hier -regexp {.*sdi_monitor/(request_sync|ack_sync|ref_sync|gt_sync)_reg\[0\]}]
set_false_path -to [get_pins -of_objects $task_sdi_first -filter {REF_PIN_NAME == D}]
set task_sdi_hold [get_cells -hier -regexp {.*sdi_monitor/payload_hold_reg\[[0-9]+\]}]
set task_sdi_snap [get_cells -hier -regexp {.*sdi_monitor/snapshot_reg\[[0-9]+\]}]
set_max_delay -datapath_only 20.0 -from $task_sdi_hold -to $task_sdi_snap
set_bus_skew 20.0 -from $task_sdi_hold -to $task_sdi_snap

# Face backend mailboxes: only the first toggle synchronizer is asynchronous.
# GP->HP request payload has >=2 HP cycles to settle before capture; HP->GP
# response has >=2 GP cycles. Never blanket-cut their bundled data paths.

# FACE read_request
set task_sync [get_cells -hier -regexp {.*U_adder_top/face/read_request/(request_sync|ack_sync)_reg\[0\]}]
set_false_path -to [get_pins -of_objects $task_sync -filter {REF_PIN_NAME == D}]
set task_hold [get_cells -hier -regexp {.*U_adder_top/face/read_request/payload_hold_reg\[[0-9]+\]}]
set task_capture [get_cells -hier -regexp {.*U_adder_top/face/read_request/m_data_reg\[[0-9]+\]}]
set_max_delay -datapath_only 8.0 -from $task_hold -to $task_capture
set_bus_skew 8.0 -from $task_hold -to $task_capture

# FACE write_request
set task_sync [get_cells -hier -regexp {.*U_adder_top/face/write_request/(request_sync|ack_sync)_reg\[0\]}]
set_false_path -to [get_pins -of_objects $task_sync -filter {REF_PIN_NAME == D}]
set task_hold [get_cells -hier -regexp {.*U_adder_top/face/write_request/payload_hold_reg\[[0-9]+\]}]
set task_capture [get_cells -hier -regexp {.*U_adder_top/face/write_request/m_data_reg\[[0-9]+\]}]
set_max_delay -datapath_only 8.0 -from $task_hold -to $task_capture
set_bus_skew 8.0 -from $task_hold -to $task_capture

# FACE read_response
set task_sync [get_cells -hier -regexp {.*U_adder_top/face/read_response/(request_sync|ack_sync)_reg\[0\]}]
set_false_path -to [get_pins -of_objects $task_sync -filter {REF_PIN_NAME == D}]
set task_hold [get_cells -hier -regexp {.*U_adder_top/face/read_response/payload_hold_reg\[[0-9]+\]}]
set task_capture [get_cells -hier -regexp {.*U_adder_top/face/read_response/m_data_reg\[[0-9]+\]}]
set_max_delay -datapath_only 20.0 -from $task_hold -to $task_capture
set_bus_skew 20.0 -from $task_hold -to $task_capture

# JPEG read_request bundled-data mailbox
set task_sync [get_cells -hier -regexp {.*U_adder_top/jpeg/read_request/(request_sync|ack_sync)_reg\[0\]}]
set_false_path -to [get_pins -of_objects $task_sync -filter {REF_PIN_NAME == D}]
set task_hold [get_cells -hier -regexp {.*U_adder_top/jpeg/read_request/payload_hold_reg\[[0-9]+\]}]
set task_capture [get_cells -hier -regexp {.*U_adder_top/jpeg/read_request/m_data_reg\[[0-9]+\]}]
set_max_delay -datapath_only 8.0 -from $task_hold -to $task_capture
set_bus_skew 8.0 -from $task_hold -to $task_capture

# JPEG write_request bundled-data mailbox
set task_sync [get_cells -hier -regexp {.*U_adder_top/jpeg/write_request/(request_sync|ack_sync)_reg\[0\]}]
set_false_path -to [get_pins -of_objects $task_sync -filter {REF_PIN_NAME == D}]
set task_hold [get_cells -hier -regexp {.*U_adder_top/jpeg/write_request/payload_hold_reg\[[0-9]+\]}]
set task_capture [get_cells -hier -regexp {.*U_adder_top/jpeg/write_request/m_data_reg\[[0-9]+\]}]
set_max_delay -datapath_only 8.0 -from $task_hold -to $task_capture
set_bus_skew 8.0 -from $task_hold -to $task_capture

# JPEG read_response bundled-data mailbox
set task_sync [get_cells -hier -regexp {.*U_adder_top/jpeg/read_response/(request_sync|ack_sync)_reg\[0\]}]
set_false_path -to [get_pins -of_objects $task_sync -filter {REF_PIN_NAME == D}]
set task_hold [get_cells -hier -regexp {.*U_adder_top/jpeg/read_response/payload_hold_reg\[[0-9]+\]}]
set task_capture [get_cells -hier -regexp {.*U_adder_top/jpeg/read_response/m_data_reg\[[0-9]+\]}]
set_max_delay -datapath_only 20.0 -from $task_hold -to $task_capture
set_bus_skew 20.0 -from $task_hold -to $task_capture
