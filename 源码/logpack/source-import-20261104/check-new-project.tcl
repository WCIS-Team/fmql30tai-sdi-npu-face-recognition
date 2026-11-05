create_project source_check ./new-project-3 -part xc7z030ffg676-2
source ./source-test/import_sources.tcl
report_ip_status -file ip-status.rpt
generate_target all [get_files *.bd]
foreach name $source_names {
    if {[file extension $name] eq ".xci"} {generate_target all [get_files [file join $source_root $name]]}
}
update_compile_order -fileset sources_1
set f [open imported-files.txt w]
foreach item [get_files -compile_order sources -used_in synthesis] {puts $f $item}
close $f
puts NEW_PROJECT_IMPORT_AND_GENERATION_PASSED
close_project

