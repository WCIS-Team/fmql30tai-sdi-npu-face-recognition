# Vivado 2018.3, logic-only proxy synthesis. No JFM hooks, case mutation,
# tool database changes, full-board build, bitstream or deployment.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_out D:/yzd/tmp/face-pl-20261015/synthesis
file mkdir $task_out
create_project -in_memory -part xc7z030ffg676-2
foreach task_file {wcis_affine_sampler.v wcis_pixel_read_axi.v wcis_face_preprocess.v} {
    read_verilog [file join $task_root rtl $task_file]
}
synth_design -top wcis_face_preprocess -part xc7z030ffg676-2 -mode out_of_context
create_clock -name backend_clk -period 10.0 [get_ports clk]
report_utilization -file [file join $task_out utilization.rpt]
report_timing_summary -file [file join $task_out timing.rpt]
report_drc -file [file join $task_out drc.rpt]
write_checkpoint -force [file join $task_out backend.dcp]
puts "FACE BACKEND LOGIC SYNTHESIS COMPLETE; no board implementation proof."
close_project
