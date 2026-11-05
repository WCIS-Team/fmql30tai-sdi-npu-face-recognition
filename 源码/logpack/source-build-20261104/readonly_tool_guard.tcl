# Applied only inside this task's cloned Vivado hooks. A vendor speed-library
# replacement must never silently mutate the installed shared toolchain.
if {![llength [info commands ::wcis_original_file]]} {
    rename ::file ::wcis_original_file
    proc ::file {operation args} {
        if {$operation eq "copy" || $operation eq "rename"} {
            set destination [::wcis_original_file normalize [lindex $args end]]
            set destination [string tolower [string map {\\ /} $destination]]
            if {[string match {c:/xilinx/vivado/2018.3/*} $destination]} {
                # A byte-identical copy is safely replaced by a no-op. Never
                # write even an identical file into the installed toolchain.
                set source [lindex $args end-1]
                if {$operation eq "copy" && [::wcis_original_file isfile $source] &&
                    [::wcis_original_file isfile $destination]} {
                    set a [open $source rb];set av [read $a];close $a
                    set b [open $destination rb];set bv [read $b];close $b
                    if {$av eq $bv} {
                        puts "WCIS_TOOL_GUARD: identical installed file retained: $destination"
                        return
                    }
                }
                error "WCIS_TOOL_GUARD: installed Vivado database write blocked: $destination"
            }
        }
        return [uplevel 1 [list ::wcis_original_file $operation {*}$args]]
    }
}
