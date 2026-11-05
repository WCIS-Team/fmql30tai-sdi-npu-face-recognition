# Release whole-design routing locks inherited from the old checkpoint.
# Keep only private DDR I/O paths. Canonicalize *all* hierarchy segments before
# inspecting leaves: inspecting one segment can hide fabric clock consumers.
if {![info exists task_out]} {error "Preview task_out is required"}
set preview_locs [get_cells -hier -filter {IS_LOC_FIXED}]
lock_design -unlock -level routing
if {[llength $preview_locs]} {set_property IS_LOC_FIXED true $preview_locs}
set preview_ddr [get_cells -hier -filter {NAME =~ U0_ps_ai_peripheral/mig_ddr3_u0/* && IS_PRIMITIVE}]
if {[llength $preview_ddr]<100} {error "DDR physical shell missing"}
set preview_physical {}
foreach c $preview_ddr {
    if {[regexp {^(IBUF.*|OBUF.*|ISERDES.*|OSERDES.*|IDELAYE2.*|ODELAYE2.*|PHASER.*|PHY_CONTROL|IN_FIFO|OUT_FIFO|IDDR|ODDR)$} [get_property REF_NAME $c]]} {lappend preview_physical $c}
}
set preview_ddr $preview_physical
set preview_roots [lsort -unique [get_nets -top_net_of_hierarchical_group -segments -of_objects [get_pins -of_objects $preview_ddr]]]
set preview_preserved {}
set preview_io_types {^(IBUF.*|OBUF.*|ISERDES.*|OSERDES.*|IDELAYE2.*|ODELAYE2.*|PHASER.*|PHY_CONTROL|IN_FIFO|OUT_FIFO|IDDR|ODDR)$}
foreach n $preview_roots {
    if {[get_property TYPE $n] in {GROUND POWER} || [get_property ROUTE $n] eq ""} {continue}
    set pins [get_pins -leaf -of_objects [get_nets -segments $n]]
    set leaves [get_cells -of_objects $pins]
    set dedicated [expr {[llength $leaves]>0}]
    foreach c $leaves {
        if {![string match {U0_ps_ai_peripheral/mig_ddr3_u0/*} $c] ||
            ![regexp $preview_io_types [get_property REF_NAME $c]]} {
            set dedicated 0
            break
        }
    }
    if {$dedicated} {lappend preview_preserved $n}
}
if {[llength $preview_preserved]<100} {error "Dedicated DDR routes unexpectedly missing"}
set_property IS_ROUTE_FIXED true $preview_preserved
set preview_all [get_nets -hier]
if {[llength $preview_all]<10000} {error "Whole-design routing collection unexpectedly small"}
set preview_fixed [filter $preview_all {IS_ROUTE_FIXED == 1}]
set preview_allowed [get_nets -segments $preview_preserved]
foreach n $preview_fixed {
    if {[lsearch -exact $preview_allowed $n]<0} {error "Unexpected fixed route remains: $n"}
}
set preview_clock_routes {}
foreach c [get_cells -hier -filter {REF_NAME =~ BUFG* || REF_NAME =~ BUFH*}] {
    foreach n [get_nets -of_objects [get_pins -of_objects $c -filter {DIRECTION == OUT}]] {
        if {[get_property IS_ROUTE_FIXED $n]} {error "Clock routing was incorrectly frozen: $n"}
        if {[get_property ROUTE $n] ne ""} {lappend preview_clock_routes $n}
    }
}
set f [open $task_out/ddr-preserved-net-names.txt w]
foreach n $preview_preserved {puts $f $n}
close $f
puts "PREVIEW_PRIVATE_DDR_ROUTES_FIXED=[llength $preview_preserved]; SHARED_CLOCK_ROUTES_EDITABLE"
# Clear shared clock routes, where new branches can conflict with old guided
# resources. Keep the remaining data-routing guide; clearing every hierarchy
# alias is both unnecessary and prohibitively slow in Vivado 2018.3.
set preview_clock_routes [lsort -unique $preview_clock_routes]
if {[llength $preview_clock_routes]} {
    route_design -unroute -nets $preview_clock_routes
} else {
    # A POST_PLACE_PHYSOPT guide may already have had its shared routes
    # cleared. Private DDR reuse and all fixed-route ownership were checked
    # above; route_design will still have to route and time every clock.
    puts "PREVIEW_SHARED_CLOCK_ROUTES_ALREADY_CLEAR; private DDR guide verified"
}
report_route_status -file $task_out/preview-clean-route-status.rpt
puts "PREVIEW_SHARED_CLOCK_ROUTES_CLEARED=[llength $preview_clock_routes]"
