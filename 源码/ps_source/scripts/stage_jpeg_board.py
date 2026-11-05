"""Stage an isolated copy of the last eMMC board case; never edit its source."""
from pathlib import Path
import difflib, hashlib, json, shutil

ROOT=Path(__file__).resolve().parents[1]
TASK=Path('D:/yzd/tmp/pl-jpeg-board-20261016')
SOURCE=Path('D:/yzd/tmp/face-emmc-store-20261015/case')

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    case=TASK/'case'
    if case.exists(): raise FileExistsError('Refuse to overwrite existing staged case')
    def ignore(directory,names):
        return [n for n in names if n.endswith(('.runs','.cache','.sim','.hw','.ip_user_files')) or n in ('.Xil','ip_cache')]
    shutil.copytree(SOURCE,case,ignore=ignore)
    changes=[]
    def patch(name,fn):
        p=case/name
        old=p.read_text(encoding='utf-8-sig');new=fn(old)
        if old==new:raise ValueError('Patch did not apply: '+name)
        changes.append(dict(path=name,before_sha256=sha(SOURCE/name),
            after_sha256=hashlib.sha256(new.encode()).hexdigest(),
            patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=name,tofile=name))))
        p.write_text(new,encoding='utf-8')
    def top(text):
        assert text.count('wcis_face_customop U_adder_top(')==1
        return text.replace('wcis_face_customop U_adder_top(','wcis_recording_customop U_adder_top(')
    patch('rtl/ai7030_edif_top.v',top)
    def clock(text):
        text=text.replace('U_adder_top/','U_adder_top/face/')
        text=text.replace('NAME !~ "U_adder_top/face/write_request/m_data_reg*"',
            'NAME !~ "U_adder_top/face/write_request/m_data_reg*" && NAME !~ "U_adder_top/jpeg/read_request/m_data_reg*" && NAME !~ "U_adder_top/jpeg/write_request/m_data_reg*"')
        text=text.replace('NAME !~ "U_adder_top/face/read_response/m_data_reg*"',
            'NAME !~ "U_adder_top/face/read_response/m_data_reg*" && NAME !~ "U_adder_top/jpeg/read_response/m_data_reg*"')
        assert text.count('U_adder_top/jpeg/')==3
        return text
    patch('constrs_1/ai7030.xdc',clock)
    def impl(text):
        text=text.replace('U_adder_top/','U_adder_top/face/')
        for box,delay in [('read_request',8),('write_request',8),('read_response',20)]:
            prefix='.*U_adder_top/jpeg/'+box+'/'
            text+='\n# JPEG '+box+' bundled-data mailbox\n'
            text+='set task_sync [get_cells -hier -regexp {'+prefix+r'(request_sync|ack_sync)_reg\[0\]}]'+'\n'
            text+='set_false_path -to [get_pins -of_objects $task_sync -filter {REF_PIN_NAME == D}]\n'
            text+='set task_hold [get_cells -hier -regexp {'+prefix+r'payload_hold_reg\[[0-9]+\]}]'+'\n'
            text+='set task_capture [get_cells -hier -regexp {'+prefix+r'm_data_reg\[[0-9]+\]}]'+'\n'
            text+=f'set_max_delay -datapath_only {delay}.0 -from $task_hold -to $task_capture\n'
            text+=f'set_bus_skew {delay}.0 -from $task_hold -to $task_capture\n'
        return text
    patch('constrs_1/impl_constraints.xdc',impl)
    added=[]
    for name in ('wcis_recording_customop.v','wcis_jpeg_customop.v','wcis_jpeg_compressor.v'):
        target=case/'rtl/wcis'/name;shutil.copy2(ROOT/'rtl'/name,target)
        added.append(dict(path=str(target.relative_to(case)),sha256=sha(target)))
    dest=case/'rtl/wcis/jpeg_vendor';dest.mkdir()
    for p in (ROOT/'rtl/vendor/mjpegzero/rtl').glob('*.v'):
        shutil.copy2(p,dest/p.name);added.append(dict(path=str((dest/p.name).relative_to(case)),sha256=sha(p)))
    shutil.copy2(Path('D:/yzd/tmp/face-emmc-store-20261015/emmc_timing.xdc'),case/'constrs_1/emmc_timing.xdc')
    (TASK/'case-source-manifest.json').write_text(json.dumps(dict(source=str(SOURCE),case=str(case),
        modifications=changes,added=added,pins_changed=False,ps_payloads_changed=False),indent=2))
    (TASK/'case.patch').write_text(''.join(c['patch'] for c in changes))
    print('Isolated eMMC case staged; JPEG added; no board changed.')
if __name__=='__main__':main()
