# Structural check independent of timing exceptions: the former packetizer
# position -> checksum-D cone must terminate at the inserted storage/registers.
set payload_pos [get_cells -hier -filter {NAME =~ U_pl_preview/packetizer/position_reg* && IS_SEQUENTIAL}]
set payload_sum [get_cells -hier -filter {NAME =~ U_pl_preview/network/checksum_generator/checksum_reg_reg* && IS_SEQUENTIAL}]
set payload_pipe_regs [get_cells -hier -filter {NAME =~ U_pl_preview/payload_pipe/storage/* && IS_SEQUENTIAL}]
if {![llength $payload_pos] || ![llength $payload_sum] || [llength $payload_pipe_regs]<10} {
    error "Payload pipeline or structural-check endpoints missing"
}
set payload_endpoints [all_fanout -flat -endpoints_only -from [get_pins -of_objects $payload_pos -filter {DIRECTION == OUT}]]
foreach endpoint [get_pins -of_objects $payload_sum -filter {REF_PIN_NAME == D}] {
    if {[lsearch -exact $payload_endpoints $endpoint]>=0} {
        error "Unregistered packetizer-to-checksum path remains: $endpoint"
    }
}
puts "UDP_PAYLOAD_REGISTER_CUT_PASS: [llength $payload_pipe_regs] pipeline/storage registers, no original combinational cone to checksum D"
