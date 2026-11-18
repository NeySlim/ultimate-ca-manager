"""scripts/pre-push runs the full suites for a push to dev or to the maintenance branch v2.x.

The hook runs in a scratch repository and is stopped by its "HEAD of the worktree" check (the pushed
sha is not HEAD), so no suite starts; the suites themselves are not exercised here.
"""
import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOK = ROOT / 'scripts' / 'pre-push'
BASH = shutil.which('bash')
OTHER = 'f' * 40

pytestmark = pytest.mark.skipif(BASH is None or shutil.which('git') is None, reason='bash and git are required')


def _env():
    # A commit hook exports GIT_DIR and friends: the scratch repository must not inherit them
    return {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}


@pytest.fixture
def repo(tmp_path):
    work = tmp_path / 'work'
    subprocess.run(['git', 'init', '-q', str(work)], check=True, env=_env())
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'x'],
                   cwd=work, check=True, env=_env())
    return work


def _push(repo, rref, sha=OTHER):
    line = f'refs/heads/x {sha} {rref} {"0" * 40}\n'
    return subprocess.run([BASH, str(HOOK)], cwd=repo, input=line, capture_output=True, text=True, env=_env(),
                          timeout=60)


@pytest.mark.parametrize('rref', ['refs/heads/v2.x', 'refs/heads/dev'])
def test_a_push_to_dev_or_the_maintenance_branch_runs_the_suites(repo, rref):
    res = _push(repo, rref)
    assert 'suites skipped' not in res.stdout
    assert res.returncode == 1
    assert 'is not the HEAD of this worktree' in res.stdout


@pytest.mark.parametrize('rref', ['refs/heads/test', 'refs/heads/main', 'refs/tags/v2.254.5', 'refs/heads/v2.xx',
                                  'refs/heads/feature/v2.x'])
def test_other_pushes_skip_the_suites(repo, rref):
    res = _push(repo, rref)
    assert res.returncode == 0, res.stdout + res.stderr
    assert 'suites skipped' in res.stdout
