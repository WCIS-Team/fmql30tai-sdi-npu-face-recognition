"""Compare every failing clock check with a baseline; never grant timing signoff."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re


def parse_report(text):
    lines = text.splitlines()
    summary = None
    for i, line in enumerate(lines):
        if 'WNS(ns)' in line and 'TPWS Total Endpoints' in line:
            for row in lines[i+1:i+8]:
                fields = row.split()
                if len(fields) == 12:
                    try:
                        summary = list(map(float, fields))
                        break
                    except ValueError:
                        pass
            break
    if summary is None or not all(map(math.isfinite, summary)):
        raise ValueError('Missing complete timing summary')
    labels = ('Check Type', 'Corner', 'Lib Pin', 'Reference Pin', 'Required(ns)',
              'Actual(ns)', 'Slack(ns)', 'Location', 'Pin')
    clock, period, columns = None, None, None
    checked, failures, tables = 0, [], 0
    for line in lines:
        if line.startswith('Clock Name:'):
            clock, period = line.split(':', 1)[1].strip(), None
        elif line.startswith('Period(ns):'):
            period = float(line.split(':', 1)[1].strip())
        elif line.startswith('Check Type'):
            # Locate columns from this table's own header. Check names may contain spaces.
            columns, start = [], 0
            for label in labels:
                pos = line.index(label, start)
                columns.append(pos)
                start = pos + len(label)
            if not clock or period is None:
                raise ValueError('Clock-check table has no clock/period')
            tables += 1
        elif columns is not None:
            if not line.strip():
                columns = None
                continue
            fields = [line[a:b].strip() for a, b in zip(columns, columns[1:] + [len(line)])]
            if len(fields) != 9 or not all(fields):
                raise ValueError('Malformed clock-check row: ' + line)
            required, actual, slack = map(float, fields[4:7])
            if period <= 0 or not all(map(math.isfinite, (period, required, actual, slack))):
                raise ValueError('Non-finite/invalid clock-check value')
            checked += 1
            if slack < 0:
                failures.append(dict(clock=clock, period_ns=period, check_type=fields[0],
                                     corner=fields[1], lib_pin=fields[2], reference_pin=fields[3],
                                     required_ns=required, actual_ns=actual, slack_ns=slack,
                                     location=fields[7], pin=fields[8]))
    if columns is not None or tables == 0 or checked == 0:
        raise ValueError('Incomplete/missing clock-check tables')
    # This prototype's baseline has two distinct failing endpoints. Reject unaccounted rows.
    if len(failures) != int(summary[10]) or summary[10] != int(summary[10]):
        raise ValueError('Detailed failing clock checks disagree with endpoint summary')
    if failures and min(row['slack_ns'] for row in failures) != summary[8]:
        raise ValueError('Detailed worst clock slack disagrees with summary')
    return dict(summary=summary, clock_tables=tables, checked_rows=checked,
                failures=sorted(failures, key=lambda row: json.dumps(row, sort_keys=True)))


def compare_reports(baseline, candidate):
    before, after = parse_report(baseline), parse_report(candidate)
    if before['failures'] != after['failures']:
        raise ValueError('Clock violation identity/type/value differs from accepted baseline')
    if before['summary'][8:11] != after['summary'][8:11]:
        raise ValueError('Aggregate clock violations differ from accepted baseline')
    s = after['summary']
    if min(s[0], s[4]) < 0 or any(s[i] != 0 for i in (1, 2, 5, 6)):
        raise ValueError('Candidate setup/hold is not clean')
    return before, after


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    report = dict(comparison_passed=False, production_timing_signoff=False,
                  board_verified=False, scope='Exact baseline compatibility, not a manufacturer waiver',
                  input_sha256={str(f.resolve()): hashlib.sha256(f.read_bytes()).hexdigest()
                                for f in (args.baseline, args.candidate, Path(__file__))})
    try:
        before, after = compare_reports(args.baseline.read_text(encoding='utf-8'),
                                        args.candidate.read_text(encoding='utf-8'))
        report.update(comparison_passed=True, baseline=before, candidate=after)
    except (ValueError, IndexError) as error:
        report['error'] = str(error)
        raise
    finally:
        args.out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PASS exact legacy clock-check compatibility; full timing signoff remains false')


if __name__ == '__main__':
    main()
