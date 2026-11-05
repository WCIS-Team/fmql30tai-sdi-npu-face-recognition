# Read a checkpoint in memory; never modify the case or deployed clocks.
set task_root [file normalize [file join [file dirname [info script]] ..]]
open_checkpoint [file join $task_root case fpai_demo_vivado.runs synth_1 ai7030_edif_top.dcp]
set task_cells [get_cells -hier -filter {NAME =~ */AI_CORE_CLK/inst/*}]
set task_file [open [file join $task_root outputs core_clock_audit.txt] w]
foreach task_cell $task_cells {
    puts $task_file "$task_cell REF_NAME=[get_property REF_NAME $task_cell]"
}
set task_root_pin [get_pins U0_ps_ai_peripheral/ZGolo/u_AI_Mate_top/clkrst_wrapper_u0/AI_CORE_CLK/inst/clkout1_buf/O]
set task_fanout [all_fanout -flat -endpoints_only -from $task_root_pin]
puts $task_file "CORE clock fanout endpoints: [llength $task_fanout]"
foreach task_pin $task_fanout { puts $task_file "$task_pin" }
close $task_file
close_design
