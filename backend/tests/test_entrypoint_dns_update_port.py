"""The image entrypoint validates UCM_DNS_UPDATE_PORT (DNS UPDATE listener).

The check is the shell function check_dns_update_port in docker/dns-update-port.sh.
The tests source that file and call the function. entrypoint.sh sources the same file.

The listener is off when the variable is unset or 0. Otherwise the port must be
an integer from 1024 to 65535 (the image runs as the user ucm, without
CAP_NET_BIND_SERVICE) and must differ from the HTTPS and HTTP ports.
"""
import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / 'docker' / 'entrypoint.sh'
HELPER = ROOT / 'docker' / 'dns-update-port.sh'


def _run(env):
    """Source the helper and call check_dns_update_port with ``env``."""
    script = f'. {HELPER}; check_dns_update_port && echo passed'
    return subprocess.run(['bash', '-c', script], env={'PATH': '/usr/bin:/bin', **env},
                          capture_output=True, text=True)


@pytest.mark.parametrize('script', [ENTRYPOINT, HELPER], ids=['entrypoint', 'helper'])
def test_scripts_have_valid_bash_syntax_pos(script):
    # One file per call: `bash -n a b` checks a only and passes b as $1.
    result = subprocess.run(['bash', '-n', str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_scripts_with_a_syntax_error_are_caught_neg(tmp_path):
    bad = tmp_path / 'bad.sh'
    bad.write_text('check() {\n')
    result = subprocess.run(['bash', '-n', str(bad)], capture_output=True, text=True)
    assert result.returncode != 0


# The entrypoint itself stops on a bad port in its validation step, before it writes
# anything. A good port goes on to set up /opt/ucm, so only the refusal is run here,
# and not as root: there a regression could write to /opt/ucm.
@pytest.mark.skipif(os.geteuid() == 0, reason='a regression could write to /opt/ucm as root')
@pytest.mark.parametrize('env, message', [
    ({'UCM_DNS_UPDATE_PORT': '53'}, 'Invalid DNS UPDATE port: 53'),
    ({'UCM_DNS_UPDATE_PORT': '8443'}, 'is the same as the HTTPS or HTTP port'),
])
def test_entrypoint_stops_on_a_bad_port_neg(tmp_path, env, message):
    result = subprocess.run(['timeout', '60', 'bash', str(ENTRYPOINT)], cwd=tmp_path,
                            env={'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path), **env},
                            capture_output=True, text=True)
    assert result.returncode == 1, result.stdout
    assert message in result.stdout


@pytest.mark.parametrize('env', [
    {},
    {'UCM_DNS_UPDATE_PORT': ''},
    {'UCM_DNS_UPDATE_PORT': '0'},
    {'UCM_DNS_UPDATE_PORT': '8053'},
    {'UCM_DNS_UPDATE_PORT': '1024'},
    {'UCM_DNS_UPDATE_PORT': '65535'},
    {'UCM_DNS_UPDATE_PORT': '8053 '},
    {'UCM_DNS_UPDATE_PORT': ' 8053'},
    {'UCM_DNS_UPDATE_PORT': ' '},
    {'UCM_DNS_UPDATE_PORT': '00'},
    {'UCM_DNS_UPDATE_PORT': ' 0 '},
])
def test_accepted(env):
    result = _run(env)
    assert result.returncode == 0, result.stdout
    assert result.stdout.strip().endswith('passed')


@pytest.mark.parametrize('value', ['53', '1023', '65536', '-1', 'abc', '80.5', '8053/udp', '99999999999999999999',
                                   '80 53', '8053x', '70000'])
def test_rejected_value(value):
    result = _run({'UCM_DNS_UPDATE_PORT': value})
    assert result.returncode == 1
    assert 'passed' not in result.stdout


def test_privileged_port_error_names_the_port_mapping():
    result = _run({'UCM_DNS_UPDATE_PORT': '53'})
    assert '-p 53:8053/udp -p 53:8053/tcp' in result.stdout


@pytest.mark.parametrize('env', [
    {'UCM_DNS_UPDATE_PORT': '8443'},
    {'UCM_DNS_UPDATE_PORT': '8080'},
    {'UCM_DNS_UPDATE_PORT': '9443', 'UCM_HTTPS_PORT': '9443'},
    {'UCM_DNS_UPDATE_PORT': '9090', 'UCM_HTTP_PORT': '9090'},
])
def test_rejected_collision(env):
    result = _run(env)
    assert result.returncode == 1
    assert 'same as' in result.stdout


def test_collision_is_numeric_after_strip():
    result = _run({'UCM_DNS_UPDATE_PORT': ' 8443 '})
    assert result.returncode == 1
    assert 'same as' in result.stdout
