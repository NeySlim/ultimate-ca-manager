"""DNS provider forms and routes agree: alwaysdata account is optional, Cloudflare takes a token or key and email."""
import uuid

import pytest

from models import db
from models.acme_models import DnsProvider


def _post(auth_client, ptype, creds):
    r = auth_client.post('/api/v2/dns-providers', json={
        'name': f'rep24b-{uuid.uuid4().hex[:8]}', 'provider_type': ptype, 'credentials': creds})
    return r


def _drop(app, r):
    if r.status_code == 201:
        with app.app_context():
            row = db.session.get(DnsProvider, r.get_json()['data']['id'])
            if row:
                db.session.delete(row)
                db.session.commit()


def test_alwaysdata_account_is_optional(app, auth_client):
    r = _post(auth_client, 'alwaysdata', {'api_key': 'k' * 20})
    try:
        assert r.status_code == 201, r.data[:300]
    finally:
        _drop(app, r)


def test_alwaysdata_account_is_not_required_in_schema():
    from services.acme.dns_providers.alwaysdata import AlwaysdataDnsProvider as P
    req = {f['name']: f['required'] for f in P.get_credential_schema()}
    assert req == {'api_key': True, 'account': False}


@pytest.mark.parametrize('account,user', [
    (None, 'tok'), ('', 'tok'), ('acme', 'tok account=acme')])
def test_alwaysdata_sends_the_account_when_given(monkeypatch, account, user):
    from services.acme.dns_providers import alwaysdata as mod
    seen = {}

    class R:
        status_code = 200
        text = '[]'

        def json(self):
            return []

    def fake(method, url, **kw):
        seen['auth'] = kw['auth']
        return R()
    monkeypatch.setattr(mod.requests, 'request', fake)
    creds = {'api_key': 'tok'}
    if account is not None:
        creds['account'] = account
    mod.AlwaysdataDnsProvider(creds).test_connection()
    assert seen['auth'] == (user, '')


@pytest.mark.parametrize('creds,status', [
    ({'api_token': 't' * 40}, 201),
    ({'api_key': 'k' * 37, 'email': 'ops@example.com'}, 201),
    ({'api_key': 'k' * 37}, 400),
    ({'email': 'ops@example.com'}, 400),
    ({}, 400),
])
def test_cloudflare_create_takes_token_or_key_and_email(app, auth_client, creds, status):
    r = _post(auth_client, 'cloudflare', creds)
    try:
        assert r.status_code == status, r.data[:300]
    finally:
        _drop(app, r)
