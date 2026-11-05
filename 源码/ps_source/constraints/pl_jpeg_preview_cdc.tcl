# Apply after synthesis. Source the unchanged upstream MAC/FIFO constraints,
# then constrain only synchronizers and held mailboxes inside the new preview.
# No clock-group-wide false paths and no whole data bus timing exclusions.
set task_preview_root [file normalize [file join [file dirname [info script]] ..]]
foreach task_name {axis_async_fifo sync_reset} {
    source $task_preview_root/rtl/vendor/verilog_ethernet/axis/syn/vivado/$task_name.tcl
}
proc wcis_constrain_preview {prefix} {
    # Single-bit retained status: only the first data stage is asynchronous.
    # Keep the second stage and its locally synchronized reset release timed.
    set task_local_status {}
    foreach inst [get_cells -hier -filter {REF_NAME =~ wcis_status_sync* || ORIG_REF_NAME =~ wcis_status_sync*}] {
        if {$prefix ne "" && $inst ne $prefix && ![string match "$prefix/*" $inst]} {continue}
        # The RTL vector is named status_reg, so Vivado 2018.3 appends
        # another _reg to each synthesized flip-flop name.
        set stages [get_cells -hier -regexp [format {^%s/status_reg_reg\[[01]\]$} $inst]]
        set first [get_cells -hier -regexp [format {^%s/status_reg_reg\[0\]$} $inst]]
        if {[llength $stages]!=2 || [llength $first]!=1} {error "Status synchronizer lost a data stage: $inst"}
        lappend task_local_status {*}$stages
        set_false_path -to [get_pins -of_objects $first -filter {REF_PIN_NAME == D}]
        puts "STATUS_SYNCHRONIZER_GATE_PASS: $inst stages=2 first_D_only"
    }
    foreach inst [get_cells -hier -filter {REF_NAME =~ wcis_cdc_mailbox* || ORIG_REF_NAME =~ wcis_cdc_mailbox*}] {
        if {$prefix ne "" && ![string match "$prefix/*" $inst]} {continue}
        set held [get_cells -hier -regexp "^$inst/payload_hold_reg.*"]
        set capture [get_cells -hier -regexp "^$inst/m_data_reg.*"]
        if {![llength $held] || ![llength $capture]} {error "Missing held preview mailbox: $inst"}
        # Both new data mailboxes hold their payload until a round-trip ACK.
        # 8 ns bounds data arrival before the synchronized request is consumed.
        set_max_delay -datapath_only 8.0 -from $held -to $capture
        set_bus_skew 8.0 -from $held -to $capture
        set first [get_cells -hier -regexp "^$inst/(request_sync|ack_sync)_reg\\\[0\\\]"]
        if {[llength $first]} {set_false_path -to [get_pins -of_objects $first -filter {REF_PIN_NAME == D}]}
    }
    foreach cell [get_cells -hier -regexp {.*(idle_sync|enable_sync|enable_to_network|lock_status_sync|mdio_sync)_reg\[0\]}] {
        if {$prefix ne "" && ![string match "$prefix/*" $cell]} {continue}
        set_false_path -to [get_pins -of_objects $cell -filter {REF_PIN_NAME == D}]
    }
    foreach cell [get_cells -hier -filter {ASYNC_REG == TRUE && REF_NAME =~ FD*}] {
        if {$prefix ne "" && ![string match "$prefix/*" $cell]} {continue}
        if {[lsearch -exact $task_local_status $cell]>=0} {continue}
        # Asynchronous reset assertion; each destination synchronizes release.
        set reset_pins [get_pins -quiet -of_objects $cell -filter {REF_PIN_NAME == PRE || REF_PIN_NAME == CLR}]
        if {[llength $reset_pins]} {set_false_path -to $reset_pins}
    }
}
