"""With UCM_HA the image entrypoint refuses to invent a per-node UCM_SECRET_KEY."""
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / 'docker' / 'ha-secret.sh'


def _run(env):
    script = f'. {HELPER}; check_ha_secret && echo passed'
    return subprocess.run(['bash', '-c', script], env={'PATH': '/usr/bin:/bin', **env},
                          capture_output=True, text=True)


@pytest.mark.parametrize('ha', ['1', 'true', 'YES', 'on'])
def test_ha_without_secret_is_refused_neg(ha):
    r = _run({'UCM_HA': ha})
    assert r.returncode != 0 and 'UCM_SECRET_KEY' in r.stdout + r.stderr


def test_ha_with_secret_passes_pos():
    assert 'passed' in _run({'UCM_HA': '1', 'UCM_SECRET_KEY': 's'}).stdout


@pytest.mark.parametrize('ha', [None, '0', 'false', ''])
def test_without_ha_nothing_changes_pos(ha):
    env = {} if ha is None else {'UCM_HA': ha}
    assert 'passed' in _run(env).stdout


def test_entrypoint_refuses_ha_without_secret_before_going_further_neg():
    r = subprocess.run(['bash', str(ROOT / 'docker' / 'entrypoint.sh')],
                       env={'PATH': '/usr/bin:/bin', 'UCM_HA': '1'},
                       capture_output=True, text=True, timeout=30)
    out = r.stdout + r.stderr
    assert r.returncode != 0 and 'UCM_SECRET_KEY' in out
    assert 'Validating configuration' not in out
