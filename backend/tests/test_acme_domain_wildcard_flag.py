"""A domain entry with "Allow wildcard" off refuses `*.` identifiers.

The flag was stored and shown, and neither new-order looked at it: both the
ACME server and the ACME proxy issued a wildcard for such a domain.
"""
import json
import uuid

import pytest

from models import db
from models.acme_models import AcmeDomain, DnsProvider
from tests.test_acme_proxy_identifier_syntax import _post_new_order
from tests.test_acme_security_paths import _build_jws, _nonce, acme_account  # noqa: F401


@pytest.fixture
def domain_entry(app):
    zone = f'wc{uuid.uuid4().hex[:8]}.example.com'
    with app.app_context():
        provider = DnsProvider(name=f'wc-{zone}', provider_type='manual', credentials='{}')
        db.session.add(provider)
        db.session.flush()
        entry = AcmeDomain(domain=zone, dns_provider_id=provider.id, is_wildcard_allowed=False)
        db.session.add(entry)
        db.session.commit()
        ids = (entry.id, provider.id)
    yield zone
    with app.app_context():
        db.session.delete(db.session.get(AcmeDomain, ids[0]))
        db.session.delete(db.session.get(DnsProvider, ids[1]))
        db.session.commit()


def _set_flag(app, zone, allowed):
    with app.app_context():
        AcmeDomain.query.filter_by(domain=zone).first().is_wildcard_allowed = allowed
        db.session.commit()


def _server_new_order(client, account, value):
    path = '/acme/new-order'
    jws = _build_jws(f'http://localhost{path}', {'identifiers': [{'type': 'dns', 'value': value}]},
                     account['key'], kid=f'http://localhost/acme/acct/{account["account_id"]}',
                     nonce=_nonce(client))
    return client.post(path, data=json.dumps(jws), content_type='application/jose+json')


class TestServer:
    def test_wildcard_refused_when_the_entry_disallows_it(self, app, client, acme_account, domain_entry):
        r = _server_new_order(client, acme_account, f'*.{domain_entry}')
        assert r.status_code == 400, r.data
        body = r.get_json()
        assert body['type'] == 'urn:ietf:params:acme:error:rejectedIdentifier'
        assert body['subproblems'][0]['identifier']['value'] == f'*.{domain_entry}'

    def test_a_wildcard_under_a_subdomain_is_refused_too(self, app, client, acme_account, domain_entry):
        r = _server_new_order(client, acme_account, f'*.sub.{domain_entry}')
        assert r.status_code == 400, r.data

    def test_plain_names_are_unaffected(self, app, client, acme_account, domain_entry):
        assert _server_new_order(client, acme_account, f'host.{domain_entry}').status_code == 201

    def test_wildcard_accepted_when_allowed(self, app, client, acme_account, domain_entry):
        _set_flag(app, domain_entry, True)
        assert _server_new_order(client, acme_account, f'*.{domain_entry}').status_code == 201


class TestProxy:
    def test_wildcard_refused_when_the_entry_disallows_it(self, app, client, monkeypatch, domain_entry):
        r, service_factory = _post_new_order(client, monkeypatch, [{'type': 'dns', 'value': f'*.{domain_entry}'}])
        assert r.status_code == 400, r.data
        assert r.get_json()['type'] == 'urn:ietf:params:acme:error:rejectedIdentifier'
        service_factory.assert_not_called()

    def test_wildcard_not_refused_when_allowed(self, app, client, monkeypatch, domain_entry):
        _set_flag(app, domain_entry, True)
        r, _ = _post_new_order(client, monkeypatch, [{'type': 'dns', 'value': f'*.{domain_entry}'}])
        # Past the wildcard rule: the stub stops at the account check.
        assert r.get_json()['type'] != 'urn:ietf:params:acme:error:rejectedIdentifier'
