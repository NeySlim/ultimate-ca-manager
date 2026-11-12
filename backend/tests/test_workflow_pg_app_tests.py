"""Every test gated on UCM_TEST_APP_PG_URL runs in the CI PostgreSQL application job, and the shards lose no file."""
import fnmatch
import pathlib
import re
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
LIST = ROOT / 'scripts' / 'ci' / 'pg-app-tests.txt'
SHARD = ROOT / 'scripts' / 'ci' / 'shard-tests.sh'


def _step_patterns():
    return [line.strip() for line in LIST.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith('#')]


def _shard(k, n, *extra):
    out = subprocess.run([str(SHARD), str(k), str(n), *extra], cwd=ROOT / 'backend',
                         capture_output=True, text=True, check=True).stdout
    return out.split()


def test_pg_gated_tests_run_in_the_pg_application_job():
    patterns = _step_patterns()
    assert patterns
    tests = ROOT / 'backend' / 'tests'
    gated = [f'tests/{f.name}' for f in sorted(tests.glob('test_*.py'))
             if f.name != pathlib.Path(__file__).name and 'UCM_TEST_APP_PG_URL' in f.read_text()]
    missing = [f for f in gated if not any(fnmatch.fnmatch(f, p) for p in patterns)]
    assert not missing, missing


@pytest.mark.parametrize('n', [1, 2, 3])
def test_the_shards_together_are_every_test_file_once(n):
    every = sorted(f'tests/{f.relative_to(ROOT / "backend" / "tests")}'
                   for f in (ROOT / 'backend' / 'tests').rglob('test_*.py'))
    dealt = [f for k in range(1, n + 1) for f in _shard(k, n)]
    assert sorted(dealt) == every


def test_the_pg_shards_together_are_the_listed_files_once():
    listed = sorted({f'tests/{f.name}' for p in _step_patterns()
                     for f in (ROOT / 'backend').glob(p)})
    dealt = [f for k in (1, 2, 3) for f in _shard(k, 3, str(LIST))]
    assert listed and sorted(dealt) == listed


def test_a_listed_pattern_matching_no_file_fails_the_shard(tmp_path):
    bad = tmp_path / 'list.txt'
    bad.write_text('tests/test_fresh_app.py\ntests/no_such_file_*.py\n')
    run = subprocess.run([str(SHARD), '1', '1', str(bad)], cwd=ROOT / 'backend',
                         capture_output=True, text=True)
    assert run.returncode != 0 and 'no_such_file' in run.stderr


WORKFLOW = ROOT / '.github' / 'workflows' / 'tests.yml'
CUT_JOBS = {'test-backend': 2, 'test-backend-postgres-app': 3}


def _jobs():
    return yaml.safe_load(WORKFLOW.read_text())['jobs']


def _cut_step(job):
    steps = [s for s in job['steps'] if 'shard-tests.sh' in s.get('run', '')]
    assert len(steps) == 1
    return steps[0]


@pytest.mark.parametrize('name,n', sorted(CUT_JOBS.items()))
def test_the_workflow_runs_every_shard_it_cuts(name, n):
    job = _jobs()[name]
    matrix = job['strategy']['matrix']
    assert matrix['shard'] == list(range(1, n + 1))
    assert 'exclude' not in matrix and 'include' not in matrix
    calls = re.findall(r'shard-tests\.sh (\$\{\{ matrix\.shard \}\}|\S+) (\d+)', _cut_step(job)['run'])
    assert calls and all(k == '${{ matrix.shard }}' and int(m) == n for k, m in calls)


@pytest.fixture
def sandbox(tmp_path):
    (tmp_path / 'backend').mkdir()
    (tmp_path / 'backend' / 'tests').mkdir()
    for f in (ROOT / 'backend' / 'tests').glob('test_*.py'):
        (tmp_path / 'backend' / 'tests' / f.name).symlink_to(f)
    (tmp_path / 'scripts').symlink_to(ROOT / 'scripts')
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    witness = tmp_path / 'pytest-called'
    stub = bin_dir / 'pytest'
    stub.write_text(f'#!/bin/sh\necho "$@" > {witness}\n')
    stub.chmod(0o755)
    return tmp_path, witness


def _run_step(name, sandbox, shard):
    tmp, _ = sandbox
    script = _cut_step(_jobs()[name])['run'].replace('${{ matrix.shard }}', str(shard))
    env = {'PATH': f'{tmp / "bin"}:/usr/bin:/bin', 'HOME': str(tmp)}
    return subprocess.run(['bash', '-eo', 'pipefail', '-c', script], cwd=tmp, env=env,
                          capture_output=True, text=True)


@pytest.mark.parametrize('name', sorted(CUT_JOBS))
def test_a_failing_cut_never_starts_pytest(name, sandbox):
    run = _run_step(name, sandbox, 9)
    assert run.returncode != 0
    assert not sandbox[1].exists()


@pytest.mark.parametrize('name', sorted(CUT_JOBS))
def test_a_working_cut_hands_pytest_files(name, sandbox):
    run = _run_step(name, sandbox, 1)
    assert run.returncode == 0, run.stderr
    assert 'tests/test_' in sandbox[1].read_text()


@pytest.mark.parametrize('name', sorted(CUT_JOBS))
def test_an_empty_cut_never_starts_pytest(name, sandbox):
    tmp, witness = sandbox
    for f in (tmp / 'backend' / 'tests').iterdir():
        f.unlink()
    (tmp / 'scripts').unlink()
    (tmp / 'scripts' / 'ci').mkdir(parents=True)
    (tmp / 'scripts' / 'ci' / 'shard-tests.sh').symlink_to(SHARD)
    (tmp / 'scripts' / 'ci' / 'pg-app-tests.txt').write_text('')
    run = _run_step(name, sandbox, 1)
    assert run.returncode != 0
    assert not witness.exists()
