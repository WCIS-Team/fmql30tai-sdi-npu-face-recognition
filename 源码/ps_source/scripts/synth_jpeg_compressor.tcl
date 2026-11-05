# Independent 1080p JPEG adapter synthesis / routing. No case/BOOT modification.
set root [file normalize [file join [file dirname [info script]] ..]]
set out D:/yzd/tmp/pl-jpeg-20261016/synthesis-adapter
file mkdir $out
create_project -in_memory -part xc7z030ffg676-2
foreach f [glob $root/rtl/vendor/mjpegzero/rtl/*.v] {read_verilog $f}
read_verilog $root/rtl/wcis_jpeg_compressor.v
synth_design -top wcis_jpeg_compressor -part xc7z030ffg676-2 -mode out_of_context
create_clock -name jpeg_clk -period 10.0 [get_ports clk]
report_utilization -file $out/synthesis-utilization.rpt
report_timing_summary -file $out/synthesis-timing.rpt
opt_design
place_design
route_design
report_utilization -file $out/routed-utilization.rpt
report_timing_summary -file $out/routed-timing.rpt
report_drc -file $out/drc.rpt
write_checkpoint -force $out/jpeg-adapter.dcp
puts "JPEG ADAPTER OOC ROUTING COMPLETE; no full-board or throughput proof"
close_project
