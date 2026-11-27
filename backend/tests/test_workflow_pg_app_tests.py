"""Every test gated on UCM_TEST_APP_PG_URL runs in the CI PostgreSQL application step."""
import fnmatch
import os
import pathlib
import re
import statistics
import subprocess

import pytest

from tests.workflow_support import load

ROOT = pathlib.Path(__file__).resolve().parents[2]
LIST = ROOT / 'scripts' / 'ci' / 'pg-app-tests.txt'
SHARD = ROOT / 'scripts' / 'ci' / 'shard-tests.sh'
DURATIONS = ROOT / 'scripts' / 'ci' / 'test-durations.txt'
# Not gated on the variable, but code whose PostgreSQL branch must be exercised too
ALSO_ON_PG = ('tests/test_discovery_recovery_ha.py', 'tests/test_health_ha.py',
              'tests/test_migration_runner_isolation.py')


def _step_patterns():
    return [line.strip() for line in LIST.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith('#')]


def _shard(k, n, *extra, durations=None):
    env = {**os.environ, **({'SHARD_DURATIONS': str(durations)} if durations else {})}
    out = subprocess.run([str(SHARD), str(k), str(n), *extra], cwd=ROOT / 'backend',
                         capture_output=True, text=True, check=True, env=env).stdout
    return out.split()


def _weights(path):
    return {line.split()[1]: float(line.split()[0]) for line in path.read_text().splitlines()
            if line.strip() and not line.startswith('#')}


def test_pg_gated_tests_run_in_the_pg_application_step():
    patterns = _step_patterns()
    assert patterns
    tests = ROOT / 'backend' / 'tests'
    gated = [f'tests/{f.name}' for f in sorted(tests.glob('test_*.py'))
             if f.name != pathlib.Path(__file__).name and 'UCM_TEST_APP_PG_URL' in f.read_text()]
    missing = [f for f in [*gated, *ALSO_ON_PG] if not any(fnmatch.fnmatch(f, p) for p in patterns)]
    assert not missing, missing


@pytest.mark.parametrize('n', [1, 2, 3, 4, 7])
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


def _five_files(tmp_path, weights):
    """Five real test files, a list naming them and a durations file weighing some of them."""
    names = sorted(f'tests/{f.name}' for f in (ROOT / 'backend' / 'tests').glob('test_*.py'))[:5]
    listed = tmp_path / 'list.txt'
    listed.write_text('\n'.join(names) + '\n')
    durations = tmp_path / 'durations.txt'
    durations.write_text('# seconds path\n' + ''.join(
        f'{seconds} {names[i]}\n' for i, seconds in weights.items()))
    return names, listed, durations


def test_the_longest_files_go_first_each_to_the_lightest_shard(tmp_path):
    names, listed, durations = _five_files(tmp_path, {0: 10, 1: 6, 2: 5, 3: 4, 4: 1})
    shards = [_shard(k, 2, str(listed), durations=durations) for k in (1, 2)]
    # 10 to the first, 6 then 5 to the second, 4 to the first (14), 1 to the second (12)
    assert shards == [[names[0], names[3]], [names[1], names[2], names[4]]]


def test_a_file_without_a_measure_weighs_the_median(tmp_path):
    names, listed, durations = _five_files(tmp_path, {0: 10, 1: 10, 2: 10, 3: 1})
    shards = [_shard(k, 2, str(listed), durations=durations) for k in (1, 2)]
    # The fifth weighs 10: 10, 10, 10, 10 alternate, then 1 to the first
    assert shards == [[names[0], names[2], names[3]], [names[1], names[4]]]


def test_the_durations_file_weighs_each_file_once():
    lines = [line for line in DURATIONS.read_text().splitlines() if line.strip() and not line.startswith('#')]
    paths = [line.split()[1] for line in lines]
    assert all(len(line.split()) == 2 and float(line.split()[0]) > 0 for line in lines)
    assert len(paths) == len(set(paths)) and all(p.startswith('tests/') for p in paths)


FAULTS = 'test-backend-faults'
# A part of test-backend: at most fifteen minutes on four workers
PART_TARGET = 15 * 60


def _every_test_file():
    return sorted(f'tests/{f.relative_to(ROOT / "backend" / "tests")}'
                  for f in (ROOT / 'backend' / 'tests').rglob('test_*.py'))


