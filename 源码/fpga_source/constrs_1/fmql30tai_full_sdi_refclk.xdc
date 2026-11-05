# FMQL30TAI full board, Bank112 CLK1: SDI 148.5 MHz via J27.
# Apply after the vendor/Lite constraints. Do not change jumpers or I/O voltage.
# Hardware evidence and user-authorized scope: docs/sdi-bitstream-compare-20261020.md.
set_property PACKAGE_PIN U6 [get_ports FMC_HPC_GBTCLK0_M2C_C_P]
set_property PACKAGE_PIN U5 [get_ports FMC_HPC_GBTCLK0_M2C_C_N]

# Logical release ID from the accepted checkpoint; not a board-test certificate.
set_property BITSTREAM.CONFIG.USERID 32'h53201021 [current_design]
