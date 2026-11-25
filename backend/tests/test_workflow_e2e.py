"""The end-to-end job: when it runs, what it runs, and what scripts/ci/e2e.sh does around Playwright."""
import os
import shutil
import subprocess
import sys
import time

import pytest

from tests.workflow_support import ROOT, evaluate, github_context, load, triggers

SCRIPT = ROOT / 'scripts' / 'ci' / 'e2e.sh'
JOB = 'test-e2e'


def _job():
    return load('tests.yml')['jobs'][JOB]


def _runs(event, ref):
    return bool(evaluate(_job()['if'], {'github': github_context(event, ref), 'inputs': {}}))


@pytest.mark.parametrize('event,ref,expected', [
    ('push', 'refs/heads/dev', True),
    ('push', 'refs/heads/retired', False),
    ('push', 'refs/heads/test', True),  # the run a release candidate is read from
    ('pull_request', 'refs/pull/12/merge', True),
    ('workflow_dispatch', 'refs/heads/feature/x', True),
    ('push', 'refs/heads/feature/x', False),
    ('schedule', 'refs/heads/main', False),
])
def test_the_job_runs_on_integration_pushes_pull_requests_and_by_hand(event, ref, expected):
    assert _runs(event, ref) is expected


def test_the_workflow_is_triggered_by_those_events():
    on = triggers(load('tests.yml'))
    assert 'dev' in on['push']['branches']
    assert 'pull_request' in on and 'workflow_dispatch' in on


def test_the_job_is_bounded_and_reads_only():
    job = _job()
    assert job['name'] == 'End-to-end (browser)'
    assert 0 < job['timeout-minutes'] <= 30
    assert job['permissions'] == {'contents': 'read'}


def test_the_report_and_traces_are_uploaded_when_it_fails():
    uploads = [s for s in _job()['steps'] if 'upload-artifact' in s.get('uses', '')]
    assert len(uploads) == 1
    step = uploads[0]
    assert step['if'] == 'failure()'
    assert {'frontend/playwright-report/', 'frontend/test-results/'} <= set(step['with']['path'].split())


def test_the_job_installs_the_browser_libraries_then_runs_the_script(tmp_path):
    """Each run step is executed with stand-ins: the script itself must be what runs the suite."""
    log = tmp_path / 'calls'
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for tool in ('npm', 'npx', 'pip', 'sudo'):
        (bin_dir / tool).write_text(f'#!/bin/sh\necho "{tool} $*" >> {log}\n')
        (bin_dir / tool).chmod(0o755)
    stub = tmp_path / 'scripts' / 'ci'
    stub.mkdir(parents=True)
    for name in ('e2e.sh', 'apt-install.sh'):
        (stub / name).write_text(f'#!/bin/sh\necho "{name} $*" >> {log}\n')
        (stub / name).chmod(0o755)
    (tmp_path / 'frontend').mkdir()
    for step in _job()['steps']:
        if 'run' in step:
            proc = subprocess.run(['bash', '-e', '-c', step['run']], cwd=tmp_path, capture_output=True, text=True,
                                  env={'PATH': f'{bin_dir}:/usr/bin:/bin'})
            assert proc.returncode == 0, (step.get('name'), proc.stderr)
    calls = log.read_text().splitlines()
    assert 'npx playwright install-deps chromium' in calls
    assert 'e2e.sh ' in calls
    assert calls.index('npx playwright install-deps chromium') < calls.index('e2e.sh ')


def _fake_tree(tmp_path):
    """A checkout with the real script and stand-ins for python, npm and npx."""
    root = tmp_path / 'repo'
    (root / 'scripts' / 'ci').mkdir(parents=True)
    shutil.copy(SCRIPT, root / 'scripts' / 'ci' / 'e2e.sh')
    (root / 'backend').mkdir()
    (root / 'backend' / 'wsgi.py').write_text('')
    (root / 'frontend' / 'node_modules').mkdir(parents=True)
    (root / 'frontend' / 'package.json').write_text('{}')
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    state = tmp_path / 'state'
    state.mkdir()
    # gunicorn stays up until killed and leaves its pid; the health check answers once it is there
    (bin_dir / 'fakepython').write_text(f'''#!/bin/sh
if [ "$1" = "-m" ] && [ "$2" = "gunicorn" ]; then
  echo $$ > {state}/server.pid; exec sleep 300
fi
if [ "$1" = "-" ]; then
  i=0; while [ ! -s {state}/server.pid ] && [ $i -lt 100 ]; do sleep 0.1; i=$((i+1)); done
  [ -s {state}/server.pid ]; exit $?
fi
exec {sys.executable} "$@"
''')
    (bin_dir / 'npm').write_text('#!/bin/sh\nexit 0\n')
    (bin_dir / 'npx').write_text(f'''#!/bin/sh
[ "$2" = "install" ] && exit 0
echo "$UCM_E2E_MANAGED $UCM_E2E_BASE_URL $UCM_E2E_ADMIN_PASSWORD $*" > {state}/playwright
exit 7
''')
    for f in bin_dir.iterdir():
        f.chmod(0o755)
    # No curl nor jq: the script falls back to its own health check, answered by the stand-in
    for tool in ('bash', 'dirname', 'mktemp', 'seq', 'sleep', 'rm', 'mkdir', 'setsid', 'tail', 'env', 'basename', 'cat'):
        (bin_dir / tool).symlink_to(shutil.which(tool))
    return root, bin_dir, state


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = open(f'/proc/{pid}/stat').read().rsplit(')', 1)[1].split()
    return stat[0] != 'Z'


def _run(root, bin_dir, tmp_path, *args):
    env = {'PATH': str(bin_dir), 'UCM_PYTHON': str(bin_dir / 'fakepython'),
           'TMPDIR': str(tmp_path), 'HOME': str(tmp_path)}
    return subprocess.run([str(bin_dir / 'bash'), 'scripts/ci/e2e.sh', *args], cwd=root, env=env,
                          capture_output=True, text=True, timeout=120)


def test_the_script_returns_playwrights_code_and_always_stops_the_instance(tmp_path):
    root, bin_dir, state = _fake_tree(tmp_path)
    proc = _run(root, bin_dir, tmp_path, '--grep', 'login')
    assert proc.returncode == 7, proc.stdout + proc.stderr
    managed, url, password, *args = (state / 'playwright').read_text().split()
    # The global setup and the restore project act only on the instance the script started
    assert managed == '1'
    assert url.startswith('https://127.0.0.1:') and password
    assert args == ['playwright', 'test', '--grep', 'login']
    pid = int((state / 'server.pid').read_text())
    deadline = time.monotonic() + 10
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _alive(pid), 'the instance outlived the script'
    # Its temporary directory is gone too
    assert not list(tmp_path.glob('ucm-e2e.*'))


def test_a_checkout_env_file_stops_the_script_before_any_instance(tmp_path):
    """settings.py loads <checkout>/.env even under env -i: the suite would run on its database."""
    root, bin_dir, state = _fake_tree(tmp_path)
    (root / '.env').write_text('DATABASE_URL=postgresql://ucm:x@db.example:5432/ucm\n')
    proc = _run(root, bin_dir, tmp_path)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert '.env' in proc.stderr
    assert not (state / 'server.pid').exists() and not (state / 'playwright').exists()
    assert not list(tmp_path.glob('ucm-e2e.*'))


@pytest.mark.skipif(not shutil.which('shellcheck'), reason='shellcheck not installed')
def test_the_script_passes_shellcheck():
    assert subprocess.run(['shellcheck', str(SCRIPT)]).returncode == 0
