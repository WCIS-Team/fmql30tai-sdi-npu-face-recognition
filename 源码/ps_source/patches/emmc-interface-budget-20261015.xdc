# Initial SDR bring-up only, Linux capped at 25 MHz. No DDR/HS200/HS400.
# Provisional conservative interface budget, NOT an AT70B32G characterization:
# 20 ns maximum return delay incl. card+board; >=0 ns minimum;
# 5 ns setup / 5 ns hold at card; 1 ns clock uncertainty.
# Card-specific AC data / PCB skew still required for production sign-off.
create_clock -name emmc_sdr25 -period 40.000 [get_pins U0_ps_ai_peripheral/ps_ai_wrapper_u0/ps_ai_i/processing_system7_0/inst/PS7_i/PS7_inst/EMIOSDIO1CLK]
set_clock_uncertainty 1.000 [get_clocks emmc_sdr25]
set_input_delay -clock emmc_sdr25 -max 20.000 [get_ports {emmc_cmd emmc_data[*]}]
set_input_delay -clock emmc_sdr25 -min 0.000 [get_ports {emmc_cmd emmc_data[*]}]
set_output_delay -clock emmc_sdr25 -max 5.000 [get_ports {emmc_cmd emmc_data[*]}]
set_output_delay -clock emmc_sdr25 -min -5.000 [get_ports {emmc_cmd emmc_data[*]}]