def _job_shards(name):
    """The file list of each part of job `name`, as its own `files=$(...)` line deals it."""
    job = load('tests.yml')['jobs'][name]
    run = next(s['run'] for s in job['steps'] if 'shard-tests.sh' in s.get('run', ''))
    line = next(line.strip() for line in run.splitlines() if line.strip().startswith('files=$('))
    out = []
    for k in job['strategy']['matrix']['shard']:
        script = line.replace('${{ matrix.shard }}', str(k)) + '\nprintf "%s\\n" "$files"\n'
        done = subprocess.run(['bash', '-e', '-c', script], cwd=ROOT / 'backend',
                              capture_output=True, text=True, check=True)
        out.append(done.stdout.split())
    return out


def test_the_fault_scenarios_are_their_own_jobs_and_nothing_else():
    """Every test_package_leftover_retry_*.py, a fifteenth one included, once in the fault
    jobs and never in test-backend; the two jobs together are the whole suite, once each."""
    scenarios = sorted(f'tests/{f.name}' for f in (ROOT / 'backend' / 'tests').glob('test_package_leftover_retry_*.py'))
    assert len(scenarios) >= 14
    faults = [f for part in _job_shards(FAULTS) for f in part]
    backend = [f for part in _job_shards('test-backend') for f in part]
    assert sorted(faults) == scenarios
    assert not set(backend) & set(scenarios)
    assert sorted(faults + backend) == _every_test_file()


def test_the_fault_jobs_run_when_the_backend_shards_run():
    jobs = load('tests.yml')['jobs']
    assert jobs[FAULTS]['if'] == jobs['test-backend']['if']
    assert jobs[FAULTS]['strategy'].get('fail-fast') is False


def test_the_fault_jobs_deal_test_by_test():
    """A file of these is twenty minutes on one worker: --dist load spreads its tests."""
    job = load('tests.yml')['jobs'][FAULTS]
    run = next(s['run'] for s in job['steps'] if 'pytest' in s.get('run', ''))
    words = next(line.split() for line in run.splitlines() if line.strip().startswith('pytest '))
    assert words[words.index('--dist') + 1] == 'load' and words[words.index('-n') + 1] == '4', words


def test_the_sqlite_shards_are_within_ten_percent_of_each_other():
    weights = _weights(DURATIONS)
    median = statistics.median(weights.values())
    totals = [sum(weights.get(f, median) for f in part) for part in _job_shards('test-backend')]
    assert len(totals) >= 2
    assert max(totals) <= min(totals) * 1.1, totals


def test_no_backend_file_outlasts_a_part():
    """In loadfile a file stays on one worker: the longest one bounds its part, so none may pass
    the target of a part, nor the share of a part on its four workers."""
    weights = _weights(DURATIONS)
    median = statistics.median(weights.values())
    parts = _job_shards('test-backend')
    files = [f for part in parts for f in part]
    longest = max(weights.get(f, median) for f in files)
    share = sum(weights.get(f, median) for f in files) / (len(parts) * 4)
    assert longest <= PART_TARGET and longest <= share and share <= PART_TARGET, (longest, share)


@pytest.mark.parametrize('content, cited', [
    (None, 'no exclusion list'),
    ('# nothing but a comment\n', 'lists nothing'),
    ('tests/test_no_such_file_*.py\n', 'tests/test_no_such_file_*.py'),
])
def test_an_exclusion_list_that_excludes_nothing_stops_the_shard(tmp_path, content, cited):
    """A missing, empty or stale exclusion list would hand the fault scenarios back to the shards."""
    listed = tmp_path / 'exclude.txt'
    if content is not None:
        listed.write_text(content)
    result = subprocess.run([str(SHARD), '1', '2'], cwd=ROOT / 'backend', capture_output=True, text=True,
                            env={**os.environ, 'SHARD_EXCLUDE': str(listed)})
    assert result.returncode != 0 and result.stdout == '' and cited in result.stderr, result


def test_a_shard_lists_its_longest_files_first(tmp_path):
    """pytest-xdist hands out the files in this order: the longest start first."""
    names, listed, durations = _five_files(tmp_path, {0: 1, 1: 2, 2: 3, 3: 4, 4: 5})
    assert _shard(1, 1, str(listed), durations=durations) == names[::-1]


