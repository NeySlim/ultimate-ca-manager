#!/usr/bin/env python3
"""Write scripts/ci/test-durations.txt, the weights shard-tests.sh deals the test files by.

Usage: test_durations.py [-o OUT] LOG...
  LOG: either the logs of the CI's backend shard jobs (pytest -v -n 4 --dist loadfile, each
       line stamped by GitHub: a worker's time between two results goes to the later test's
       file), or the output of a run with `--durations=0 --durations-min=0` (setup, call and
       teardown summed per file);
  OUT: the weights file (default: test-durations.txt beside this script).
"""
import argparse
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DURATION = re.compile(r'^\s*(\d+(?:\.\d+)?)s\s+(?:setup|call|teardown)\s+(tests/\S+?\.py)(?:::|\s*$)')
STAMP = r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?Z '
WORKERS_UP = re.compile('^' + STAMP + r'\d+ workers \[\d+ items?\]')
RESULT = re.compile('^' + STAMP + r'\[(gw\d+)\] \[\s*\d+%\] [A-Z]+ (tests/\S+?\.py)::')
HEADER = ('# Seconds per backend test file, read by shard-tests.sh to balance the CI shards.\n'
          '# Regenerate with scripts/ci/test_durations.py from the logs of the shard jobs.\n')


def _seconds(whole, fraction):
    return datetime.fromisoformat(whole).timestamp() + float(f'0.{fraction or 0}')


def from_durations(lines):
    """{path: seconds} of the duration lines of a pytest report."""
    totals = defaultdict(float)
    for line in lines:
        match = DURATION.match(line)
        if match:
            totals[match.group(2)] += float(match.group(1))
    return dict(totals)


def from_ci_log(lines):
    """{path: seconds} of one shard job's log: each worker's time, test after test."""
    totals, last, start = defaultdict(float), {}, None
    for line in lines:
        up = WORKERS_UP.match(line)
        if up:
            start = _seconds(*up.groups())
            continue
        match = RESULT.match(line)
        if match and start is not None:
            now = _seconds(match.group(1), match.group(2))
            worker, path = match.group(3), match.group(4)
            totals[path] += max(0.0, now - last.get(worker, start))
            last[worker] = now
    return dict(totals)


def render(totals):
    return HEADER + ''.join(f'{max(seconds, 0.01):.2f} {path}\n' for path, seconds in sorted(totals.items()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('logs', nargs='+', type=Path)
    parser.add_argument('-o', '--out', type=Path, default=Path(__file__).with_name('test-durations.txt'))
    args = parser.parse_args(argv)
    totals = defaultdict(float)
    for log in args.logs:
        lines = log.read_text(encoding='utf-8', errors='replace').splitlines()
        for path, seconds in (from_ci_log(lines) or from_durations(lines)).items():
            totals[path] += seconds
    if not totals:
        parser.error('no result or duration line in the logs')
    args.out.write_text(render(totals), encoding='utf-8')
    print(f'{args.out}: {len(totals)} files, {sum(totals.values()):.0f} s')


if __name__ == '__main__':
    main()
