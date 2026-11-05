# Call on the elaborated/synthesized full design, outside an XDC file.
set task_sdi_first [get_cells -hier -regexp {.*sdi_monitor/(request_sync|ack_sync|ref_sync|gt_sync)_reg\[0\]}]
set task_sdi_hold [get_cells -hier -regexp {.*sdi_monitor/payload_hold_reg\[[0-9]+\]}]
set task_sdi_snap [get_cells -hier -regexp {.*sdi_monitor/snapshot_reg\[[0-9]+\]}]
if {[llength $task_sdi_first] != 4} {error "Expected four SDI2 first-stage synchronizers"}
if {![llength $task_sdi_hold] || ![llength $task_sdi_snap]} {error "Missing SDI2 snapshot payload registers"}
puts "SDI2 full-design CDC constraint endpoints found"
