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


def test_the_workflow_runs_every_shard_it_cuts():
    text = (ROOT / '.github' / 'workflows' / 'tests.yml').read_text()
    assert 'shard-tests.sh ${{ matrix.shard }} 2)' in text and 'shard: [1, 2]\n' in text
    assert 'shard-tests.sh ${{ matrix.shard }} 3 ../scripts/ci/pg-app-tests.txt)' in text
    assert 'shard: [1, 2, 3]\n' in text
