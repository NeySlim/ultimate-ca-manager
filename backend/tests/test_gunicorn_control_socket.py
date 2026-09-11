"""Gunicorn 25.1 introduced a control socket whose bundled release creates
``gunicorn.ctl`` in the working directory by default. The service runs from
/opt/ucm/backend, which ProtectSystem=strict keeps read-only, so the master
logged an error at every start and the worker logged a second one from the same
component (#349, reported by JoseGoncalves). UCM never uses the control
interface, so the socket is disabled in the shared gunicorn configuration,
which covers the Debian package, the RPM and the image.
"""
import ast
import pathlib

import pytest

CONFIG = pathlib.Path(__file__).resolve().parent.parent / 'gunicorn_config.py'


def _bindings():
    """Every value the configuration binds to a name, read without importing
    it: importing runs gevent's monkey.patch_all and would poison the suite.
    The whole tree is walked, not just its top level, so a name rebound in a
    branch further down is seen too, and annotated assignments count, since
    gunicorn reads the module's final state either way."""
    found = {}
    for node in ast.walk(ast.parse(CONFIG.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                try:
                    found.setdefault(target.id, []).append(ast.literal_eval(value))
                except ValueError:
                    found.setdefault(target.id, []).append(None)
    return found


def test_the_control_socket_is_disabled():
    values = _bindings().get('control_socket_disable')
    assert values, 'the configuration never disables the control socket'
    assert all(value is True for value in values), values


def test_the_key_used_is_one_gunicorn_reads():
    """``--no-control-socket`` is the command-line flag; the configuration key
    is ``control_socket_disable``. Gunicorn ignores an unknown key in a
    configuration file without a word, so a near-miss name would disable
    nothing and say nothing.

    Skipped when the importable gunicorn predates the control socket: those
    versions expose neither the interface nor its disable setting, and
    therefore need no configuration guard.
    """
    import gunicorn
    from gunicorn.config import Config
    known = Config().settings
    if not any('control_socket' in key for key in known):
        pytest.skip(f'gunicorn {gunicorn.__version__} has no control socket')
    used = [key for key in _bindings() if 'control_socket' in key]
    assert used, 'the configuration says nothing about the control socket'
    for key in used:
        assert key in known, f'{key} is not a gunicorn setting'
