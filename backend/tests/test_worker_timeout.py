"""UCM_WORKER_TIMEOUT sets gunicorn's worker timeout: 120 s unset, 30 to 3600 s, and a value
out of bounds or unreadable refuses the start with a message naming the variable."""
import ast
import pathlib

import pytest

from worker_timeout import DEFAULT, MAXIMUM, MINIMUM, worker_timeout

CONFIG = pathlib.Path(__file__).resolve().parent.parent / 'gunicorn_config.py'


@pytest.mark.parametrize('value, expected', [(None, 120), ('', 120), ('30', 30), (' 600 ', 600),
                                             ('3600', 3600)])
def test_accepted_values(value, expected):
    env = {} if value is None else {'UCM_WORKER_TIMEOUT': value}
    assert worker_timeout(env) == expected


@pytest.mark.parametrize('value', ['29', '3601', '0', '-5', '12.5', 'two minutes'])
def test_refused_values_stop_the_start(value):
    with pytest.raises(SystemExit) as stopped:
        worker_timeout({'UCM_WORKER_TIMEOUT': value})
    message = str(stopped.value)
    assert 'UCM_WORKER_TIMEOUT' in message and f'{MINIMUM}' in message and f'{MAXIMUM}' in message


def test_the_bounds():
    assert (MINIMUM, DEFAULT, MAXIMUM) == (30, 120, 3600)


def test_the_gunicorn_configuration_reads_it():
    """Read without importing: the configuration runs gevent's monkey.patch_all."""
    tree = ast.parse(CONFIG.read_text(encoding='utf-8'))
    bound = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == 'timeout' for t in node.targets)]
    assert len(bound) == 1
    call = bound[0]
    assert isinstance(call, ast.Call) and getattr(call.func, 'id', None) == 'worker_timeout'
