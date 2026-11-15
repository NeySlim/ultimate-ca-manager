"""--order-seed shuffles the order of the test FILES, never the tests inside a file."""
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
FILES = ['tests/test_2fa_enforcement.py', 'tests/test_access_log_redaction.py',
         'tests/test_account_factors_need_session.py']


def _collect(*args):
    env = {k: v for k, v in os.environ.items() if not k.startswith('UCM_TEST_REQUIRE_')}
    proc = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', *(['-q'] if '-q' not in args and not any(a == '-v' for a in args) else []), '-p', 'no:cacheprovider',
                           '-p', 'no:randomly', *args, *FILES[:3]],
                          cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    ids = [ln for ln in proc.stdout.splitlines() if '::' in ln]
    return ids, proc.stdout


def _files(ids):
    out = []
    for i in ids:
        f = i.split('::')[0]
        if not out or out[-1] != f:
            out.append(f)
    return out


def test_without_the_option_the_order_is_unchanged():
    plain, out = _collect()
    assert _files(plain) == sorted(set(_files(plain)))
    assert 'order-seed' not in out


def test_the_same_seed_gives_the_same_order_and_keeps_tests_inside_a_file():
    plain, _ = _collect()
    a, out = _collect('--order-seed=7')
    b, _ = _collect('--order-seed=7')
    assert a == b
    assert sorted(a) == sorted(plain)
    assert 'order-seed: 7' in _collect('--order-seed=7', '-v')[1]
    for f in _files(plain):
        assert [i for i in a if i.split('::')[0] == f] == [i for i in plain if i.split('::')[0] == f]
    assert len(_files(a)) == len(_files(plain))


def test_some_seed_moves_the_files():
    plain, _ = _collect()
    orders = {tuple(_files(_collect(f'--order-seed={s}')[0])) for s in (1, 2, 3, 4)}
    assert any(o != tuple(_files(plain)) for o in orders)
