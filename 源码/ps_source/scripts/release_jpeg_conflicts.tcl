# Whole-shell routing preservation caused new-pin conflicts. Use the native
# routing-only unlock, retaining original cell locations/logical preservation.
# Fix only already routed nonconstant nets between dedicated DDR I/O cells.
# FIFO-to-fabric and shared clock fanout use regular routing. The original
# calibration control nets remain editable for the standard placer replicas.
set task_shell [get_cells U0_ps_ai_peripheral]
if {[llength $task_shell]!=1} {error "Original peripheral shell missing"}
set task_fresh_routing [expr {[info exists ::env(WCIS_JPEG_FRESH_ROUTING)] && $::env(WCIS_JPEG_FRESH_ROUTING) eq "1"}]
if {$task_fresh_routing} {
    set_param general.maxThreads 4
    set task_location_locks [get_cells -hier -filter {IS_LOC_FIXED}]
    lock_design -unlock -level routing
    if {[llength $task_location_locks]} {set_property IS_LOC_FIXED true $task_location_locks}
    puts "JPEG_GLOBAL_ROUTING_UNLOCKED; original fixed cell locations restored"
} else {
    lock_design -unlock -level routing $task_shell
    puts "JPEG_SHELL_ROUTING_UNLOCKED; cell locations retained"
}
flush stdout
set task_phy {}
foreach task_cell [get_cells -hier -filter {NAME =~ U0_ps_ai_peripheral/mig_ddr3_u0/* && IS_PRIMITIVE}] {
    set task_ref [get_property REF_NAME $task_cell]
    if {[regexp {^(IBUF.*|OBUF.*|ISERDES.*|OSERDES.*|IDELAYE2.*|ODELAYE2.*|PHASER.*|PHY_CONTROL|IN_FIFO|OUT_FIFO|MMCM.*|PLL.*|BUF.*|IDDR|ODDR)$} $task_ref]} {
        lappend task_phy $task_cell
    }
}
if {![llength $task_phy]} {error "DDR physical interface cells missing"}
set task_nets [get_nets -top_net_of_hierarchical_group -segments -of_objects [get_pins -of_objects $task_phy]]
set task_idcs [get_cells -hier -filter {REF_NAME == IDELAYCTRL}]
set task_calibration [get_property NAME [get_nets -top_net_of_hierarchical_group -segments -of_objects [get_pins -of_objects $task_idcs]]]
set task_preserved {}
foreach task_net $task_nets {
    if {[get_property TYPE $task_net] in {GROUND POWER}} {continue}
    if {[lsearch -exact $task_calibration [get_property NAME $task_net]]>=0} {continue}
    if {[get_property ROUTE $task_net] eq ""} {continue}
    set task_dedicated 1
    foreach task_cell [get_cells -of_objects [get_pins -leaf -of_objects $task_net]] {
        set task_ref [get_property REF_NAME $task_cell]
        if {![regexp {^(IBUF.*|OBUF.*|ISERDES.*|OSERDES.*|IDELAYE2.*|ODELAYE2.*|PHASER.*|PHY_CONTROL|IN_FIFO|OUT_FIFO|MMCM.*|PLL.*|BUF.*|IDDR|ODDR)$} $task_ref]} {
            set task_dedicated 0
            break
        }
    }
    if {!$task_dedicated} {continue}
    lappend task_preserved $task_net
}
set task_preserved [lsort -unique $task_preserved]
if {[llength $task_preserved]<100} {error "Too few original DDR physical routes available"}
set_property IS_ROUTE_FIXED true $task_preserved
set task_file [open D:/yzd/tmp/pl-jpeg-board-20261016/ddr-preserved-net-names.txt w]
foreach task_net $task_preserved {puts $task_file [get_property NAME $task_net]}
close $task_file
puts "JPEG_DDR_PHY_ROUTES_PRESERVED=[llength $task_preserved]"
flush stdout
if {$task_fresh_routing} {
    # Remove old ordinary routes in one native operation. Canonicalize hierarchy
    # aliases first, so a shared constant tree is not edited thousands of times.
    set task_roots [lsort -unique [get_nets -top_net_of_hierarchical_group -segments [get_nets -hier]]]
    set task_ordinary [filter $task_roots {IS_ROUTE_FIXED == 0}]
    puts "JPEG_ORDINARY_ROUTES_TO_CLEAR=[llength $task_ordinary]"
    flush stdout
    route_design -unroute -nets $task_ordinary
    report_route_status -file D:/yzd/tmp/pl-jpeg-board-20261016/clean-routing-status.rpt
    write_checkpoint -force D:/yzd/tmp/pl-jpeg-board-20261016/jpeg-clean-routing.dcp
    puts "JPEG_ORDINARY_ROUTES_CLEARED; dedicated DDR routes retained"
    flush stdout
}
