"""The optional-backend markers: a skip without the backend, a failure when the CI requires it;
and the CI job that installs SoftHSM and GSSAPI runs every marked test with skips forbidden."""
import os
import re
import subprocess
import sys

import pytest

from tests.optional_backends import BACKENDS, required_env
from tests.workflow_support import ROOT, load

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
    clean = {k: v for k, v in os.environ.items() if not k.startswith('UCM_TEST_REQUIRE_')}
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


def test_the_job_installs_both_backends_and_keeps_tokens_in_its_temp_dir():
    job = _job()
    runs = '\n'.join(str(s.get('run', '')) for s in job['steps'])
    assert re.search(r'apt-install\.sh\b[^\n]*\bsofthsm2\b', runs)
    assert re.search(r'apt-install\.sh\b[^\n]*\blibkrb5-dev\b', runs)
    assert 'pyspnego[kerberos]' in runs
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
