"""The ACME proxy connection test fetches a URL from the body: it is a write:acme
action like the other outbound tests, never open to the read-only auditor."""
import json

import pytest

pytestmark = pytest.mark.usefixtures('drop_new_users')

URL = '/api/v2/acme/client/proxy/test-connection'


def _client(app, create_user, role):
    create_user(username=f'proxytest_{role}', role=role)
    c = app.test_client()
    r = c.post('/api/v2/auth/login', data=json.dumps(
        {'username': f'proxytest_{role}', 'password': 'TestPass123!'}), content_type='application/json')
    assert r.status_code == 200, r.data
    return c


@pytest.fixture
def fetched(monkeypatch):
    """Records the URLs the route fetches; none leaves the test."""
    import utils.ssrf_protection as ssrf
    seen = []

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {'newNonce': 'x', 'meta': {'website': 'https://ca.example'}}

    def _get(url, *a, **kw):
        seen.append(url)
        return _Resp()
    monkeypatch.setattr(ssrf, 'safe_request_get', _get)
    import api.v2.acme_client.proxy as proxy
    if hasattr(proxy, 'safe_request_get'):
        monkeypatch.setattr(proxy, 'safe_request_get', _get)
    return seen


def test_the_auditor_is_refused_and_nothing_is_fetched(app, create_user, fetched):
    c = _client(app, create_user, 'auditor')
    r = c.post(URL, data=json.dumps({'url': 'https://10.0.0.5:8443/anything'}),
               content_type='application/json')
    assert r.status_code == 403, r.data
    assert fetched == []


@pytest.mark.parametrize('role', ['operator', 'admin'])
def test_write_acme_may_test(app, create_user, fetched, role):
    c = _client(app, create_user, role)
    r = c.post(URL, data=json.dumps({'url': 'https://acme.example/directory'}),
               content_type='application/json')
    assert r.status_code != 403, r.data
