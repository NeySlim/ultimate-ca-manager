"""The ACME proxy judges an identifier by the same rules as the ACME server.

Both front doors take an `identifiers` array straight from an unauthenticated
client. The server refuses a value that carries a port, userinfo, a scheme, a
path, whitespace, an over-long or empty label. The proxy refused only a
non-`dns` *type*, so such a value went into `AcmeClientOrder.domains`, reached
the configured DNS provider's API as a record name, and was forwarded verbatim
upstream. A name like `169.254.169.254:80` does not resolve as a host, so the
challenge validator's address guard never fired on it, while an HTTP client
re-parsing it as a URL authority strips the port and reaches what is behind.

`services/acme/identifiers.py` holds the rules; both doors call them.

The rules are syntax, not policy. UCM is deployed on LAN, so the names an
on-prem operator really orders -- `localhost`, `host-1.internal.lan`,
wildcards, punycode, a trailing root dot -- must keep working, and the second
class below is what says so.
"""
import json
from unittest.mock import MagicMock

import pytest

from services.acme.identifiers import validate_acme_identifier


MALFORMED = [
    '169.254.169.254:80',
    'evil@169.254.169.254',
    '127.0.0.1:8080',
    '169.254.169.254/latest/meta-data/#',
    'host with space.example.com',
    'http://example.com',
    'example.com:443',
    'x' * 250 + '.example.com',
    # Every label legal on its own, 255 characters in total: only the
    # whole-name ceiling refuses this one.
    '.'.join(['a' * 60] * 4) + '.example.com',
    '-leading-hyphen.example.com',
    'a..example.com',
]

# Every one of these is accepted by the ACME server's own new-order
# (tests/test_acme_dns_identifier_ssrf.py pins them), so the proxy must not
# start refusing them.
LEGITIMATE = [
    'example.com',
    '*.example.com',
    'sub.example.co.uk',
    'xn--80ak6aa92e.com',
    'host-1.internal.lan',
    'EXAMPLE.com',
    'example.com.',
    '_acme-challenge.example.com',
    'localhost',
    'ucm.lan',
]


def _post_new_order(client, monkeypatch, identifiers):
    """Drive the proxy's new-order up to its account check."""
    from api.acme import acme_proxy_api

    service_factory = MagicMock()
    payload = {'identifiers': identifiers}
    monkeypatch.setattr(acme_proxy_api, 'verify_proxy_jws',
                        lambda: (True, payload, None, None))
    monkeypatch.setattr(acme_proxy_api, 'get_proxy_service', service_factory)
    monkeypatch.setattr(acme_proxy_api, '_kid_account_thumbprint',
                        lambda _protected: None)

    response = client.post(
        '/acme/proxy/new-order',
        data=json.dumps({'protected': 'stub', 'payload': 'stub',
                         'signature': 'stub'}),
        content_type='application/jose+json',
    )
    return response, service_factory


class TestTheProxyRefusesWhatTheServerRefuses:
    @pytest.mark.parametrize('value', MALFORMED)
    def test_a_malformed_dns_identifier_is_refused(self, client, monkeypatch, value):
        # The rule, as the server states it.
        ok, err_type, detail = validate_acme_identifier({'type': 'dns', 'value': value})
        assert (ok, err_type, detail) == (False, 'malformed',
                                          'Malformed DNS identifier value')

        response, service_factory = _post_new_order(
            client, monkeypatch, [{'type': 'dns', 'value': value}])

        assert response.status_code == 400, response.data
        body = response.get_json()
        assert body['type'] == 'urn:ietf:params:acme:error:malformed'
        assert body['detail'] == 'Malformed DNS identifier value'
        # Refused before anything was relayed upstream.
        service_factory.assert_not_called()

    def test_a_value_that_is_not_a_string_is_refused(self, client, monkeypatch):
        response, service_factory = _post_new_order(
            client, monkeypatch, [{'type': 'dns', 'value': 12345}])
        assert response.status_code == 400, response.data
        assert response.get_json()['detail'] == 'Malformed DNS identifier value'
        service_factory.assert_not_called()

    def test_one_bad_identifier_among_good_ones_is_enough(self, client, monkeypatch):
        response, service_factory = _post_new_order(client, monkeypatch, [
            {'type': 'dns', 'value': 'good.example.com'},
            {'type': 'dns', 'value': 'example.com:443'},
        ])
        assert response.status_code == 400, response.data
        assert response.get_json()['detail'] == 'Malformed DNS identifier value'
        service_factory.assert_not_called()


class TestTheProxyStillAcceptsWhatAnOnPremDeploymentOrders:
    @pytest.mark.parametrize('value', LEGITIMATE)
    def test_a_legitimate_name_is_not_refused(self, client, monkeypatch, value):
        ok, _err_type, _detail = validate_acme_identifier(
            {'type': 'dns', 'value': value})
        assert ok is True, f'the server accepts {value!r}'

        response, _ = _post_new_order(
            client, monkeypatch, [{'type': 'dns', 'value': value}])

        # It reaches the next gate, the account check, untouched by the
        # syntax rules.
        body = response.get_json()
        assert body['type'] == 'urn:ietf:params:acme:error:malformed', response.data
        assert 'kid' in body['detail'].lower(), response.data


class TestTheOlderRefusalsAreUnchanged:
    def test_an_ip_identifier_is_still_an_unsupported_identifier(
            self, client, monkeypatch):
        response, service_factory = _post_new_order(
            client, monkeypatch, [{'type': 'ip', 'value': '192.0.2.44'}])
        body = response.get_json()
        assert response.status_code == 400
        assert body['type'] == 'urn:ietf:params:acme:error:unsupportedIdentifier'
        assert 'dns-01' in body['detail']
        service_factory.assert_not_called()

    def test_a_missing_identifiers_array_is_still_malformed(
            self, client, monkeypatch):
        response, _ = _post_new_order(client, monkeypatch, [])
        assert response.status_code == 400
        assert response.get_json()['detail'] == "Missing 'identifiers' in payload"

    def test_a_non_array_identifiers_is_still_malformed(self, client, monkeypatch):
        response, _ = _post_new_order(client, monkeypatch, 'abc')
        assert response.status_code == 400
        assert response.get_json()['type'] == 'urn:ietf:params:acme:error:malformed'
