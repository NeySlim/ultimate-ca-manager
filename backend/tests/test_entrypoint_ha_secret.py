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


@pytest.mark.parametrize('ha', ['1', 'true', 'YES', 'on', ' 1 ', '\ttrue\n'])
def test_ha_without_secret_is_refused_neg(ha):
    r = _run({'UCM_HA': ha})
    assert r.returncode != 0 and 'UCM_SECRET_KEY' in r.stdout + r.stderr


def test_ha_with_secret_passes_pos():
    assert 'passed' in _run({'UCM_HA': '1', 'UCM_SECRET_KEY': 's'}).stdout


@pytest.mark.parametrize('ha', [None, '0', 'false', '', 't rue', 'o n', '\x1c1'])
def test_without_ha_nothing_changes_pos(ha):
    env = {} if ha is None else {'UCM_HA': ha}
    assert 'passed' in _run(env).stdout


def _utf8_locale_trims_unicode_blanks():
    """Whether bash has C.UTF-8 here: without it the cases below would pass either way."""
    r = subprocess.run(['bash', '-c', 'x=$1; [ "${x%[[:space:]]}" != "$x" ]', '_', '1\u3000'],
                       env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C.UTF-8'}, capture_output=True)
    return r.returncode == 0


@pytest.mark.parametrize('ha', ['1\u3000', '\u2028true', 'on\u2003'])
def test_a_unicode_blank_is_no_ha_under_a_utf8_locale_pos(ha):
    if not _utf8_locale_trims_unicode_blanks():
        pytest.skip('no C.UTF-8 locale for bash here')
    assert 'passed' in _run({'UCM_HA': ha, 'LC_ALL': 'C.UTF-8'}).stdout


def test_entrypoint_checks_ha_secret_before_generating_one_neg():
    # test d'ordre textuel, le comportement est prouvé par les tests de ha-secret.sh et par l'image en CI
    text = (ROOT / 'docker' / 'entrypoint.sh').read_text()
    check = text.index('check_ha_secret || exit 1')
    assert check < text.index('ucm_secret_key /etc/ucm')


@pytest.mark.parametrize('ha', [' 1', '1 ', ' true\t'])
def test_ha_flag_blanks_are_ignored_neg(ha):
    r = _run({'UCM_HA': ha})
    assert r.returncode != 0 and 'UCM_SECRET_KEY' in r.stdout + r.stderr


@pytest.mark.parametrize('raw, expected', [('1', True), (' on ', True), ('\tTRUE\n', True), ('', False),
                                           ('t rue', False), ('\x1c1', False)])
def test_the_master_reads_the_ha_flag_as_the_application_does(monkeypatch, raw, expected):
    from config.settings import env_bool
    from services import cluster_commands
    monkeypatch.setenv('UCM_HA', raw)
    assert cluster_commands._ha_from_environment() is expected
    assert env_bool('UCM_HA', False) is expected
