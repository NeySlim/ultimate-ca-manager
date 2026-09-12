"""The gunicorn access and error logs are rotated by the system.

The application bounds its own log, but the two gunicorn streams grew without
limit on a native install, and the documentation described an
/etc/logrotate.d/ucm that no package had ever shipped (#350, reported by
JoseGoncalves). Both packages install it now, so this checks the file exists
and that each recipe puts it where logrotate looks.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG = ROOT / 'packaging' / 'logrotate' / 'ucm'


def test_the_configuration_is_in_the_tree():
    assert CONFIG.is_file(), f'{CONFIG} is missing'


def test_it_rotates_the_two_unbounded_streams():
    body = CONFIG.read_text(encoding='utf-8')
    for stream in ('/var/log/ucm/access.log', '/var/log/ucm/error.log'):
        assert stream in body, f'{stream} is not rotated'


def test_it_reopens_the_logs_without_restarting_the_worker():
    """USR1 makes gunicorn reopen its files. A reload maps to HUP, which
    gracefully restarts the worker and drops every open WebSocket, so the
    rotation must never ask for one."""
    body = CONFIG.read_text(encoding='utf-8')
    assert 'USR1' in body
    directives = [line.split('#')[0] for line in body.splitlines()]
    assert not any(re.search(r'\bsystemctl\s+reload\b', line) for line in directives)
    assert not any(re.search(r'-HUP\b|SIGHUP\b', line) for line in directives)


@pytest.mark.parametrize('recipe', ['packaging/debian/rules', 'packaging/rpm/ucm.spec'])
def test_each_recipe_installs_it(recipe):
    body = (ROOT / recipe).read_text(encoding='utf-8')
    assert 'packaging/logrotate/ucm' in body, f'{recipe} does not install the rotation config'
    assert 'logrotate.d' in body, f'{recipe} does not name the logrotate directory'
