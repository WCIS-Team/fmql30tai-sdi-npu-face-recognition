# Run in Vivado 2018.3: source D:/renlianshibie/fpga_project/scripts/prepare_case.tcl
# This configures the copied project only. It does not replace tool timing files.
set task_root [file normalize [file join [file dirname [info script]] ..]]
set task_case [file join $task_root case]
if {[info exists ::env(WCIS_CASE_DIR)]} {set task_case [file normalize $::env(WCIS_CASE_DIR)]}
if {[llength [get_projects -quiet]] == 0} {
    open_project [file join $task_case fpai_demo_vivado.xpr]
}
if {[file normalize [get_property DIRECTORY [current_project]]] ne $task_case} {
    error "Open only the copied project under $task_case"
}
if {[get_property PART [current_project]] ne "xc7z030ffg676-2"} {
    error "Unexpected part; tutorial requires xc7z030ffg676-2"
}
set_property ip_repo_paths [list [file join $task_case "PS_AI IP"]] [current_project]
update_ip_catalog
config_ip_cache -disable_cache
set_property ip_output_repo [file join $task_case ip_cache] [current_project]
# This project targets the full FMQL30TAI board. Override the supplied Lite
# reference-clock balls last, including when building a separately staged case.
set task_refclk [file join $task_root constraints fmql30tai_full_sdi_refclk.xdc]
if {[llength [get_files -quiet $task_refclk]] == 0} {
    add_files -fileset constrs_1 -norecurse $task_refclk
}
set_property PROCESSING_ORDER LATE [get_files $task_refclk]
set task_extra [file join $task_case rtl wcis wcis_frame_rate_gate.v]
if {[llength [get_files -quiet $task_extra]] == 0} { add_files -norecurse $task_extra }
set task_diag [file join $task_case rtl wcis wcis_sdi_monitor.v]
if {[llength [get_files -quiet $task_diag]] == 0} { add_files -norecurse $task_diag }
foreach task_name {wcis_face_customop.v wcis_cdc_mailbox.v wcis_face_preprocess.v wcis_affine_sampler.v wcis_pixel_read_axi.v} {
    set task_face [file join $task_case rtl wcis $task_name]
    if {[llength [get_files -quiet $task_face]] == 0} {add_files -norecurse $task_face}
}
set_property top ai7030_edif_top [get_filesets sources_1]
# These two stale hook files do not exist in the vendor archive. Remove only
# their project references; the six supplied JFM hooks are installed below.
foreach task_missing {implementation_place_pre.tcl implementation_place_post.tcl} {
    set task_files [get_files -quiet *$task_missing]
    if {[llength $task_files]} { remove_files $task_files }
}
if {![info exists ::env(JFM_PATH)]} { error "Set process/user JFM_PATH to the JFM_Kits directory first" }
if {[regexp {[^\x00-\x7f]|\s} $::env(JFM_PATH)]} {
    error "Tutorial requires an ASCII JFM_PATH without spaces"
}
set task_patch [file join $::env(JFM_PATH) ip_patch run.tcl]
if {![file exists $task_patch]} { error "JFM run.tcl not found at $task_patch" }
source $task_patch
add_hook_tcl_to_prj
update_compile_order -fileset sources_1
puts "WCIS copied project prepared; reset uses bypass, rate CSR offsets are 0xB8/0xBC."
puts "30TAI timing-library installation and physical board constraints still require verification."
