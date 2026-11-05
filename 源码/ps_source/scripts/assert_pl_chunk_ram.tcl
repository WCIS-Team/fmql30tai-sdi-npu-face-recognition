# Storage topology check; independent of timing exceptions and interface data.
set chunk_rams [get_cells -hier -filter {NAME =~ U_pl_preview/packetizer/chunk_storage/* && (REF_NAME == RAMB18E1 || REF_NAME == RAMB36E1)}]
if {[llength $chunk_rams]!=1} {error "Packetizer chunk must use one synchronous block RAM"}
set chunk_counters [get_cells -hier -regexp {^U_pl_preview/packetizer/count_reg\[[0-9]+\]$}]
if {[llength $chunk_counters]<6} {error "Packetizer chunk counters missing"}
set chunk_max_fanout 0
foreach c $chunk_counters {
    set nets [get_nets -segments -of_objects [get_pins $c/Q]]
    set loads [get_pins -leaf -of_objects $nets -filter {DIRECTION == IN}]
    if {[llength $loads]>$chunk_max_fanout} {set chunk_max_fanout [llength $loads]}
    if {[llength $loads]>=64} {error "Packetizer counter still has excessive fanout: $c"}
}
puts "CHUNK_BLOCK_RAM_GATE_PASS: one [get_property REF_NAME $chunk_rams], packet-count maximum fanout=$chunk_max_fanout"
