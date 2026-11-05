# Run with Procise after the bitstream is generated. Output is a review
# candidate; packaging success does not sign off timing or change the board.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set_device JFMQL30TAI676H
set task_bit [file join $task_root case fpai_demo_vivado.runs impl_1 ai7030_edif_top_disable_icap.bit]
if {![file exists $task_bit]} { error "Patched bitstream is missing: $task_bit" }
set task_src C:/Users/anxianji/Downloads/20260916/BOOT_Gen/BOOT_Gen
set task_out [file join $task_root outputs release-candidate]
file mkdir $task_out
foreach task_name {FSBL251210_ddr400_demo.out bl31.elf u-boot} {
    file copy -force [file join $task_src $task_name] [file join $task_out $task_name]
}
file copy -force $task_bit [file join $task_out ai7030_edif_top.bit]
# The supplied BIF contains absolute paths into Downloads. Reusing it would
# silently package the old vendor bit despite copying a new bit beside it.
set task_bif [open [file join $task_out wcis.bif] w]
puts $task_bif {//arch = fmql; split = false; format = BIN
the_ROM_image:
{
  [bootloader, destination_device = ps] FSBL251210_ddr400_demo.out
  [destination_device = pl] ai7030_edif_top.bit
  [destination_cpu = apu_0, destination_device = ps] bl31.elf
  [destination_cpu = apu_0, destination_device = ps] u-boot
  [fsbl_config] apu_x32
}}
close $task_bif
cd $task_out
if {[catch {create_boot_image wcis.bif BOOT.bin -fmql} task_result]} {
    puts "BOOT PACK ERROR: $task_result"
    exit 1
}
if {![file exists [file join $task_out BOOT.bin]]} { error "Procise did not produce BOOT.bin" }
if {[catch {dump_boot_image BOOT.bin boot-image-dump.txt -fmql} task_dump_result]} {
    puts "BOOT DUMP ERROR: $task_dump_result"
    exit 1
}
set task_status [open [file join $task_out procise-package-status.txt] w]
puts $task_status "Procise create_boot_image and dump_boot_image completed."
close $task_status
puts "WCIS BOOT PACK COMPLETE: [file join $task_out BOOT.bin]"
puts "Review timing and manifest before deployment."
exit 0
