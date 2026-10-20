"""Admin UI / management API source-address allowlist (#402)."""
import json

import pytest

from models import db, SystemConfig, AuditLog
from utils import admin_allowlist
from utils.admin_allowlist import REFUSAL_MESSAGE, SocketIOAllowlistGate

INSIDE = '10.1.2.3'
OUTSIDE = '203.0.113.9'


def _store(app, value):
    with app.app_context():
        row = SystemConfig.query.filter_by(key=admin_allowlist.CONFIG_KEY).first()
        if value is None:
            if row:
                db.session.delete(row)
        elif row:
            row.value = value
        else:
            db.session.add(SystemConfig(key=admin_allowlist.CONFIG_KEY, value=value))
        db.session.commit()
    admin_allowlist.invalidate_cache()


def _stored(app):
    with app.app_context():
        row = SystemConfig.query.filter_by(key=admin_allowlist.CONFIG_KEY).first()
        return row.value if row else None


@pytest.fixture(autouse=True)
def _reset_allowlist(app, monkeypatch):
    monkeypatch.delenv(admin_allowlist.ENV_NETWORKS, raising=False)
    monkeypatch.delenv(admin_allowlist.ENV_DISABLE, raising=False)
    _store(app, None)
    yield
    # Anything left behind would lock the rest of the suite out.
    _store(app, None)


def _get(client, path, addr):
    return client.get(path, environ_base={'REMOTE_ADDR': addr})


def _refused(response):
    return response.status_code == 403 and REFUSAL_MESSAGE.encode() in response.data


ADMIN_PATHS = [
    '/',
    '/settings',
    '/assets/index.js',
    '/api/v2/certificates',
    '/api/v2/settings/general',
    '/api/docs',
    '/socket.io/?EIO=4&transport=polling',
]


@pytest.mark.parametrize('path', ADMIN_PATHS)
def test_empty_list_restricts_nothing(client, path):
    assert not _refused(_get(client, path, OUTSIDE))


@pytest.mark.parametrize('path', ADMIN_PATHS)
def test_outside_address_is_refused(app, client, path):
    _store(app, '10.0.0.0/8')
    r = _get(client, path, OUTSIDE)
    assert _refused(r)
    if path.startswith('/api/'):
        assert r.get_json()['status'] == 403
    assert not _refused(_get(client, path, INSIDE))


def test_login_is_refused_from_outside(app, client):
    _store(app, '10.0.0.0/8')
    r = client.post('/api/v2/auth/login', environ_base={'REMOTE_ADDR': OUTSIDE},
                    data=json.dumps({'username': 'admin', 'password': 'changeme123'}),
                    content_type='application/json')
    assert _refused(r)


PROTOCOL_PATHS = [
    '/acme/directory',
    '/acme/proxy/directory',
    '/acme/new-nonce',
    '/scep/pkiclient.exe?operation=GetCACaps',
    '/cgi-bin/pkiclient.exe?operation=GetCACaps',
    '/.well-known/est/cacerts',
    '/.well-known/acme-challenge/token',
    '/ocsp',
    '/ocsp/MEMwQTA_MD0wOzAJBgUrDgMCGgUABBQ',
    '/cdp/missing.crl',
    '/ca/missing.pem',
    '/tsa',
    '/ADPolicyProvider_CEP_UsernamePassword/service.svc',
    '/ADCertificateService_CES_Kerberos/service.svc',
    '/ssh/setup/missing',
    '/health',
    '/health/live',
    '/api/health',
    '/api/v2/health',
    '/api/v2/health/ready',
    '/metrics',
    '/api/v2/auth/verify',
]


@pytest.mark.parametrize('path', PROTOCOL_PATHS)
def test_protocols_and_probes_pass_from_outside(app, client, path):
    _store(app, '10.0.0.0/8')
    assert not _refused(_get(client, path, OUTSIDE))


def test_protocol_only_port_still_serves_from_outside(app):
    from werkzeug.test import Client
    from protocol_http_server import ProtocolOnlyMiddleware
    _store(app, '10.0.0.0/8')
    c = Client(ProtocolOnlyMiddleware(app))
    r = c.get('/cdp/missing.crl', environ_base={'REMOTE_ADDR': OUTSIDE})
    assert REFUSAL_MESSAGE.encode() not in r.data


def test_ipv6_networks(app, client):
    _store(app, '2001:db8::/32')
    assert not _refused(_get(client, '/', '2001:db8::5'))
    assert _refused(_get(client, '/', '2001:db9::5'))
    assert _refused(_get(client, '/', INSIDE))


def test_ipv4_mapped_peer_matches_ipv4_entry(app, client):
    _store(app, '10.0.0.0/8')
    assert not _refused(_get(client, '/', '::ffff:10.1.2.3'))
    assert _refused(_get(client, '/', '::ffff:203.0.113.9'))


def test_ipv4_mapped_entry_matches_ipv4_peer(app, client):
    _store(app, '::ffff:192.0.2.7')
    assert not _refused(_get(client, '/', '192.0.2.7'))
    assert _refused(_get(client, '/', '192.0.2.8'))


def _patch(auth_client, networks, addr):
    return auth_client.patch('/api/v2/settings/general',
                             data=json.dumps({'admin_allowed_networks': networks}),
                             content_type='application/json',
                             environ_base={'REMOTE_ADDR': addr})


