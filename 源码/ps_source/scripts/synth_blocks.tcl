# Logic-only synthesis of new blocks; no JFM hooks, timing-library replacement,
# bitstream generation or board deployment. xc7z030 is the tutorial proxy part.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_out [file join $task_root outputs synthesis]
file mkdir $task_out
foreach task_top {wcis_frame_rate_gate wcis_stream_letterbox} {
    create_project -in_memory -part xc7z030ffg676-2
    read_verilog [file join $task_root rtl ${task_top}.v]
    synth_design -top $task_top -part xc7z030ffg676-2 -mode out_of_context
    if {$task_top eq "wcis_frame_rate_gate"} {
        create_clock -period 10.0 [get_ports cfg_clk]
        create_clock -period 5.0 [get_ports cam_clk]
        # Only asynchronous control-to-FIRST-synchronizer-stage paths are false.
        # Hold payload has a physical propagation bound; don't blanket-cut it.
        foreach task_name {request_sync_reg ack_sync_reg} {
            set task_first [get_cells -regexp ${task_name}\\\[0\\\]]
            set_false_path -to [get_pins -of_objects $task_first -filter {REF_PIN_NAME == D}]
        }
        set task_payload [get_cells -regexp {payload_hold_reg\[[01]\]}]
        set_max_delay -datapath_only 6.0 -from $task_payload -to [all_registers -clock [get_clocks cam_clk]]
    } else { create_clock -period 10.0 [get_ports clk] }
    report_utilization -file [file join $task_out ${task_top}_utilization.rpt]
    report_timing_summary -file [file join $task_out ${task_top}_timing.rpt]
    write_checkpoint -force [file join $task_out ${task_top}.dcp]
    close_project
}
puts "WCIS BLOCK SYNTHESIS PASSED; this is not full-board implementation or timing closure."
