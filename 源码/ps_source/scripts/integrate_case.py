"""Reproducible minimal patches, applied only to the staged vendor case."""
from pathlib import Path
import hashlib
import json
import shutil
import difflib

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"C:\Users\anxianji\Downloads\20260916\fpai_demo_fpga\fpai_demo_fpga")
CASE = ROOT / "case"

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f"Patch anchor is ambiguous or missing: {old[:100]!r}")
    return text.replace(old, new, 1)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_vendor(path):
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return raw.decode("gb18030").replace("\r\n", "\n")

def main():
    ctrl_rel = Path("rtl/display/frame_ctrl.v")
    trans_rel = Path("rtl/display/frame_trans.sv")
    xdc_rel = Path("constrs_1/impl_constraints.xdc")
    clock_xdc_rel = Path("constrs_1/ai7030.xdc")
    resize_rel = Path("rtl/display/cmos_resize_24bit.v")
    vtc_rel = Path("rtl/display/vtc.v")
    rx_rel = Path("rtl/sdi/rx_sdi.v")
    top_rel = Path("rtl/ai7030_edif_top.v")
    peripheral_rel = Path("rtl/ps_ai_peripheral.sv")
    ctrl = read_vendor(SOURCE / ctrl_rel)
    ctrl = replace_once(ctrl, "    output reg            soft_rst     ",
        "    output wire           rate_cfg_valid,\n"
        "    output wire [1:0]     rate_cfg_word,\n"
        "    input wire            rate_cfg_ready,\n"
        "    input wire [1:0]      rate_cfg_applied,\n"
        "    output reg            soft_rst     ")
    ctrl = replace_once(ctrl, "    assign slv_reg_wren = ", """    // WCIS extension; no existing register offsets are changed.
    // 0xB8 [1:0] = requested {enable,active}; [2] = rejected busy write.
    // 0xBC [1:0] = applied {enable,active}; [3] = pending (not yet applied).
    reg [1:0] rate_requested;
    reg rate_rejected;
    assign rate_cfg_valid = slv_reg_wren && (S_AXI_AWADDR == 9'h0B8) && S_AXI_WSTRB[0];
    assign rate_cfg_word = S_AXI_WDATA[1:0];
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            rate_requested <= 2'b01;
            rate_rejected <= 1'b0;
        end else if (rate_cfg_valid) begin
            if (rate_cfg_ready) begin
                rate_requested <= rate_cfg_word;
                rate_rejected <= 1'b0;
            end else rate_rejected <= 1'b1;
        end
    end

    assign slv_reg_wren = """)
    ctrl = replace_once(ctrl, "                default : S_AXI_RDATA <= 32'h0000_0000;",
        "                9'h0B8 : S_AXI_RDATA <= {29'd0,rate_rejected,rate_requested};\n"
        "                9'h0BC : S_AXI_RDATA <= {28'd0,!rate_cfg_ready,1'b0,rate_cfg_applied};\n"
        "                9'h0C0 : S_AXI_RDATA <= 32'h57434953; // WCIS extension ID\n"
        "                default : S_AXI_RDATA <= 32'h0000_0000;")
    # Independent read-only SDI2 diagnostics; never reuse rate-gate 0xB8..0xC0.
    ctrl = replace_once(ctrl, "    output reg            soft_rst     ",
        "    input wire [415:0]    sdi_diag_words,\n    output reg            soft_rst     ")
    diag_reads = "".join(
        f"                9'h{0x100+4*i:03X} : S_AXI_RDATA <= sdi_diag_words[{32*i} +: 32];\n"
        for i in range(13))
    ctrl = replace_once(ctrl, "                default : S_AXI_RDATA <= 32'h0000_0000;",
        diag_reads + "                default : S_AXI_RDATA <= 32'h0000_0000;")

    trans = read_vendor(SOURCE / trans_rel)
    anchor = "    //assign dvp_vsync_in = cam_vs  ;"
    trans = replace_once(trans, anchor, """    // Select before frame_ctrl so PS capture and NPU see the same admitted frames.
    // Source fps is an assumption/configuration, not measured automatically here.
    wire rate_cfg_valid, rate_cfg_ready;
    wire [1:0] rate_cfg_word, rate_cfg_applied;
    wire rate_vsync, rate_href;
    wire [23:0] rate_data;
    (* mark_debug = "true" *) wire [31:0] rate_seen, rate_selected, rate_dropped;
    wcis_frame_rate_gate #(.SOURCE_FPS(30), .ACTIVE_FPS(20), .STANDBY_FPS(1)) rate_gate (
        .cfg_clk(S_AXI_ACLK), .cam_clk(cam_clk),
        .reset(reset_cam_clk | !S_AXI_ARESETN),
        .cfg_valid(rate_cfg_valid), .cfg_word(rate_cfg_word),
        .cfg_ready(rate_cfg_ready), .cfg_applied(rate_cfg_applied),
        .s_vsync(dvp_vsync_in), .s_href(dvp_href_in), .s_data(dvp_db_in),
        .m_vsync(rate_vsync), .m_href(rate_href), .m_data(rate_data),
        .seen_frames(rate_seen), .selected_frames(rate_selected), .dropped_frames(rate_dropped));

""" + anchor)
    for old, new in ((".dvp_vsync_in         (dvp_vsync_in        )", ".dvp_vsync_in         (rate_vsync          )"),
                     (".dvp_href_in          (dvp_href_in         )", ".dvp_href_in          (rate_href           )"),
                     (".dvp_db_in            (dvp_db_in           )", ".dvp_db_in            (rate_data           )")):
        trans = replace_once(trans, old, new)
    trans = replace_once(trans, "        .soft_rst             (soft_rst            )",
        "        .rate_cfg_valid       (rate_cfg_valid      ),\n"
        "        .rate_cfg_word        (rate_cfg_word       ),\n"
        "        .rate_cfg_ready       (rate_cfg_ready      ),\n"
        "        .rate_cfg_applied     (rate_cfg_applied    ),\n"
        "        .soft_rst             (soft_rst            )")
    diag_ports = ("    input wire sdi_rx_clk,\n    input wire [11:0] sdi_rx_flags,\n"
                  "    input wire sdi_ref_stable, sdi_gt_reset_released,\n")
    trans = replace_once(trans, "module frame_trans (", "module frame_trans (\n" + diag_ports)
    trans = replace_once(trans, "    // Select before frame_ctrl", """    // Observe the real camera upstream of VTC and frame admission.
    wire [415:0] sdi_diag_words;
    wcis_sdi_monitor sdi_monitor (
        .cfg_clk(S_AXI_ACLK), .reset_n(S_AXI_ARESETN),
        .rx_clk(sdi_rx_clk), .rx_flags(sdi_rx_flags),
        .rx_vs(cam_vs), .rx_de(cam_de),
        .ref_stable(sdi_ref_stable), .gt_reset_released(sdi_gt_reset_released),
        .words(sdi_diag_words));

    // Select before frame_ctrl""")
    trans = replace_once(trans, "        .rate_cfg_valid       (rate_cfg_valid      ),",
        "        .sdi_diag_words       (sdi_diag_words      ),\n"
        "        .rate_cfg_valid       (rate_cfg_valid      ),")
    peripheral = read_vendor(SOURCE / peripheral_rel)
    peripheral = replace_once(peripheral, "module ps_ai_peripheral (",
        "module ps_ai_peripheral (\n" + diag_ports)
    peripheral = replace_once(peripheral, "frame_trans frame_trans_inst0(",
        "frame_trans frame_trans_inst0(\n"
        "    .sdi_rx_clk(sdi_rx_clk), .sdi_rx_flags(sdi_rx_flags),\n"
        "    .sdi_ref_stable(sdi_ref_stable), .sdi_gt_reset_released(sdi_gt_reset_released),")
    rx = read_vendor(SOURCE / rx_rel)
    rx = replace_once(rx, "module rx_sdi (", "module rx_sdi (\n"
        "    output wire sdi_rx_clk,\n    output wire [11:0] sdi_rx_flags,\n"
        "    output wire sdi_ref_stable, sdi_gt_reset_released,\n")
    rx = replace_once(rx, "assign cam_rgb = {img_red,img_green,img_blue};",
        "assign sdi_rx_clk = rx_usrclk;\n"
        "assign sdi_rx_flags = {rx0_t_scan,rx0_t_rate,rx0_t_family,rx0_mode,rx0_locked};\n"
        "assign sdi_ref_stable = locked2;\n"
        "assign sdi_gt_reset_released = rx_gtx_full_reset_n;\n"
        "assign cam_rgb = {img_red,img_green,img_blue};")
    top = read_vendor(SOURCE / top_rel)
    top = replace_once(top, "ps_ai_peripheral U0_ps_ai_peripheral(",
        "wire sdi_rx_clk, sdi_ref_stable, sdi_gt_reset_released;\n"
        "wire [11:0] sdi_rx_flags;\n\nps_ai_peripheral U0_ps_ai_peripheral(\n"
        "  .sdi_rx_clk(sdi_rx_clk), .sdi_rx_flags(sdi_rx_flags),\n"
        "  .sdi_ref_stable(sdi_ref_stable), .sdi_gt_reset_released(sdi_gt_reset_released),")
    top = replace_once(top, "rx_sdi rx_sdi_inst (", "rx_sdi rx_sdi_inst (\n"
        "    .sdi_rx_clk(sdi_rx_clk), .sdi_rx_flags(sdi_rx_flags),\n"
        "    .sdi_ref_stable(sdi_ref_stable), .sdi_gt_reset_released(sdi_gt_reset_released),")

    # Reuse the existing CustomOp register + 512-bit PL-DDR boundary. Retain
    # the original adder inside the new wrapper, without a second DDR master
    # connection to PS HP ports or any changes to AI_Mate/clocks/pins.
    top = replace_once(top, "assign User_Ddr_awwinfo = {1'b0, {64{1'b1}}, 6'b0, 1'b1};", "// Native byte strobes are supplied by the CustomOp wrapper.")
    top = replace_once(top, "assign User_Ddr_arinfo  = {25'h0, 6'b0, 1'b1};", "")
    top = replace_once(top, "adder_top U_adder_top(", "wcis_face_customop U_adder_top(")
    top = replace_once(top, "  .itf_awdata       (User_Ddr_awwdata      ),", "  .itf_awdata       (User_Ddr_awwdata      ),\n  .itf_awinfo       (User_Ddr_awwinfo      ),")
    top = replace_once(top, "  .itf_araddr       (User_Ddr_araddr       ),", "  .itf_araddr       (User_Ddr_araddr       ),\n  .itf_arinfo       (User_Ddr_arinfo       ),")
    top = replace_once(top, "  .itf_rdata        (User_Ddr_rdata        ),", "  .itf_rdata        (User_Ddr_rdata        ),\n  .itf_rinfo        (User_Ddr_rinfo        ),")
    top = replace_once(top, "  .reset_reg        (                      ),", "")

    xdc = read_vendor(SOURCE/xdc_rel)
    # In Tcl, a trailing comment must begin a new command. The supplied XDC
    # used '##' as extra set_property arguments, aborting the rest of the file.
    import re
    xdc, comment_fixes = re.subn(r"(?m)^(set_property[^\n]*\])\s+##([^\n]*)$", r"\1 ; #\2", xdc)
    if comment_fixes != 2:
        raise RuntimeError(f"Expected two vendor XDC inline-comment fixes, got {comment_fixes}")
    xdc += r"""
# SDI2 passive snapshot CDC. Only asynchronous control FIRST stages are cut.
# Bundled snapshot data must settle within one 50 MHz CFG period; ACK crosses
# two stages and is consumed on a later edge. These bounds need routed proof.
set task_sdi_first [get_cells -hier -regexp {.*sdi_monitor/(request_sync|ack_sync|ref_sync|gt_sync)_reg\[0\]}]
set_false_path -to [get_pins -of_objects $task_sdi_first -filter {REF_PIN_NAME == D}]
set task_sdi_hold [get_cells -hier -regexp {.*sdi_monitor/payload_hold_reg\[[0-9]+\]}]
set task_sdi_snap [get_cells -hier -regexp {.*sdi_monitor/snapshot_reg\[[0-9]+\]}]
set_max_delay -datapath_only 20.0 -from $task_sdi_hold -to $task_sdi_snap
set_bus_skew 20.0 -from $task_sdi_hold -to $task_sdi_snap

# Face backend mailboxes: only the first toggle synchronizer is asynchronous.
# GP->HP request payload has >=2 HP cycles to settle before capture; HP->GP
# response has >=2 GP cycles. Never blanket-cut their bundled data paths.
"""
    # Vivado 2018.3 XDC is a restricted Tcl dialect: foreach/if are silently
    # skipped with a critical warning. Expand here and assert cells in build Tcl.
    for box, bound in [('read_request',8.0),('write_request',8.0),('read_response',20.0)]:
        xdc += (f'\n# FACE {box}\n'
                f'set task_sync [get_cells -hier -regexp {{.*U_adder_top/{box}/(request_sync|ack_sync)_reg\\[0\\]}}]\n'
                'set_false_path -to [get_pins -of_objects $task_sync -filter {REF_PIN_NAME == D}]\n'
                f'set task_hold [get_cells -hier -regexp {{.*U_adder_top/{box}/payload_hold_reg\\[[0-9]+\\]}}]\n'
                f'set task_capture [get_cells -hier -regexp {{.*U_adder_top/{box}/m_data_reg\\[[0-9]+\\]}}]\n'
                f'set_max_delay -datapath_only {bound} -from $task_hold -to $task_capture\n'
                f'set_bus_skew {bound} -from $task_hold -to $task_capture\n')
    clock_xdc = read_vendor(SOURCE / clock_xdc_rel)
    # Preserve vendor cuts for legacy crossings, but exclude the new mailbox
    # capture flops so broad clock false paths cannot hide their max delays.
    for source_clock, destination_clock, boxes in (
        ('clk_out1_clk_wiz_0','clk_pll_i',('read_request','write_request')),
        ('clk_pll_i','clk_out1_clk_wiz_0',('read_response',))):
        original = f'set_false_path -from [get_clocks {source_clock}] -to [get_clocks {destination_clock}]'
        excludes=' && '.join(f'NAME !~ "U_adder_top/{box}/m_data_reg*"' for box in boxes)
        replacement=(f'set task_legacy_regs [filter [all_registers -clock [get_clocks {destination_clock}]] {{{excludes}}}]\n'
                     f'set_false_path -from [get_clocks {source_clock}] -to $task_legacy_regs')
        clock_xdc=replace_once(clock_xdc,original,replacement)
    resize = read_vendor(SOURCE / resize_rel)
    resize = replace_once(resize,
        "\telse if(resize_href_temp)\n\t\tresize_data <= resize_data_temp;",
        "\t// Payload is consumed only with resize_href. Avoid a long config-to-CE path.\n"
        "\telse\n\t\tresize_data <= resize_data_temp;")
    vtc = (ROOT / "rtl/wcis_vtc.v").read_text(encoding="utf-8")
    patched_rels = (ctrl_rel, trans_rel, xdc_rel, clock_xdc_rel, resize_rel, vtc_rel, rx_rel, top_rel, peripheral_rel)
    for rel, text in ((ctrl_rel, ctrl), (trans_rel, trans), (xdc_rel, xdc), (resize_rel, resize),
                      (rx_rel, rx), (top_rel, top), (peripheral_rel, peripheral), (clock_xdc_rel,clock_xdc)):
        (CASE / rel).write_text(text, encoding="utf-8", newline="\n")
    (CASE / vtc_rel).write_text(vtc, encoding="utf-8", newline="\n")
    extra = CASE / "rtl/wcis"
    extra.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "rtl/wcis_frame_rate_gate.v", extra)
    shutil.copy2(ROOT / "rtl/wcis_sdi_monitor.v", extra)
    face_rtl = [Path('rtl') / name for name in (
        'wcis_face_customop.v', 'wcis_cdc_mailbox.v', 'wcis_face_preprocess.v',
        'wcis_affine_sampler.v', 'wcis_pixel_read_axi.v')]
    for path in face_rtl:
        shutil.copy2(ROOT / path, extra)
    # Letterbox is independently tested. It is deliberately not wired into the
    # legacy ImageMake pulse protocol without a matching NPU model contract.
    manifest = {
        "source": str(SOURCE), "tutorial": r"C:\Users\anxianji\Downloads\20260916\30TAI使用教程.pdf",
        "tutorial_sha256": sha(Path(r"C:\Users\anxianji\Downloads\20260916\30TAI使用教程.pdf")),
        "source_fps_assumed": 30, "active_target_fps": 20, "standby_target_fps": 1,
        "reset_mode": "bypass", "workspace_cleared_by_archive": True,
        "old_project_archive": r"D:\renlianshibie_old_20261012", "old_files_permanently_deleted": False,
        "patched": [{"path": str(r), "original_sha256": sha(SOURCE/r), "patched_sha256": sha(CASE/r)}
                    for r in patched_rels],
        "reuse": [{"path": str(r), "sha256": sha(CASE/r)} for r in (
            Path("rtl/display/axi_master.v"), Path("rtl/edif/AI_Mate.edif"))],
        "constraint_pin_assignments_changed": True,
        "constraint_pin_assignment_overrides": {
            "file": "constraints/fmql30tai_full_sdi_refclk.xdc",
            "sha256": sha(ROOT / "constraints/fmql30tai_full_sdi_refclk.xdc"),
            "applied_by": "scripts/prepare_case.tcl, PROCESSING_ORDER=LATE",
            "scope": "Full-board SDI reference clock only: P R6->U6, N R5->U5",
        },
        "new_rtl": [{"path": str(r), "sha256": sha(ROOT/r)} for r in (
            Path("rtl/wcis_frame_rate_gate.v"), Path("rtl/wcis_stream_letterbox.v"), Path("rtl/wcis_vtc.v"), Path("rtl/wcis_sdi_monitor.v"))],
        "sdi_diagnostics": {"id": "SDI2", "offsets": "0x100..0x130", "read_only": True,
                            "cfg_hz": 50000000, "board_verified": False},
        "letterbox_integrated": False, "new_face_models_integrated": False,
        "face_customop": {"register_base": "0x400C2000", "memory_bus": "vendor 512-bit UserCustomOp_0", "legacy_adder_preserved": True,
                          "rtl": [{"path": str(path), "sha256": sha(ROOT/path)} for path in face_rtl],
                          "full_board_verified": False},
        "board_verified": False
    }
    (ROOT / "docs").mkdir(exist_ok=True)
    patch = "".join("".join(difflib.unified_diff(read_vendor(SOURCE/r).splitlines(keepends=True),
                     (CASE/r).read_text(encoding="utf-8").splitlines(keepends=True),
                     fromfile="original/"+r.as_posix(), tofile="case/"+r.as_posix()))
                    for r in patched_rels)
    (ROOT / "docs/case_changes.patch").write_text(patch,encoding="utf-8")
    (ROOT / "docs/source_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Patched staged controls, passive SDI diagnostics, resize and VTC; preserved AI_Mate, original sources, pins and existing register offsets.")

if __name__ == "__main__":
    main()
