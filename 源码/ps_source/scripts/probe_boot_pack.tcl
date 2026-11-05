# Local packaging probe using the preserved pre-fix bit. Never deploy this file.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_out [file join $task_root outputs boot-pack-probe]
file mkdir $task_out
set task_src C:/Users/anxianji/Downloads/20260916/BOOT_Gen/BOOT_Gen
foreach task_name {FSBL251210_ddr400_demo.out bl31.elf u-boot} {
    file copy -force [file join $task_src $task_name] [file join $task_out $task_name]
}
file copy -force [file join $task_root outputs build-before-fix ai7030_edif_top_disable_icap.bit] [file join $task_out ai7030_edif_top.bit]
file copy -force [file join $task_src 7030ai_psin.bif] [file join $task_out probe.bif]
cd $task_out
if {[catch {create_boot_image probe.bif probe-DO-NOT-DEPLOY.bin -fmql} task_result]} {
    puts "BOOT PACK PROBE ERROR: $task_result"
    exit 1
}
puts "BOOT PACK PROBE RESULT: $task_result"
puts "File exists: [file exists [file join $task_out probe-DO-NOT-DEPLOY.bin]]"
exit
