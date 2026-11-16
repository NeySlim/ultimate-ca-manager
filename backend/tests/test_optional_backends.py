"""The optional-backend markers: a skip without the backend, a failure when the CI requires it;
and the CI job that installs SoftHSM, GSSAPI and Redis runs every marked test with skips forbidden."""
import os
import re
import shlex
import subprocess
import sys

import pytest

from tests.optional_backends import BACKENDS, required_env
from tests.workflow_support import ROOT, evaluate, github_context, load

BACKEND_DIR = ROOT / 'backend'

SAMPLE = '''
import pytest
from tests.optional_backends import needs

missing = needs('softhsm', False, 'SoftHSM not installed')
present = needs('softhsm', True, 'SoftHSM not installed')

@missing
def test_missing():
    pass

@present
def test_skips_in_its_body():
    pytest.skip('python-pkcs11 not installed')

@present
def test_runs():
    pass

@needs('gssapi', False, 'no gssapi')
def test_other_backend():
    pass

def test_unmarked_skip():
    pytest.skip('unrelated')

@present
@pytest.mark.xfail(reason='known', strict=True)
def test_xfail():
    assert False
'''


def _run(tmp_path, env):
    (tmp_path / 'test_sample.py').write_text(SAMPLE)
    (tmp_path / 'conftest.py').write_text('from tests.optional_backends import pytest_configure, '
                                          'pytest_runtest_setup, pytest_runtest_makereport  # noqa\n')
    clean = {k: v for k, v in os.environ.items() if not k.startswith('UCM_TEST_REQUIRE_') and k != 'UCM_TEST_LEAK_MODE'}
    proc = subprocess.run([sys.executable, '-m', 'pytest', '-rA', '-p', 'no:cacheprovider', '-p', 'no:randomly',
                           '-o', 'addopts=', str(tmp_path / 'test_sample.py')],
                          cwd=tmp_path, capture_output=True, text=True, timeout=120,
                          env={**clean, **env, 'PYTHONPATH': str(BACKEND_DIR)})
    return proc, proc.stdout.strip().splitlines()[-1]


def test_without_the_variable_a_missing_backend_skips(tmp_path):
    proc, tail = _run(tmp_path, {})
    assert proc.returncode == 0, proc.stdout
    assert '1 passed' in tail and '4 skipped' in tail and '1 xfailed' in tail, tail


def test_with_the_variable_every_skip_of_a_marked_test_fails(tmp_path):
    proc, tail = _run(tmp_path, {required_env('softhsm'): '1'})
    assert proc.returncode == 1, proc.stdout
    # test_missing (setup) and test_skips_in_its_body fail; the other backend and the unmarked skip stay skips
    assert re.search(r'\b1 failed\b', tail) and re.search(r'\b1 error\b', tail), tail
    assert '2 skipped' in tail and '1 passed' in tail and '1 xfailed' in tail, tail
    assert 'skipped although UCM_TEST_REQUIRE_SOFTHSM=1: SoftHSM not installed' in proc.stdout
    assert 'skipped although UCM_TEST_REQUIRE_SOFTHSM=1: python-pkcs11 not installed' in proc.stdout


# ---------------------------------------------------------------- the CI job

SOFTHSM_FILES = ('test_hsm_brainpool.py', 'test_hsm_pss.py', 'test_hsm_sync_and_listing.py',
                 'test_pkcs11_fork.py', 'test_issue_366_hsm_ecdsa_der.py', 'test_hsm_pkcs11_mldsa.py',
                 'test_hsm_fips_softhsm.py')
GSSAPI_FILES = ('test_kerberos_keytab_validation.py', 'test_keytab_composed.py')
REDIS_FILES = ('test_redis_sessions.py', 'test_redis_events.py', 'test_factor_change_sessions.py',
               'test_websocket_handshake.py')


def _job():
    jobs = load('tests.yml')['jobs']
    found = [job for job in jobs.values()
             if any(required_env(b) in str(s.get('env', {})) for s in job.get('steps', []) for b in BACKENDS)]
    assert len(found) == 1, len(found)
    return found[0]


def _run_steps(job):
    return [s for s in job['steps'] if 'pytest' in str(s.get('run', ''))]


@pytest.mark.parametrize('backend', BACKENDS)
def test_the_job_runs_each_marker_with_skips_forbidden(backend):
    steps = [s for s in _run_steps(_job()) if f'-m needs_{backend}' in s['run']]
    assert len(steps) == 1, backend
    assert str(steps[0]['env'].get(required_env(backend))) == '1', backend


def test_the_job_installs_the_backends_and_keeps_tokens_in_its_temp_dir():
    job = _job()
    runs = '\n'.join(str(s.get('run', '')) for s in job['steps'])
    assert re.search(r'apt-install\.sh\b[^\n]*\bsofthsm2\b', runs)
    assert re.search(r'apt-install\.sh\b[^\n]*\blibkrb5-dev\b', runs)
    assert 'pyspnego[kerberos]' in runs
    # Redis: the package for its binary, the service it starts stopped before the tests
    assert re.search(r'apt-install\.sh\b[^\n]*\bredis-server\b', runs)
    steps = [str(s.get('run', '')) for s in job['steps']]
    stop = next(i for i, run in enumerate(steps) if re.search(r'systemctl stop redis-server\b', run))
    assert stop < next(i for i, run in enumerate(steps) if '-m needs_redis' in run)
    for step in _run_steps(job):
        if '-m needs_softhsm' in step['run']:
            conf = str(step['env'].get('SOFTHSM2_CONF', ''))
            assert conf.startswith('${{ runner.temp }}/'), conf
    # The token directory the job creates lives there too
    assert re.search(r'directories\.tokendir = \$\{\{ runner\.temp \}\}/', runs) or \
        re.search(r'directories\.tokendir = \$RUNNER_TEMP/', runs), runs


