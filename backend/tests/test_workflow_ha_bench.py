"""The HA bench runs in CI as shards that together are every file of tests/ha, once each: in one
job it outlasts the job's time limit."""
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SHARD = ROOT / 'scripts' / 'ci' / 'ha-bench-shard.sh'
WORKFLOW = ROOT / '.github' / 'workflows' / 'tests.yml'


def _shard(*args, check=True):
    return subprocess.run([str(SHARD), *args], cwd=ROOT / 'backend', capture_output=True, text=True,
                          check=check)


def _names():
    return _shard('--list').stdout.split()


def _job():
    """The text of the HA bench job in the workflow."""
    text = WORKFLOW.read_text()
    start = text.index('\n  test-ha-bench:')
    end = re.search(r'\n  [a-z][a-z0-9-]*:\n', text[start + 1:])
    return text[start:start + 1 + end.start()] if end else text[start:]


def test_the_shards_together_are_every_bench_file_once():
    every = sorted(f'tests/ha/{f.name}' for f in (ROOT / 'backend' / 'tests' / 'ha').glob('test_*.py'))
    assert every
    dealt = [f for name in _names() for f in _shard(name).stdout.split()]
    assert sorted(dealt) == every
    assert all(_shard(name).stdout.split() for name in _names()), 'an empty shard'


def test_the_workflow_runs_each_shard_and_no_other():
    job = _job()
    matrix = re.search(r'shard: \[([^\]]+)\]', job)
    assert matrix, 'the HA bench job has no shard matrix'
    assert sorted(s.strip() for s in matrix.group(1).split(',')) == sorted(_names())
    assert 'ha-bench-shard.sh ${{ matrix.shard }}' in job
    # A shard that fails or times out never cancels the others
    assert 'fail-fast: false' in job


def test_the_bench_is_never_run_whole_in_one_job():
    assert not re.search(r'pytest[^\n]*-m ha tests/ha\s*\n', _job())


@pytest.mark.parametrize('args', [(), ('nope',)])
def test_an_unknown_shard_is_refused(args):
    assert _shard(*args, check=False).returncode == 2