def _durations_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location('test_durations', ROOT / 'scripts' / 'ci' / 'test_durations.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_durations_are_read_from_a_pytest_report(tmp_path):
    module = _durations_module()
    report = ['============ slowest durations ============',
              '12.50s call     tests/test_a.py::TestX::test_y[p-1]',
              '0.50s setup    tests/test_a.py::TestX::test_y[p-1]',
              '3.00s teardown tests/ha/test_b.py::test_z',
              '(1 durations < 0.005s hidden.)']
    totals = module.from_durations(report)
    assert totals == {'tests/test_a.py': 13.0, 'tests/ha/test_b.py': 3.0}
    out = tmp_path / 'weights.txt'
    out.write_text(module.render(totals))
    assert _weights(out) == {'tests/ha/test_b.py': 3.0, 'tests/test_a.py': 13.0}


def test_the_durations_are_read_from_a_shard_jobs_log():
    """Each worker's time between two results goes to the later test's file."""
    log = ['2026-11-24T07:11:12.0000000Z 2 workers [4 items]',
           '2026-11-24T07:11:14.5000000Z [gw0] [ 25%] PASSED tests/test_a.py::test_1 ',
           '2026-11-24T07:11:15.0000000Z [gw1] [ 50%] SKIPPED tests/test_b.py::test_1 ',
           '2026-11-24T07:11:20.5000000Z [gw0] [ 75%] FAILED tests/test_c.py::test_1 ',
           '2026-11-24T07:11:21.0000000Z [gw1] [100%] PASSED tests/test_b.py::test_2[x y] ']
    assert _durations_module().from_ci_log(log) == {
        'tests/test_a.py': 2.5, 'tests/test_b.py': 9.0, 'tests/test_c.py': 6.0}


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
    assert {'test-backend', 'test-backend-postgres-app', FAULTS} <= set(jobs), sorted(jobs)
    for name, (job, runs) in jobs.items():
        matrix = job['strategy']['matrix']
        assert set(matrix) == {'shard'}, (name, matrix)  # no include or exclude
        n = len(matrix['shard'])
        assert matrix['shard'] == list(range(1, n + 1)), (name, matrix)
        assert len(runs) == 1 and f'shard-tests.sh ${{{{ matrix.shard }}}} {n}' in runs[0], (name, runs)


@pytest.mark.parametrize('job', ['test-backend', 'test-backend-postgres-app', FAULTS])
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


@pytest.mark.parametrize('content', [None, 'abc tests/test_a.py\n', '1.5\n'])
def test_a_missing_or_malformed_durations_file_stops_the_dealing(tmp_path, content):
    path = tmp_path / 'durations.txt'
    if content is not None:
        path.write_text(content)
    run = subprocess.run([str(SHARD), '1', '4'], cwd=ROOT / 'backend', capture_output=True, text=True,
                         env={**os.environ, 'SHARD_DURATIONS': str(path)})
    assert run.returncode == 2 and 'durations' in run.stderr and not run.stdout


def test_every_weighed_file_still_exists():
    """A weight left for a removed file is a list nobody refreshes."""
    gone = [p for p in _weights(DURATIONS) if not (ROOT / 'backend' / p).is_file()]
    assert not gone, gone


def _ha_files_the_marker_deselects():
    return sorted(p for p in (ROOT / 'backend' / 'tests' / 'ha').glob('test_*.py')
                  if re.search(r'^pytestmark\s*=.*\bpytest\.mark\.ha\b', p.read_text(), re.M))


def test_a_file_the_ha_marker_deselects_weighs_next_to_nothing():
    """pytest runs with -m 'not ha': these files are only collected, so the median would be a
    weight nothing measures (the shard job's log has no result line for them)."""
    files = _ha_files_the_marker_deselects()
    assert len(files) > 20, files
    weights = _weights(DURATIONS)
    heavy = {p.name: weights.get(f'tests/ha/{p.name}') for p in files
             if weights.get(f'tests/ha/{p.name}', 99) > 0.1}
    assert not heavy, heavy


def test_the_regenerated_weights_keep_the_deselected_ha_files(tmp_path):
    module = _durations_module()
    backend = tmp_path / 'backend'
    (backend / 'tests' / 'ha').mkdir(parents=True)
    (backend / 'tests' / 'ha' / 'test_marked.py').write_text('pytestmark = [pytest.mark.ha, node_counts(3)]\n')
    (backend / 'tests' / 'ha' / 'test_plain.py').write_text('pytestmark = pytest.mark.ha\n')
    (backend / 'tests' / 'ha' / 'test_unit.py').write_text('def test_x(): pass\n')
    assert module.deselected_files(backend) == {'tests/ha/test_marked.py': 0.0, 'tests/ha/test_plain.py': 0.0}