def _collected(marker, files):
    proc = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', '-q', '-p', 'no:cacheprovider',
                           '-m', marker, *[f'tests/{f}' for f in files]],
                          cwd=BACKEND_DIR, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    return {line.split('::')[0].split('/')[-1] for line in proc.stdout.splitlines() if '::' in line}


def test_each_named_file_has_tests_under_its_marker():
    assert _collected('needs_softhsm', SOFTHSM_FILES) == set(SOFTHSM_FILES)
    assert _collected('needs_gssapi', GSSAPI_FILES) == set(GSSAPI_FILES)
    assert _collected('needs_redis', REDIS_FILES) == set(REDIS_FILES)


@pytest.mark.parametrize('event, ref, runs', [
    ('push', 'refs/heads/feature/x', True),
    ('push', 'refs/heads/test', True),
    ('pull_request', 'refs/pull/1/merge', True),
    ('workflow_dispatch', 'refs/heads/dev', True),
    ('schedule', 'refs/heads/main', False),  # the nightly run is the sequential suite's
])
def test_when_the_job_runs(event, ref, runs):
    assert bool(evaluate(_job()['if'], {'github': github_context(event, ref), 'inputs': {}})) is runs


def _pytest_paths(run):
    """Positional arguments of the pytest command of a step: the paths it collects."""
    words = shlex.split(run.split('pytest', 1)[1].splitlines()[0])
    paths, skip = [], False
    for w in words:
        if skip:
            skip = False
        elif w in ('-m', '-k', '-p', '-o', '--tb', '-n'):
            skip = True
        elif not w.startswith('-'):
            paths.append(w)
    return paths


@pytest.mark.parametrize('backend', BACKENDS)
def test_each_step_collects_the_whole_test_tree(backend):
    step = next(s for s in _run_steps(_job()) if f'-m needs_{backend}' in s['run'])
    assert 'cd backend' in step['run'].splitlines()[0]
    assert _pytest_paths(step['run']) == ['tests/'], step['run']


# ---------------------------------------------------------------- a missing import never hides a module

BLOCK_PKCS11 = '''
import sys


class _Block:
    def find_spec(self, name, path=None, target=None):
        if name == 'pkcs11' or name.startswith('pkcs11.'):
            raise ImportError(f'{name} blocked by the test')


sys.meta_path.insert(0, _Block())
'''

NO_MLDSA = '''
from utils import key_algorithms

key_algorithms.mldsa_supported = lambda: False
'''


def _run_files(tmp_path, plugin, files, env, marker=None):
    (tmp_path / 'shim_plugin.py').write_text(plugin)
    clean = {k: v for k, v in os.environ.items() if not k.startswith('UCM_TEST_REQUIRE_') and k != 'UCM_TEST_LEAK_MODE'}
    args = [sys.executable, '-m', 'pytest', '-q', '-rA', '-p', 'no:cacheprovider', '-p', 'no:randomly',
            '-p', 'shim_plugin', *(['-m', marker] if marker else []), *[f'tests/{f}' for f in files]]
    proc = subprocess.run(args, cwd=BACKEND_DIR, capture_output=True, text=True, timeout=600,
                          env={**clean, **env, 'PYTHONPATH': os.pathsep.join([str(tmp_path), str(BACKEND_DIR)])})
    return proc, proc.stdout.strip().splitlines()[-1]


PKCS11_FILES = ('test_hsm_sync_and_listing.py', 'test_hsm_fips_softhsm.py')


def test_without_python_pkcs11_the_softhsm_tests_fail_under_the_variable(tmp_path):
    proc, tail = _run_files(tmp_path, BLOCK_PKCS11, PKCS11_FILES, {required_env('softhsm'): '1'},
                            marker='needs_softhsm')
    assert proc.returncode == 1, proc.stdout[-3000:]
    failed = {line.split('::')[0].split('/')[-1] for line in proc.stdout.splitlines()
              if line.startswith(('FAILED', 'ERROR'))}
    assert failed == set(PKCS11_FILES), proc.stdout[-3000:]
    assert 'passed' not in tail and 'skipped' not in tail, tail


def test_without_python_pkcs11_the_module_skips_quietly_otherwise(tmp_path):
    proc, tail = _run_files(tmp_path, BLOCK_PKCS11, PKCS11_FILES, {})
    assert proc.returncode == 0, proc.stdout[-3000:]
    assert 'skipped' in tail and 'failed' not in tail and 'error' not in tail, tail


def test_a_build_without_ml_dsa_is_no_lost_softhsm_test(tmp_path):
    proc, tail = _run_files(tmp_path, NO_MLDSA, ('test_hsm_pkcs11_mldsa.py',), {required_env('softhsm'): '1'})
    assert proc.returncode == 0, proc.stdout[-3000:]
    assert 'skipped' in tail and 'failed' not in tail, tail
