"""The Intune client outlives a SCEP request: one token and one discovery per
app registration, renewed when its secret changes or its token is refused."""
import threading
import time
from types import SimpleNamespace

import pytest
import requests

from services.scep.intune_client import IntuneScepError, client_for_profile

SERVICE = [{'providerName': 'ScepRequestValidationFEService', 'uri': 'https://fef.example/scep'}]


class _Resp:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code}', response=self)

    def json(self):
        return self._body


def _profile(tenant='t1', client='c1', secret='s1'):
    return SimpleNamespace(intune_enabled=True,
                           intune_credentials=lambda: (tenant, client, secret))


@pytest.fixture
def net(monkeypatch):
    log = {'token': 0, 'discover': 0, 'validate': [], 'validate_status': 200}

    def post(url, data=None, json=None, headers=None, timeout=None):
        if 'oauth2' in url:
            time.sleep(0.02)  # lets concurrent callers overlap
            log['token'] += 1
            return _Resp({'access_token': f"tok-{log['token']}", 'expires_in': 3600})
        log['validate'].append(headers['Authorization'])
        return _Resp({'code': 'Success'}, log['validate_status'])

    def get(url, headers=None, timeout=None):
        log['discover'] += 1
        return _Resp({'value': SERVICE})

    monkeypatch.setattr('requests.post', post)
    monkeypatch.setattr('requests.get', get)
    return log


def test_two_requests_share_one_token_and_one_discovery(net):
    for _ in range(2):
        client_for_profile(_profile()).validate_request('txn', b'x')
    # graph token + intune token once each, one discovery
    assert net['token'] == 2
    assert net['discover'] == 1


def test_two_applications_do_not_share_a_client(net):
    a = client_for_profile(_profile('t1', 'c1', 's1'))
    b = client_for_profile(_profile('t2', 'c2', 's2'))
    assert a is not b


def test_changed_secret_or_tenant_builds_a_new_client(net):
    first = client_for_profile(_profile())
    first.validate_request('txn', b'x')
    assert client_for_profile(_profile(secret='s2')) is not first
    assert client_for_profile(_profile(tenant='t9')) is not first
    client_for_profile(_profile(secret='s2')).validate_request('txn', b'x')
    assert net['token'] == 4  # the rotated secret asked again


def test_concurrent_requests_fetch_the_token_once(net):
    errors = []

    def run():
        try:
            client_for_profile(_profile()).validate_request('txn', b'x')
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    assert net['token'] == 2 and net['discover'] == 1


def test_off_or_missing_profile_has_no_client():
    assert client_for_profile(None) is None
    assert client_for_profile(SimpleNamespace(intune_enabled=False)) is None


def test_incomplete_registration_raises():
    with pytest.raises(ValueError):
        client_for_profile(_profile(secret=''))


def test_401_from_validation_forgets_the_token(net):
    client = client_for_profile(_profile())
    client.validate_request('txn', b'x')
    net['validate_status'] = 401
    with pytest.raises(IntuneScepError):
        client.validate_request('txn', b'x')
    net['validate_status'] = 200
    client.validate_request('txn', b'x')
    # the intune token (second one) was asked for again, the graph one kept
    assert net['token'] == 3
    assert net['validate'][-1] != net['validate'][0]


def test_403_from_validation_forgets_the_token(net):
    client = client_for_profile(_profile())
    client.validate_request('txn', b'x')
    net['validate_status'] = 403
    with pytest.raises(IntuneScepError):
        client.validate_request('txn', b'x')
    net['validate_status'] = 200
    client.validate_request('txn', b'x')
    assert net['validate'][-1] != net['validate'][0]


@pytest.mark.parametrize('status', [401, 403])
def test_refused_discovery_forgets_the_graph_token(monkeypatch, net, status):
    seen = []
    codes = iter([status, 200])

    def get(url, headers=None, timeout=None):
        seen.append(headers['Authorization'])
        return _Resp({'value': SERVICE}, next(codes))

    monkeypatch.setattr('requests.get', get)
    client = client_for_profile(_profile())
    with pytest.raises(IntuneScepError):
        client.validate_request('txn', b'x')
    client.validate_request('txn', b'x')
    assert seen[0] != seen[1]
