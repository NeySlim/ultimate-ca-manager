"""Every test gated on UCM_TEST_APP_PG_URL runs in the CI PostgreSQL application step."""
import fnmatch
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
LIST = ROOT / 'scripts' / 'ci' / 'pg-app-tests.txt'
SHARD = ROOT / 'scripts' / 'ci' / 'shard-tests.sh'
# Not gated on the variable, but HA code whose PostgreSQL behaviour must be exercised too
ALSO_ON_PG = ('tests/test_discovery_recovery_ha.py', 'tests/test_health_ha.py')


def _step_patterns():
    return [line.strip() for line in LIST.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith('#')]


def _shard(k, n, *extra):
    out = subprocess.run([str(SHARD), str(k), str(n), *extra], cwd=ROOT / 'backend',
                         capture_output=True, text=True, check=True).stdout
    return out.split()


def test_pg_gated_tests_run_in_the_pg_application_step():
    patterns = _step_patterns()
    assert patterns
    tests = ROOT / 'backend' / 'tests'
    gated = [f'tests/{f.name}' for f in sorted(tests.glob('test_*.py'))
             if f.name != pathlib.Path(__file__).name and 'UCM_TEST_APP_PG_URL' in f.read_text()]
    missing = [f for f in [*gated, *ALSO_ON_PG] if not any(fnmatch.fnmatch(f, p) for p in patterns)]
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


def _sharded_jobs():
    import yaml
    jobs = yaml.safe_load((ROOT / '.github' / 'workflows' / 'tests.yml').read_text())['jobs']
    found = {}
    for name, job in jobs.items():
        runs = [step['run'] for step in job.get('steps', []) if 'shard-tests.sh' in step.get('run', '')]
        if runs:
            found[name] = (job, runs)
    return found


def test_the_workflow_runs_every_shard_it_cuts():
    jobs = _sharded_jobs()
    assert {'test-backend', 'test-backend-postgres-app'} <= set(jobs), sorted(jobs)
    for name, (job, runs) in jobs.items():
        matrix = job['strategy']['matrix']
        assert set(matrix) == {'shard'}, (name, matrix)  # no include or exclude
        n = len(matrix['shard'])
        assert matrix['shard'] == list(range(1, n + 1)), (name, matrix)
        assert len(runs) == 1 and f'shard-tests.sh ${{{{ matrix.shard }}}} {n}' in runs[0], (name, runs)


@pytest.mark.parametrize('job', ['test-backend', 'test-backend-postgres-app'])
@pytest.mark.parametrize('shard_out, shard_rc, runs_pytest', [
    ('tests/test_a.py\ntests/test_b.py\n', 0, True),
    ('', 1, False),   # the script failed
    ('', 0, False),   # it printed nothing: pytest would run the whole suite
])
def test_a_failed_or_empty_shard_list_stops_the_step(tmp_path, job, shard_out, shard_rc, runs_pytest):
    # The step as GitHub runs it (bash -e), with stand-ins for the script and pytest
    run = _sharded_jobs()[job][1][0].replace('${{ matrix.shard }}', '1')
    (tmp_path / 'backend').mkdir()
    (tmp_path / 'scripts' / 'ci').mkdir(parents=True)
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    called = tmp_path / 'pytest-args'
    for path, body in ((tmp_path / 'scripts' / 'ci' / 'shard-tests.sh',
                        f'printf %s "{shard_out}"\nexit {shard_rc}\n'),
                       (bin_dir / 'pytest', f'printf "%s\\n" "$@" > {called}\n')):
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755)
    result = subprocess.run(['bash', '-e', '-c', run], cwd=tmp_path, capture_output=True, text=True,
                            env={'PATH': f'{bin_dir}:/usr/bin:/bin'})
    assert (result.returncode == 0) is runs_pytest, result.stderr
    assert called.exists() is runs_pytest
    if runs_pytest:
        assert called.read_text().split()[-2:] == ['tests/test_a.py', 'tests/test_b.py']