def test_save_reports_client_ip_and_applies_at_once(app, auth_client, client):
    r = auth_client.get('/api/v2/settings/general', environ_base={'REMOTE_ADDR': INSIDE})
    data = r.get_json()['data']
    assert data['admin_client_ip'] == INSIDE
    assert data['admin_allowed_networks'] == []
    assert data['admin_allowed_networks_env_locked'] is False

    r = _patch(auth_client, ['10.0.0.0/8', '2001:db8::1'], INSIDE)
    assert r.status_code == 200, r.data
    assert _stored(app) == '10.0.0.0/8,2001:db8::1'
    assert _refused(_get(client, '/', OUTSIDE))
    with app.app_context():
        entry = AuditLog.query.filter_by(action='admin_allowlist_update') \
            .order_by(AuditLog.id.desc()).first()
        assert entry is not None and '10.0.0.0/8' in entry.details


def test_save_accepts_newline_separated_text(app, auth_client):
    r = _patch(auth_client, '10.0.0.0/8\n192.0.2.0/24', INSIDE)
    assert r.status_code == 200, r.data
    assert _stored(app) == '10.0.0.0/8,192.0.2.0/24'


def test_save_that_excludes_the_caller_is_refused(app, auth_client):
    r = _patch(auth_client, ['192.0.2.0/24'], INSIDE)
    assert r.status_code == 400
    assert INSIDE in r.get_json()['message']
    assert _stored(app) is None


@pytest.mark.parametrize('bad', [['10.0.0.0/8', 'not-an-ip'], ['10.0.0.300'],
                                 ['fe80::1%eth0'], 42,
                                 [f'10.0.{i // 256}.{i % 256}' for i in range(101)]])
def test_invalid_lists_are_refused(app, auth_client, bad):
    r = _patch(auth_client, bad, INSIDE)
    assert r.status_code == 400
    assert _stored(app) is None


def test_clearing_the_list_lifts_the_restriction(app, auth_client, client):
    _store(app, '10.0.0.0/8')
    r = _patch(auth_client, [], INSIDE)
    assert r.status_code == 200, r.data
    assert not _refused(_get(client, '/', OUTSIDE))


def test_env_wins_and_locks_the_setting(app, auth_client, client, monkeypatch):
    _store(app, '192.0.2.0/24')
    monkeypatch.setenv(admin_allowlist.ENV_NETWORKS, '10.0.0.0/8, 2001:db8::/32')
    assert _refused(_get(client, '/', '192.0.2.5'))
    assert not _refused(_get(client, '/', INSIDE))

    data = auth_client.get('/api/v2/settings/general',
                           environ_base={'REMOTE_ADDR': INSIDE}).get_json()['data']
    assert data['admin_allowed_networks_env_locked'] is True
    assert data['admin_allowed_networks'] == ['10.0.0.0/8', '2001:db8::/32']

    r = _patch(auth_client, ['10.0.0.0/8', '198.51.100.0/24'], INSIDE)
    assert r.status_code == 200
    assert _stored(app) == '192.0.2.0/24'


def test_env_with_only_invalid_entries_admits_nobody(client, monkeypatch):
    monkeypatch.setenv(admin_allowlist.ENV_NETWORKS, 'nonsense')
    assert _refused(_get(client, '/', INSIDE))
    assert not _refused(_get(client, '/health', INSIDE))


def test_disable_switch_lifts_the_check(app, auth_client, client, monkeypatch):
    _store(app, '10.0.0.0/8')
    monkeypatch.setenv(admin_allowlist.ENV_DISABLE, '1')
    assert not _refused(_get(client, '/', OUTSIDE))
    assert not _refused(_get(client, '/socket.io/?EIO=4&transport=polling', OUTSIDE))
    data = auth_client.get('/api/v2/settings/general',
                           environ_base={'REMOTE_ADDR': INSIDE}).get_json()['data']
    assert data['admin_allowlist_disabled'] is True


def _socket_gate_call(app, hops, peer, xff=None):
    from werkzeug.test import Client

    def inner(environ, start_response):
        start_response('200 OK', [('Content-Type', 'text/plain')])
        return [b'socket']

    c = Client(SocketIOAllowlistGate(inner, app, trusted_hops=hops))
    headers = {'X-Forwarded-For': xff} if xff else {}
    return c.get('/socket.io/?EIO=4&transport=polling', headers=headers,
                 environ_base={'REMOTE_ADDR': peer})


def test_socket_gate_resolves_the_client_behind_a_trusted_proxy(app):
    _store(app, '10.0.0.0/8')
    assert _socket_gate_call(app, 1, '127.0.0.1', INSIDE).status_code == 200
    assert _socket_gate_call(app, 1, '127.0.0.1', OUTSIDE).status_code == 403
    assert _socket_gate_call(app, 1, '127.0.0.1', '::ffff:10.1.2.3').status_code == 200
    # Forwarded headers from a peer outside UCM_TRUSTED_PROXIES are ignored.
    assert _socket_gate_call(app, 1, '198.51.100.7', INSIDE).status_code == 403
    assert _socket_gate_call(app, 0, '127.0.0.1', INSIDE).status_code == 403
