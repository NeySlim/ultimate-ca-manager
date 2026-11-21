"""SharedCheck under the production worker (gevent, monkey-patched): callers that overlap a run
share it, wait no longer than its deadline, and never start a second read."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

SCRIPT = r'''
from gevent import monkey
monkey.patch_all()
import json, sys, threading, time
sys.path.insert(0, sys.argv[1])
from shared_check import SharedCheck

def matrix(kind, callers):
    shared = SharedCheck('probe')
    state = {'reads': 0, 'inflight': 0, 'peak': 0}
    release = threading.Event()

    def check():
        state['reads'] += 1
        state['inflight'] += 1
        state['peak'] = max(state['peak'], state['inflight'])
        try:
            if kind == 'slow':
                time.sleep(0.4)
            elif kind == 'silent':
                release.wait(30)
            else:
                time.sleep(0.01)
                raise OSError('refused')
        finally:
            state['inflight'] -= 1
    results = [None] * callers
    began = time.monotonic()

    def call(i):
        results[i] = [shared(check, 0.6 if kind == 'silent' else 2.0)[0], time.monotonic() - began]
    threads = []
    for i in range(callers):
        threads.append(threading.Thread(target=call, args=(i,)))
        threads[-1].start()
        time.sleep(0.05 if kind != 'error' else 0.002)
    for t in threads:
        t.join(10)
    release.set()
    shared.wait(5)
    return {'results': results, 'reads': state['reads'], 'peak': state['peak']}

print(json.dumps({f'{k}/{n}': matrix(k, n) for k in ('slow', 'silent', 'error') for n in (1, 2, 5)}))
'''


@pytest.fixture(scope='module')
def matrix():
    out = subprocess.run([sys.executable, '-I', '-c', SCRIPT, str(BACKEND)], capture_output=True,
                         text=True, timeout=60, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize('callers', [1, 2, 5])
def test_slow_healthy_check_is_shared(matrix, callers):
    m = matrix[f'slow/{callers}']
    assert [r[0] for r in m['results']] == ['ok'] * callers
    assert m['reads'] == 1 and m['peak'] == 1
    assert all(end < 0.9 for _, end in m['results']), m


@pytest.mark.parametrize('callers', [1, 2, 5])
def test_silent_check_ends_every_caller_at_its_deadline(matrix, callers):
    m = matrix[f'silent/{callers}']
    assert [r[0] for r in m['results']] == ['timeout'] * callers
    assert m['reads'] == 1 and m['peak'] == 1
    assert all(0.5 < end < 1.0 for _, end in m['results']), m


@pytest.mark.parametrize('callers', [1, 2, 5])
def test_failing_check_reads_one_at_a_time(matrix, callers):
    m = matrix[f'error/{callers}']
    assert [r[0] for r in m['results']] == ['error'] * callers
    assert 1 <= m['reads'] <= callers and m['peak'] == 1
    assert all(end < 0.5 for _, end in m['results']), m
