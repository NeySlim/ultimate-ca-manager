"""A DNS provider's error message never carries the credential back out.

Five of the fifty providers passed a failure through ``redact_secrets``; the
rest returned ``str(e)`` or the raw response body. That matters because several
providers authenticate with query parameters, and a requests ConnectionError
or Timeout message embeds the full URL: the API key and token came back out of
``POST /api/v2/dns-providers/<id>/test`` as the message shown in the browser,
and went into the application log on the way. A provider that authenticates
with a token it fetched at runtime leaked that too -- ``redact_secrets`` only
knew the configured credentials.
"""

import json

import pytest
import requests

from services.acme.dns_providers.base import BaseDnsProvider
from services.acme.dns_providers.cloudns import ClouDnsDnsProvider
from services.acme.dns_providers.corenetworks import CoreNetworksDnsProvider
from services.acme.dns_providers.easydns import EasyDnsDnsProvider

API_KEY = 'EASYDNSKEY-abcdef0123456789'
API_TOKEN = 'EASYDNSTOKEN-9876543210fedcba'
CLOUDNS_PASSWORD = 'CLOUDNSPASS-0123456789abcdef'
DERIVED_BEARER = 'CORENET-BEARER-aaaaaaaaaaaaaaaa'


def _connection_error(url):
    """The exception requests really raises: it carries the whole URL."""
    return requests.exceptions.ConnectionError(
        f"HTTPSConnectionPool(host='x', port=443): Max retries exceeded "
        f"with url: {url} (Caused by NewConnectionError('...'))"
    )


class _Response:
    """Enough of a requests.Response for the error helpers."""

    def __init__(self, status_code=403, text='', reason='Forbidden'):
        self.status_code = status_code
        self.text = text
        self.reason = reason

    def json(self):
        return json.loads(self.text)


def test_easydns_network_failure_keeps_its_query_credentials(monkeypatch):
    """The provider whose secrets travel in the URL."""
    monkeypatch.setattr(
        requests, 'request',
        lambda method, url, **kw: (_ for _ in ()).throw(_connection_error(url)))

    provider = EasyDnsDnsProvider({'api_key': API_KEY, 'api_token': API_TOKEN})
    ok, message = provider.test_connection()

    assert ok is False
    assert API_KEY not in message
    assert API_TOKEN not in message


def test_cloudns_network_failure_keeps_its_query_credentials(monkeypatch):
    """The provider that already redacted: its answer does not change."""
    def fake_get(url, **kw):
        query = '&'.join(f'{k}={v}' for k, v in (kw.get('params') or {}).items())
        raise _connection_error(f'{url}?{query}')

    monkeypatch.setattr(requests, 'get', fake_get)

    provider = ClouDnsDnsProvider({'auth_id': '1234',
                                   'auth_password': CLOUDNS_PASSWORD})
    ok, message = provider.test_connection()

    assert ok is False
    assert CLOUDNS_PASSWORD not in message


def test_a_token_fetched_at_runtime_is_redacted_too(monkeypatch):
    """``redact_secrets`` only knew the configured credentials."""
    class _Token:
        status_code = 200
        text = '{"token": "%s"}' % DERIVED_BEARER

        def json(self):
            return {'token': DERIVED_BEARER}

    monkeypatch.setattr(requests, 'post', lambda *a, **k: _Token())

    def fake_request(method, url, **kw):
        raise _connection_error(
            f"{url} (Authorization: {kw['headers']['Authorization']})")

    monkeypatch.setattr(requests, 'request', fake_request)

    provider = CoreNetworksDnsProvider({'username': 'u', 'password': 'pw1234'})
    ok, message = provider.test_connection()

    assert ok is False
    assert DERIVED_BEARER not in message


def test_the_leak_does_not_reach_the_browser(auth_client, monkeypatch):
    """The whole path: POST /api/v2/dns-providers/<id>/test."""
    created = auth_client.post('/api/v2/dns-providers', data=json.dumps({
        'name': 'redaction-check', 'provider_type': 'easydns',
        'credentials': {'api_key': API_KEY, 'api_token': API_TOKEN},
    }), content_type='application/json')
    assert created.status_code == 201
    provider_id = created.get_json()['data']['id']

    monkeypatch.setattr(
        requests, 'request',
        lambda method, url, **kw: (_ for _ in ()).throw(_connection_error(url)))

    answer = auth_client.post(f'/api/v2/dns-providers/{provider_id}/test')
    body = answer.get_data(as_text=True)

    assert answer.status_code == 200
    assert API_KEY not in body
    assert API_TOKEN not in body


class _Probe(BaseDnsProvider):
    PROVIDER_TYPE = 'probe'
    REQUIRED_CREDENTIALS = []

    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        return True, ''

    def delete_txt_record(self, domain, record_name, record_value):
        return True, ''

    def test_connection(self):
        return True, ''


def test_error_helper_keeps_the_status_and_bounds_the_body():
    provider = _Probe({'api_key': API_KEY})
    message = provider._error(_Response(403, 'forbidden: key ' + API_KEY))

    assert '403' in message
    assert API_KEY not in message
    assert len(provider._error(_Response(500, 'x' * 5000))) < 600


def test_error_helper_states_the_status_when_the_body_is_empty():
    assert '404' in _Probe({})._error(_Response(404, '', 'Not Found'))


@pytest.mark.parametrize('secret', ['short', '', None, 12345])
def test_redaction_ignores_values_too_short_or_not_text(secret):
    """Contract kept: a 6-character floor, so 'true' is not redacted away."""
    provider = _Probe({'api_key': secret})
    assert provider.redact_secrets('body says short') == 'body says short'
