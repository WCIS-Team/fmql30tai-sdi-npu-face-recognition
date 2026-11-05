# Run with Procise after restore_implemented.tcl and supplying boot/ components.
# Procise GUI source does not reliably update info script for nested scripts.
if {[info exists ::wcis_source_root]} {
    set source_root [file normalize $::wcis_source_root]
} else {
    set source_root [file normalize [file dirname [info script]]]
}
set output [file normalize [file join $source_root .. build-restored]]
foreach name {FSBL251210_ddr400_demo.out bl31.elf u-boot wcis.bif} {
    if {![file isfile [file join $source_root boot $name]]} {error "Missing boot input: $name"}
}
if {![file isfile [file join $output refclk.bit]]} {error "Run restore_implemented.tcl in Vivado first"}
set_device JFMQL30TAI676H
increment_bit_cfg_v3 [file join $output refclk.bit] [file join $output ai7030_edif_top.bit] -disable_icap
foreach name {FSBL251210_ddr400_demo.out bl31.elf u-boot wcis.bif} {
    file copy -force [file join $source_root boot $name] [file join $output $name]
}
cd $output
create_boot_image wcis.bif BOOT.bin -fmql
dump_boot_image BOOT.bin boot-image-dump.txt -fmql
puts "Restored BOOT: [file join $output BOOT.bin]"
