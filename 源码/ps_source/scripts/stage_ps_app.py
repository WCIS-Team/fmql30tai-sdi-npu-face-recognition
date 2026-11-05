"""Stage the vendor PLIN reference app without editing its original files."""
from pathlib import Path
import shutil
import json
import hashlib

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'C:\Users\anxianji\Downloads\20260916\fpai_demo_app\fpai_demo_app')
EXAMPLE = SOURCE / 'examples/1_single_input+ai/PLin+SingleNet+HDMI'
DEST = ROOT / 'ps_app'

def read(path):
    data = path.read_bytes()
    try:
        return data.decode('utf-8-sig').replace('\r\n', '\n')
    except UnicodeDecodeError:
        return data.decode('gb18030').replace('\r\n', '\n')

def replace(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Missing/ambiguous patch anchor: ' + old[:60])
    return text.replace(old, new, 1)

DEST.mkdir(exist_ok=True)
shutil.copytree(SOURCE / 'deps/modelzoo_utils/include', DEST / 'vendor/include', dirs_exist_ok=True)
(DEST / 'example_include').mkdir(exist_ok=True)
if (EXAMPLE / 'include').exists():
    shutil.copytree(EXAMPLE / 'include', DEST / 'example_include', dirs_exist_ok=True)
shutil.copytree(EXAMPLE / 'configs', DEST / 'configs', dirs_exist_ok=True)
shutil.copy2(ROOT / 'include/wcis_rate_gate.hpp', DEST / 'example_include/wcis_rate_gate.hpp')
app_path = EXAMPLE / 'src/sdicamera+yolov5+hdmi.cpp'
app = read(app_path)
app = replace(app, '#include "ai_example/postprocesses.hpp"',
              '#include "wcis_rate_gate.hpp"\n#include "ai_example/postprocesses.hpp"')
app = replace(app, '    if (argc < 2)', '''    if (argc == 2 && std::string(argv[1]) == "--help") {
        std::cout << "Usage: wcis_sdi_reference <config.yaml>\\n"
                     "Optional camera.vision_mode: bypass | standby | active\\n"
                     "New modes require the WCIS bitstream and input VS.\\n";
        return 0;
    }
    if (argc < 2)''')
app = replace(app, '    camera_actor->start();', '''    // Apply only when explicitly configured, so an old reference bitstream
    // remains usable. Commit waits for an input frame boundary.
    if (camera_yaml["vision_mode"]) {
        const auto mode = camera_yaml["vision_mode"].as<std::string>();
        wcis::VisionMode value;
        if (mode == "bypass") value = wcis::VisionMode::Bypass;
        else if (mode == "standby") value = wcis::VisionMode::Standby;
        else if (mode == "active") value = wcis::VisionMode::Active;
        else throw std::invalid_argument("camera.vision_mode must be bypass, standby or active");
        const auto result = wcis::set_vision_mode(fpai_device, value);
        if (result != wcis::RateResult::Applied) {
            spdlog::error("WCIS mode not applied (code {}). Check bitstream signature and input VS.", static_cast<int>(result));
            return 2;
        }
        spdlog::info("WCIS vision mode applied: {}", mode);
    }
    camera_actor->start();''')
(DEST / 'src').mkdir(exist_ok=True)
(DEST / 'src/wcis_sdi_reference.cpp').write_text(app, encoding='utf-8', newline='\n')
actor = DEST / 'vendor/include/pipeline/actor/sdicamera_input_actor.hpp'
actor_text = replace(read(actor), 'if (!camera_->wait()) // in ms',
                     'if (!camera_->wait(1500)) // WCIS: allow a one-second standby frame interval')
actor.write_text(actor_text, encoding='utf-8', newline='\n')
buffer_manager = DEST / 'vendor/include/pipeline/memory/buffer_manager.hpp'
buffer_manager.write_text(replace(read(buffer_manager), '#include <mutex>',
                                  '#include <mutex>\n#include <shared_mutex>'),
                          encoding='utf-8', newline='\n')
# The ImageMake wait happens before PS capture wait in the ZG330 actor.
# Both must allow a standby frame interval plus transfer time.
et_device = DEST / 'vendor/include/et_device.hpp'
et_text = read(et_device)
zg_anchor = 'inline void runImageMakeForward(icraft::xrt::ZG330Device &device'
before, marker, zg = et_text.partition(zg_anchor)
if not marker:
    raise RuntimeError('ZG330 ImageMake specialization missing')
zg = replace(zg, 'if (duration.count() > 1000)', 'if (duration.count() > 1500)')
zg = replace(zg, 'auto start = std::chrono::high_resolution_clock::now();',
             'auto start = std::chrono::steady_clock::now();')
zg = replace(zg, 'std::chrono::duration<double, std::milli> duration = std::chrono::high_resolution_clock::now() - start;',
             'std::chrono::duration<double, std::milli> duration = std::chrono::steady_clock::now() - start;')
et_device.write_text(before + marker + zg, encoding='utf-8', newline='\n')
manifest = {'source': str(SOURCE), 'icraft_target': '3.39.0 onchip aarch64',
            'reference_model': 'vendor YOLOv5; no new face model integration',
            'source_sha256': hashlib.sha256(app_path.read_bytes()).hexdigest(),
            'patched_sha256': hashlib.sha256((DEST / 'src/wcis_sdi_reference.cpp').read_bytes()).hexdigest(),
            'camera_timeout_ms': 1500, 'imagemake_timeout_ms': 1500,
            'default_vision_mode': 'no extension register write',
            'board_application_run': False}
(ROOT / 'docs/ps_app_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print('Staged vendor PLIN app; original app and deployed board example preserved.')
