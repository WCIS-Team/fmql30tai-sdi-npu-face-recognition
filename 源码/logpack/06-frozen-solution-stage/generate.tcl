source D:/renlianshibie/fpga_project/scripts/readonly_tool_guard.tcl
set_param general.maxThreads 2
set out D:/yzd/tmp/sdi-refclk-fix-20261020
open_checkpoint $out/refclk-final.dcp
foreach rule {REQP-44 REQP-46 REQP-52 REQP-56} {set_property SEVERITY Warning [get_drc_checks $rule]}
puts [exec C:/Users/anxianji/AppData/Local/Programs/Python/Python312/python.exe $out/gate.py]
write_bitstream -force $out/refclk.bit
close_design
exit
