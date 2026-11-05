set task_out D:/yzd/tmp/sdi-refclk-fix-20261020
set_device JFMQL30TAI676H
increment_bit_cfg_v3 $task_out/refclk.bit $task_out/refclk-disable-icap.bit -disable_icap
set dst $task_out/boot-candidate
file mkdir $dst
set src D:/yzd/tmp/pl-jpeg-board-20261016/boot-candidate
foreach name {FSBL251210_ddr400_demo.out bl31.elf u-boot} {file copy -force $src/$name $dst/$name}
file copy -force $task_out/refclk-disable-icap.bit $dst/ai7030_edif_top.bit
set f [open $dst/wcis.bif w]
puts $f {//arch = fmql; split = false; format = BIN
the_ROM_image:
{
 [bootloader, destination_device = ps] FSBL251210_ddr400_demo.out
 [destination_device = pl] ai7030_edif_top.bit
 [destination_cpu = apu_0, destination_device = ps] bl31.elf
 [destination_cpu = apu_0, destination_device = ps] u-boot
 [fsbl_config] apu_x32
}}
close $f
cd $dst
create_boot_image wcis.bif BOOT.bin -fmql
dump_boot_image BOOT.bin boot-image-dump.txt -fmql
set f [open $task_out/package_candidate.done w];puts $f "complete";close $f
exit 0

