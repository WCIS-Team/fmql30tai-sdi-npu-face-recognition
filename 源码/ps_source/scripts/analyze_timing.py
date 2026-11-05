from pathlib import Path
import re
from collections import Counter

root = Path(__file__).resolve().parents[1]
report = (root / 'case/fpai_demo_vivado.runs/impl_1/ai7030_edif_top_timing_summary_routed.rpt').read_text(errors='replace')
failed = []
for item in re.split(r'(?=Slack \()', report):
    m = re.match(r'Slack \(VIOLATED\)\s*:\s*([-\d.]+)ns', item)
    if not m:
        continue
    source = re.search(r'Source:\s*(.*)', item)
    dest = re.search(r'Destination:\s*(.*)', item)
    group = re.search(r'Path Group:\s*(.*)', item)
    if source and dest:
        failed.append((float(m.group(1)), source.group(1), dest.group(1), group.group(1) if group else ''))
print('Reported violated paths:', len(failed))
print('Destination parents:', Counter(d.rsplit('/', 1)[0] for _, _, d, _ in failed))
for row in failed[:12]:
    print(row)
for line in report.splitlines():
    if re.search(r'\s-0\.\d+\s+\S+\s+\S+$', line) and ('Period' in line or 'Width' in line):
        print(line)
(root / 'outputs/timing_failed_paths.txt').write_text('\n'.join(map(str, failed)), encoding='utf-8')
