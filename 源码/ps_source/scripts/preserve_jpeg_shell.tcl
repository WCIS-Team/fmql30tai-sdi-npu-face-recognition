# Called before placement. Guide unchanged logic from the verified reference,
# but fix only DDR physical primitives and clock buffers. Free controller LUTs
# and registers so the placer can make room for the added JPEG datapath.
set task_ref D:/yzd/tmp/face-emmc-store-20261015/case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top_routed.dcp
set task_shell [get_cells U0_ps_ai_peripheral]
if {[llength $task_shell]!=1} {error "Original DDR/NPU shell missing"}
read_checkpoint -incremental -reuse_objects $task_shell $task_ref
report_incremental_reuse -cells $task_shell -hierarchical -hierarchical_depth 3 -file D:/yzd/tmp/pl-jpeg-board-20261016/shell-reuse.rpt
set task_fixed {}
foreach task_cell [get_cells -hier -filter {IS_PRIMITIVE}] {
    set task_name [get_property NAME $task_cell]
    set task_refname [get_property REF_NAME $task_cell]
    set task_clock [regexp {^(BUFG.*|BUFH.*|MMCM.*|PLL.*)$} $task_refname]
    set task_io [expr {[string match {U0_ps_ai_peripheral/mig_ddr3_u0/*} $task_name] &&
        [regexp {^(IBUF.*|OBUF.*|ISERDES.*|OSERDES.*|IDELAYE2.*|ODELAYE2.*|PHASER.*|PHY_CONTROL|IN_FIFO|OUT_FIFO|IDDR|ODDR)$} $task_refname]}]
    if {($task_io || $task_clock) && [get_property LOC $task_cell] ne ""} {lappend task_fixed $task_cell}
}
if {[llength $task_fixed]<100} {error "Original DDR physical placement missing"}
set_property IS_LOC_FIXED true $task_fixed
# Do not add BEL constraints to the vendor's differential I/O mapping. The
# compatible proxy part rejects the supplied P/N mapping when BEL is fixed;
# preserve the reference LOC and the unchanged board PACKAGE_PIN constraints.
puts "DDR_IO_AND_CLOCK_LOCATIONS_FIXED=[llength $task_fixed]; controller and NPU fabric may move"
# Allow the standard placer to re-create IDELAYCTRL replicas.
set task_idcs [get_cells -hier -filter {REF_NAME == IDELAYCTRL}]
if {![llength $task_idcs]} {error "DDR calibration controller missing"}
set_property DONT_TOUCH false $task_idcs
set task_controls [get_nets -segments -of_objects [get_pins -of_objects $task_idcs -filter {REF_PIN_NAME == RDY || REF_PIN_NAME == RST || REF_PIN_NAME == REFCLK}]]
if {![llength $task_controls]} {error "DDR calibration control nets missing"}
set_property DONT_TOUCH false $task_controls
set_property MARK_DEBUG false $task_controls
set_property IS_ROUTE_FIXED false $task_controls
set_property FIXED_ROUTE {} $task_controls
puts "CALIBRATION_CONTROLS_UNLOCKED=$task_controls"
puts "ORIGINAL LOGIC GUIDED; ONLY DDR PHYSICAL INTERFACE AND CLOCK BUFFER LOCATIONS FIXED"
