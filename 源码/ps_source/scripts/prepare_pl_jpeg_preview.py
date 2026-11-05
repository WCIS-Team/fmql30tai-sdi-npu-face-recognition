"""Stage the full preview candidate without modifying the proven source case."""
from pathlib import Path
import argparse,difflib,hashlib,json,re,shutil

R=Path(__file__).resolve().parents[1]
DEFAULT=Path('D:/yzd/tmp/pl-jpeg-bram-chunk-20261025')
BASE=Path('D:/yzd/tmp/pl-jpeg-board-20261016/case')

def once(s,a,b):
    if s.count(a)!=1:raise RuntimeError(f'Expected one integration anchor: {a!r}')
    return s.replace(a,b,1)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=DEFAULT)
    p.add_argument('--cache-case',type=Path,help='Read-only prior task case; retain completed IP runs, rebuild top only')
    p.add_argument('--buffer-camera-clock',action='store_true',help='Candidate-only BUFG after the unchanged legacy camera clock select')
    p.add_argument('--synchronize-frame-error',action='store_true',help='Candidate-only two-stage memory-domain synchronization of the retained writer overflow status')
    a=p.parse_args()
    out=a.out.resolve();case=out/'case';out.mkdir(parents=True,exist_ok=True)
    prior=json.loads((out/'preview-staging.json').read_text()) if (out/'preview-staging.json').exists() else {}
    if case.exists():
        for name,digest in prior.get('source_sha256',{}).items():
            source=Path(name)
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
                raise RuntimeError('Archived candidate source changed; stage into a new output directory: '+name)
    if case.exists() and prior.get('camera_clock_buffer',{}).get('enabled') and not a.buffer_camera_clock:
        raise RuntimeError('Existing candidate uses a buffered camera clock; keep --buffer-camera-clock')
    if case.exists() and a.synchronize_frame_error and not prior.get('frame_error_synchronizer',{}).get('enabled'):
        raise RuntimeError('Do not retrofit the frame-error CDC fix into an archived candidate; use a new output directory')
    if case.exists() and prior.get('frame_error_synchronizer',{}).get('enabled') and not a.synchronize_frame_error:
        raise RuntimeError('Existing candidate synchronizes frame errors; keep --synchronize-frame-error')
    cache=a.cache_case.resolve() if a.cache_case else BASE
    if a.cache_case:
        receipt=json.loads((cache.parent/'preview-staging.json').read_text())
        if Path(receipt['candidate_case']).resolve()!=cache:raise RuntimeError('Cache case does not match its task receipt')
        if receipt.get('camera_clock_buffer',{}).get('enabled') and not a.buffer_camera_clock:
            raise RuntimeError('Buffered camera cache requires an explicit matching --buffer-camera-clock option')
        if receipt.get('frame_error_synchronizer',{}).get('enabled') and not a.synchronize_frame_error:
            raise RuntimeError('Frame-error CDC cache requires --synchronize-frame-error')
    if case.exists() and a.buffer_camera_clock:
        previous=out/'preview-staging.json'
        if not previous.exists() or not json.loads(previous.read_text()).get('camera_clock_buffer',{}).get('enabled'):
            raise RuntimeError('Do not retrofit an archived candidate; use a new task output directory')
    if not case.exists():
        ignored=shutil.ignore_patterns('*.cache','*.hw','.Xil','*.log','*.jou','*.backup.*','ip_cache')
        def ignore(folder,names):
            excluded=set(ignored(folder,names))
            if not a.cache_case:excluded.update(n for n in names if n.endswith('.runs'))
            elif Path(folder).name.endswith('.runs'):excluded.update({'synth_1','impl_1'}&set(names))
            return excluded
        shutil.copytree(cache,case,ignore=ignore)
    elif not (out/'preview-staging.json').exists() and not (out/'preview-top.patch').exists():
        raise RuntimeError('Existing candidate directory has no staging receipt; refusing to overwrite')
    copied={}
    names=['wcis_recording_customop','wcis_jpeg_customop','wcis_jpeg_compressor',
        'wcis_face_customop','wcis_face_preprocess','wcis_affine_sampler','wcis_pixel_read_axi',
        'wcis_cdc_mailbox','wcis_status_sync','wcis_frame_rate_gate','wcis_sdi_monitor','wcis_native_write_commit',
        'wcis_sdi_jpeg_stream','wcis_jpeg_udp_packetizer','wcis_jpeg_network_tx','wcis_rgmii_tx_serdes','wcis_udp_payload_pipe',
        'wcis_mdio_clause22','wcis_preview_csr_router','wcis_preview_registers','wcis_pl_jpeg_preview']
    for name in names:
        src=R/f'rtl/{name}.v';dst=case/f'rtl/wcis/{name}.v'
        shutil.copy2(src,dst);copied[str(src)]=hashlib.sha256(src.read_bytes()).hexdigest()
    for name in ('mjpegzero','verilog_ethernet'):
        shutil.copytree(R/f'rtl/vendor/{name}',case/f'rtl/wcis/vendor/{name}',dirs_exist_ok=True)
    # Use one pinned JPEG RTL source set; the old project already lists this
    # directory. Preserve file identities for project references.
    for src in (R/'rtl/vendor/mjpegzero/rtl').glob('*.v'):shutil.copy2(src,case/'rtl/wcis/jpeg_vendor'/src.name)
    frame_error_synchronizer=dict(enabled=False)
    if a.synchronize_frame_error:
        frame_source=case/'rtl/display/frame_read_write_largebuf.v'
        frame_before=frame_source.read_bytes()
        normalized=frame_before.replace(b'\r\n',b'\n')
        marker=b'wire wr_wfifo_err_mem;'
        if marker not in normalized:
            anchor=b'frame_fifo_write\n#\n('
            if normalized.count(anchor)!=1:raise RuntimeError('Writer instance anchor changed')
            extra=(b'// Retained camera overflow status; keep the local write inhibit immediate.\n'
                   b'wire wr_wfifo_err_mem;\n'
                   b'wcis_status_sync write_error_crossing (\n'
                   b'    .clk(mem_clk), .reset(rst),\n'
                   b'    .s_status(wr_wfifo_err), .m_status(wr_wfifo_err_mem)\n);\n')
            normalized=normalized.replace(anchor,extra+anchor,1)
            normalized,n=re.subn(rb'(\.wr_wfifo_err\s*\()wr_wfifo_err(\s*\))',rb'\1wr_wfifo_err_mem\2',normalized)
            if n!=1:raise RuntimeError('Expected one unsynchronized writer status association')
        elif (normalized.count(marker)!=1 or normalized.count(b'wcis_status_sync write_error_crossing')!=1
              or not re.search(rb'\.wr_wfifo_err\s*\(wr_wfifo_err_mem\s*\)',normalized)):
            raise RuntimeError('Unexpected preexisting writer status patch')
        frame_after=normalized.replace(b'\n',b'\r\n') if b'\r\n' in frame_before else normalized
        frame_source.write_bytes(frame_after)
        (out/'frame-error-cdc.patch').write_text(''.join(difflib.unified_diff(
            frame_before.decode('utf-8').splitlines(True),frame_after.decode('utf-8').splitlines(True),
            fromfile='unpatched-candidate/frame_read_write_largebuf.v',tofile=str(frame_source))),encoding='utf-8')
        frame_error_synchronizer=dict(enabled=True,candidate_source=str(frame_source),
            before_sha256=prior.get('frame_error_synchronizer',{}).get('before_sha256',hashlib.sha256(frame_before).hexdigest()),
            after_sha256=hashlib.sha256(frame_after).hexdigest(),source_inhibit_changed=False,
            whole_source_synthesis_tested=False)
    camera_clock_buffer=dict(enabled=False)
    if a.buffer_camera_clock:
        camera_source=case/'rtl/sdi/rx_sdi.v'
        camera_before=camera_source.read_bytes()
        newline=b'\r\n' if b'\r\n' in camera_before else b'\n'
        old=b'assign cam_clk = rx0_locked ? rx_usrclk : sys_clk_200m;'
        new=newline.join([
            b'// Distribution buffer; the original asynchronous select equation is unchanged.',
            b'// This does not make clock-source switching glitch-free.',
            b'wire wcis_cam_clk_prebuf;',
            b'assign wcis_cam_clk_prebuf = rx0_locked ? rx_usrclk : sys_clk_200m;',
            b'BUFG wcis_cam_clk_bufg (.I(wcis_cam_clk_prebuf), .O(cam_clk));'])
        if camera_before.count(old)==1:camera_after=camera_before.replace(old,new)
        elif camera_before.count(new)==1:camera_after=camera_before
        else:raise RuntimeError('Unexpected camera clock source; refusing to guess')
        camera_source.write_bytes(camera_after)
        camera_clock_buffer=dict(enabled=True,selection_equation_changed=False,
            candidate_source=str(camera_source),before_sha256=prior.get('camera_clock_buffer',{}).get('before_sha256',hashlib.sha256(camera_before).hexdigest()),
            after_sha256=hashlib.sha256(camera_after).hexdigest(),switching_glitch_free_proven=False)
    src=BASE/'rtl/ai7030_edif_top.v';before=src.read_text(encoding='utf-8');s=before
    s=once(s,'  // PL DDR', '''  // Independent full-view PL Ethernet preview; full-board manual pin map.
  output pl_eth_tx_clk,pl_eth_tx_ctl,
  output [3:0] pl_eth_txd,
  output pl_eth_reset_n,pl_eth_mdc,
  inout pl_eth_mdio,
  // PL DDR''')
    # Address and data fan out. Only the register handshake/response traverses
    # the router; existing native DDR requests retain their original wiring.
    s=once(s,'wcis_recording_customop U_adder_top(','''wire old_awvalid,old_awready,old_arvalid,old_arready,old_rvalid,old_rready;
wire [31:0] old_rdata;
wire mdio_out,mdio_tristate,mdio_in;
IOBUF preview_mdio_buffer(.I(mdio_out),.T(mdio_tristate),.O(mdio_in),.IO(pl_eth_mdio));
(* keep_hierarchy="yes" *) wcis_pl_jpeg_preview U_pl_preview(
    .hp_clk(hp_clk),.gp_clk(gp_clk),.reset(hp_clk_rst|gp_clk_rst),
    .cam_clk(sdi_rx_clk),.cam_locked(sdi_rx_flags[0]),.cam_vsync(cam_vs),.cam_de(cam_data_en),.cam_rgb(cam_rgb),
    .awaddr(User_Reg_awwaddr),.awdata(User_Reg_awwdata),.awvalid(User_Reg_awwvalid),.awready(User_Reg_awwready),
    .araddr(User_Reg_araddr),.arvalid(User_Reg_arvalid),.arready(User_Reg_arready),
    .rdata(User_Reg_rdata),.rvalid(User_Reg_rvalid),.rready(User_Reg_rready),
    .legacy_awvalid(old_awvalid),.legacy_awready(old_awready),
    .legacy_arvalid(old_arvalid),.legacy_arready(old_arready),
    .legacy_rdata(old_rdata),.legacy_rvalid(old_rvalid),.legacy_rready(old_rready),
    .phy_tx_clk(pl_eth_tx_clk),.phy_tx_ctl(pl_eth_tx_ctl),.phy_txd(pl_eth_txd),
    .phy_reset_n(pl_eth_reset_n),.phy_mdc(pl_eth_mdc),
    .phy_mdio_out(mdio_out),.phy_mdio_tristate(mdio_tristate),.phy_mdio_in(mdio_in));
// Preserve the currently deployed fixed-priority DDR policy in this candidate.
wcis_recording_customop #(.FAIR_ARBITRATION(0),.VERIFY_NATIVE_WRITES(0)) U_adder_top(''')
    # Replace only legacy instance associations, not the new preview's input.
    for port,original,new in [('itf_ra_awvalid','User_Reg_awwvalid','old_awvalid'),
        ('itf_ra_awready','User_Reg_awwready','old_awready'),('itf_ra_arvalid','User_Reg_arvalid','old_arvalid'),
        ('itf_ra_arready','User_Reg_arready','old_arready'),('itf_ra_rdata','User_Reg_rdata','old_rdata'),
        ('itf_ra_rvalid','User_Reg_rvalid','old_rvalid'),('itf_ra_rready','User_Reg_rready','old_rready')]:
        s,n=re.subn(r'(\.'+port+r'\s*\(\s*)'+original+r'(\s*\))',lambda m:m[1]+new+m[2],s)
        if n!=1:raise RuntimeError(f'Legacy association missing: {port}')
    (case/'rtl/ai7030_edif_top.v').write_text(s,encoding='utf-8')
    (out/'preview-top.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),s.splitlines(True),fromfile=str(src),tofile=str(case/'rtl/ai7030_edif_top.v'))),encoding='utf-8')
    # Rewrite only the new project / copied hooks; never alter shared tooling.
    for src in [case/'fpai_demo_vivado.xpr',*(case/'ip_patch').rglob('*.tcl')]:
        # Some supplied Tcl files contain non-UTF8 comments. Replace ASCII
        # paths as bytes so their original encoding and content stay intact.
        text=src.read_bytes()
        # Cached projects can express this checkout as $PPRDIR/../../... .
        # Preserve its actual source location when the new task is nested
        # at a different depth; never relocate these external constraints.
        text=re.sub(rb'\$PPRDIR/(?:\.\./)+renlianshibie/fpga_project/',
                    lambda _:R.as_posix().encode()+b'/',text,flags=re.I)
        for origin in {BASE,cache}:
            for spelling in (origin.as_posix(),str(origin)):
                text=re.sub(re.escape(spelling.encode()),lambda _:case.as_posix().encode(),text,flags=re.I)
        src.write_bytes(text)
    report=dict(base_case=str(BASE),cache_case=str(cache),base_top_sha256=hashlib.sha256(before.encode()).hexdigest(),
        candidate_case=str(case),source_sha256=copied,board_deployed=False,
        current_native_policy=dict(FAIR_ARBITRATION=0,VERIFY_NATIVE_WRITES=0),
        changes=['new TX-only preview ports','NTP2 0x2200 CSR router with explicit next-hop MAC',
                 'PLL150/125/250 shared-clock serializers','registered UDP payload boundary','raw upstream SDI tap'],
        network_mode='TX_ONLY_SERDES_1G_FULL_DUPLEX',phy_extra_tx_delay_ps=0,
        camera_clock_buffer=camera_clock_buffer,frame_error_synchronizer=frame_error_synchronizer)
    (out/'preview-staging.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('FULL PREVIEW CANDIDATE STAGED')
if __name__=='__main__':main()
