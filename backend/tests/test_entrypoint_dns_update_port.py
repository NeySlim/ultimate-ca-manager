"""The image entrypoint validates UCM_DNS_UPDATE_PORT (DNS UPDATE listener).

The listener is off when the variable is unset or 0. Otherwise the port must be
an integer from 1024 to 65535 (the image runs as the user ucm, without
CAP_NET_BIND_SERVICE) and must differ from the HTTPS and HTTP ports.
"""
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / 'docker' / 'entrypoint.sh'


def _run(env):
    """Run the entrypoint's port function and its DNS UPDATE check with ``env``."""
    body = ENTRYPOINT.read_text(encoding='utf-8')
    func = re.search(r'^validate_unprivileged_port\(\) \{.*?^\}', body, re.M | re.S).group(0)
    check = re.search(r'^# Validate the DNS UPDATE.*?(?=^echo -e "\$\{GREEN\}✅ Configuration validated)',
                      body, re.M | re.S).group(0)
    script = ('RED=; GREEN=; NC=\n: "${UCM_HTTPS_PORT:=8443}"\n: "${UCM_HTTP_PORT:=8080}"\n'
              + func + '\n' + check + '\necho passed\n')
    return subprocess.run(['bash', '-c', script], env={'PATH': '/usr/bin:/bin', **env},
                          capture_output=True, text=True)


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
