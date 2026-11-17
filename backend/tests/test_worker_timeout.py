"""UCM_WORKER_TIMEOUT sets gunicorn's worker timeout: 120 s unset, 30 to 3600 s, and a value
out of bounds or unreadable refuses the start with a message naming the variable and exit 78,
the configuration refusal the systemd unit does not restart."""
import os
import pathlib
import subprocess
import sys

import pytest

from startup_refusal import EXIT_CODE
from worker_timeout import DEFAULT, MAXIMUM, MINIMUM, worker_timeout

BACKEND = pathlib.Path(__file__).resolve().parent.parent
CONFIG = BACKEND / 'gunicorn_config.py'

# The configuration as the gunicorn master executes it, over a temporary data directory;
# the boot reads of the database are stubbed, nothing else.
_LOAD = r'''
import runpy, sys
sys.path.insert(0, sys.argv[1])
import boot_config
boot_config.wstep_enabled = lambda data_path: False
boot_config.mtls_client_ca = lambda data_path: None
boot_config.materialize_https = lambda *args: None
print('timeout', runpy.run_path(sys.argv[2])['timeout'])
'''


def _load_config(tmp_path, value):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_') and k not in (
        'DATABASE_URL', 'DATABASE_PATH', 'UCM_HA', 'HTTPS_CERT_PATH', 'HTTPS_KEY_PATH',
        'PYTHONPATH', 'UCM_WORKER_TIMEOUT')}
    (tmp_path / 'etc').mkdir(exist_ok=True)
    env.update(DATA_DIR=str(tmp_path), UCM_BASE_PATH=str(tmp_path), UCM_CONFIG_DIR=str(tmp_path / 'etc'),
               ACCESS_LOG=str(tmp_path / 'access.log'), ERROR_LOG=str(tmp_path / 'error.log'))
    if value is not None:
        env['UCM_WORKER_TIMEOUT'] = value
    return subprocess.run([sys.executable, '-c', _LOAD, str(BACKEND), str(CONFIG)], cwd=tmp_path,
                          env=env, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize('value, expected', [(None, 120), ('', 120), ('30', 30), (' 600 ', 600),
                                             ('3600', 3600)])
def test_accepted_values(value, expected):
    env = {} if value is None else {'UCM_WORKER_TIMEOUT': value}
    assert worker_timeout(env) == expected


@pytest.mark.parametrize('value', ['29', '3601', '0', '-5', '12.5', 'two minutes'])
def test_refused_values_stop_the_start(value, capsys):
    with pytest.raises(SystemExit) as stopped:
        worker_timeout({'UCM_WORKER_TIMEOUT': value})
    assert stopped.value.code == EXIT_CODE == 78
    message = capsys.readouterr().err
    assert 'UCM_WORKER_TIMEOUT' in message and f'{MINIMUM}' in message and f'{MAXIMUM}' in message


def test_the_gunicorn_master_exits_78_on_a_refused_value(tmp_path):
    run = _load_config(tmp_path, '5')
    assert run.returncode == 78, run.stderr
    assert 'UCM_WORKER_TIMEOUT must be a whole number of seconds from 30 to 3600' in run.stderr


def test_the_bounds():
    assert (MINIMUM, DEFAULT, MAXIMUM) == (30, 120, 3600)


@pytest.mark.parametrize('value, expected', [('45', 45), (None, 120)])
def test_the_gunicorn_configuration_reads_it(tmp_path, value, expected):
    run = _load_config(tmp_path, value)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip().splitlines()[-1] == f'timeout {expected}'
