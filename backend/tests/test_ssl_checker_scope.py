"""The SSL checker opens a TLS connection to any host and port: admin:system, as the
discovery scans, and the same outbound vetting as the other routes, connecting to the
addresses vetted rather than resolving the name again."""
import json
import socket
import types

import pytest

pytestmark = pytest.mark.usefixtures('drop_new_users')

URL = '/api/v2/tools/check-ssl'


def _client(app, create_user, role):
    create_user(username=f'sslcheck_{role}', role=role)
    c = app.test_client()
    r = c.post('/api/v2/auth/login', data=json.dumps(
        {'username': f'sslcheck_{role}', 'password': 'TestPass123!'}), content_type='application/json')
    assert r.status_code == 200, r.data
    return c


@pytest.fixture
def network(monkeypatch):
    """The name resolves to what the test says; connections are recorded and refused."""
    import api.v2.tools.ssl_checker as checker
    import utils.ssrf_protection as ssrf
    state = {'answer': '203.0.113.7', 'connected': []}

    def _getaddrinfo(host, *a, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (state['answer'], 0))]

    def _connect(address, timeout=None, *a, **kw):
        state['connected'].append(address)
        raise ConnectionRefusedError('refused')
    monkeypatch.setattr(ssrf.socket, 'getaddrinfo', _getaddrinfo)
    monkeypatch.setattr(checker, 'socket', types.SimpleNamespace(
        create_connection=_connect, timeout=socket.timeout, gaierror=socket.gaierror))
    return state


def _check(client, host='tls.example.com', port=443):
    return client.post(URL, data=json.dumps({'hostname': host, 'port': port}),
                       content_type='application/json')


@pytest.mark.parametrize('role', ['viewer', 'auditor', 'operator'])
def test_without_admin_system_nothing_is_opened(app, create_user, network, role):
    r = _check(_client(app, create_user, role), host='203.0.113.7')
    assert r.status_code == 403, r.data
    assert network['connected'] == []


def test_the_admin_connects_to_the_vetted_address(auth_client, network):
    r = _check(auth_client, port=8443)
    assert r.status_code == 400 and 'refused' in r.get_json()['message'], r.data
    assert network['connected'] == [('203.0.113.7', 8443)]


@pytest.mark.parametrize('answer', ['169.254.169.254', '127.0.0.1', '169.254.10.1', '0.0.0.0'])
def test_forbidden_addresses_are_refused_before_connecting(auth_client, network, answer):
    network['answer'] = answer
    r = _check(auth_client)
    assert r.status_code == 403, r.data
    assert network['connected'] == []


@pytest.mark.parametrize('host', ['169.254.169.254', '127.0.0.1', '0.0.0.0', '::1'])
def test_a_literal_forbidden_address_is_refused(auth_client, network, host):
    r = _check(auth_client, host=host, port=80)
    assert r.status_code == 403, r.data
    assert network['connected'] == []


def test_a_port_out_of_range_is_refused(auth_client, network):
    assert _check(auth_client, port=70000).status_code == 400
    assert network['connected'] == []
