"""newAccount and account requests on the ACME server and proxy (#410-#413)."""
import base64
import hashlib
import hmac
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from models import db, AcmeClientAccount, AcmeClientOrder, SystemConfig
from models.acme_models import AcmeAccount, AcmeEabCredential
from services.acme import AcmeService
from services.acme.acme_proxy_service import AcmeProxyService
from services.acme.jwk_thumbprint import jwk_thumbprint_or_none

_SLUG = 'acct-tests'
_UPSTREAM = 'https://acme-acct-tests.example/directory'


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def _key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_numbers()
    as_b64 = lambda n: _b64(n.to_bytes((n.bit_length() + 7) // 8, 'big'))  # noqa: E731
    return key, {'kty': 'RSA', 'n': as_b64(pub.n), 'e': as_b64(pub.e)}


def _post(client, path, payload, key, jwk=None, kid=None, raw_payload=None, nonce=None):
    nonce = nonce or client.get('/acme/new-nonce').headers.get('Replay-Nonce', 'n')
    protected = {'alg': 'RS256', 'nonce': nonce, 'url': f'http://localhost{path}'}
    protected.update({'kid': kid} if kid else {'jwk': jwk})
    protected_b64 = _b64(json.dumps(protected).encode())
    if raw_payload is not None:
        payload_b64 = _b64(raw_payload.encode())
    else:
        payload_b64 = '' if payload is None else _b64(json.dumps(payload).encode())
    signature = key.sign(f'{protected_b64}.{payload_b64}'.encode(),
                         padding.PKCS1v15(), hashes.SHA256())
    return client.post(path, data=json.dumps({
        'protected': protected_b64, 'payload': payload_b64, 'signature': _b64(signature),
    }), content_type='application/jose+json')


def _accounts(app, jwk):
    with app.app_context():
        return AcmeAccount.query.filter_by(jwk_thumbprint=jwk_thumbprint_or_none(jwk)).count()


def _set_status(app, jwk, status):
    with app.app_context():
        acct = AcmeAccount.query.filter_by(jwk_thumbprint=jwk_thumbprint_or_none(jwk)).first()
        acct.status = status
        db.session.commit()


def _type(response):
    return response.get_json()['type'].rsplit(':', 1)[-1]


@pytest.fixture(autouse=True)
def _eab_off(app):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='acme_eab_required').first()
        if row:
            row.value = 'false'
            db.session.commit()


@pytest.fixture
def slug_endpoint(app):
    with app.app_context():
        acct = AcmeClientAccount(directory_url=_UPSTREAM, label='Account tests',
                                 email='acct-tests@example.com',
                                 proxy_slug=_SLUG, proxy_enabled=True)
        db.session.add(acct)
        db.session.commit()
        upstream_id = acct.id
    yield upstream_id
    with app.app_context():
        db.session.rollback()
        AcmeClientOrder.query.filter_by(acme_client_account_id=upstream_id).delete()
        AcmeClientAccount.query.filter_by(id=upstream_id).delete()
        db.session.commit()


def _proxy_account(client, slug=None, payload=None):
    key, jwk = _key()
    base = f'/acme/proxy/{slug}' if slug else '/acme/proxy'
    r = _post(client, f'{base}/new-account', payload or {'termsOfServiceAgreed': True},
              key, jwk=jwk)
    assert r.status_code == 201, r.get_json()
    return key, jwk, r.headers['Location']


def _path(url):
    return url.split('http://localhost', 1)[1]


class TestProxyAccountUrl:
    """#410: the Location of a proxy account answers RFC 8555 §7.3.2 and §7.3.6."""

    def test_post_as_get_returns_the_account(self, client):
        key, _, kid = _proxy_account(client)
        r = _post(client, _path(kid), None, key, kid=kid)
        assert r.status_code == 200
        assert r.headers['Location'] == kid
        assert r.get_json()['status'] == 'valid'

    def test_contact_update_is_applied(self, client):
        key, _, kid = _proxy_account(client)
        r = _post(client, _path(kid), {'contact': ['mailto:new@example.com']}, key, kid=kid)
        assert r.status_code == 200
        assert r.get_json()['contact'] == ['mailto:new@example.com']
        again = _post(client, _path(kid), None, key, kid=kid)
        assert again.get_json()['contact'] == ['mailto:new@example.com']

    @pytest.mark.parametrize('contact,error', [
        ('mailto:a@example.com', 'invalidContact'),
        (['https://example.com'], 'unsupportedContact'),
    ])
    def test_bad_contact_update_is_refused_and_not_stored(self, client, contact, error):
        key, _, kid = _proxy_account(client, payload={'contact': ['mailto:old@example.com']})
        r = _post(client, _path(kid), {'contact': contact}, key, kid=kid)
        assert r.status_code == 400 and _type(r) == error
        assert _post(client, _path(kid), None, key, kid=kid).get_json()['contact'] == [
            'mailto:old@example.com']

    def test_deactivation_closes_the_account(self, client):
        key, jwk, kid = _proxy_account(client)
        r = _post(client, _path(kid), {'status': 'deactivated'}, key, kid=kid)
        assert r.status_code == 200 and r.get_json()['status'] == 'deactivated'
        lookup = _post(client, '/acme/proxy/new-account', {'onlyReturnExisting': True},
                       key, jwk=jwk)
        assert lookup.status_code == 401 and _type(lookup) == 'unauthorized'

    def test_another_account_kid_is_refused(self, client):
        _, _, kid = _proxy_account(client)
        other_key, _, other_kid = _proxy_account(client)
        r = _post(client, _path(kid), {'status': 'deactivated'}, other_key, kid=other_kid)
        assert r.status_code == 403 and _type(r) == 'unauthorized'
        assert _post(client, _path(other_kid), None, other_key,
                     kid=other_kid).get_json()['status'] == 'valid'

    def test_a_jwk_signed_request_is_refused(self, client):
        key, jwk, kid = _proxy_account(client)
        r = _post(client, _path(kid), {'status': 'deactivated'}, key, jwk=jwk)
        assert r.status_code == 400 and _type(r) == 'malformed'

    def test_orders_lists_this_account_orders_only(self, app, client, slug_endpoint):
        key, jwk, kid = _proxy_account(client, slug=_SLUG)
        _, other_jwk, _ = _proxy_account(client, slug=_SLUG)
        account_id = kid.rsplit('/', 1)[-1]
        mine = 'https://acme-acct-tests.example/order/mine'
        with app.app_context():
            for url, owner in ((mine, jwk), ('https://acme-acct-tests.example/order/other', other_jwk)):
                db.session.add(AcmeClientOrder(
                    domains='["a.example"]', is_proxy_order=True, upstream_order_url=url,
                    client_jwk_thumbprint=jwk_thumbprint_or_none(owner),
                    acme_client_account_id=slug_endpoint))
            db.session.commit()
        r = _post(client, f'/acme/proxy/{_SLUG}/acct/{account_id}/orders', None, key, kid=kid)
        assert r.status_code == 200
        assert r.get_json()['orders'] == [
            f'http://localhost/acme/proxy/{_SLUG}/order/{AcmeProxyService._proxy_id(mine)}']

    def test_orders_of_another_endpoint_are_not_listed(self, app, client, slug_endpoint):
        key, jwk, kid = _proxy_account(client, slug=_SLUG)
        account_id = kid.rsplit('/', 1)[-1]
        with app.app_context():
            other = AcmeClientAccount(directory_url='https://other.example/directory',
                                      label='Other endpoint', email='other@example.com')
            db.session.add(other)
            db.session.flush()
            db.session.add(AcmeClientOrder(
                domains='["a.example"]', is_proxy_order=True,
                upstream_order_url='https://other.example/order/1',
                client_jwk_thumbprint=jwk_thumbprint_or_none(jwk),
                acme_client_account_id=other.id))
            db.session.commit()
            other_id = other.id
        try:
            r = _post(client, f'/acme/proxy/{_SLUG}/acct/{account_id}/orders', None, key, kid=kid)
            assert r.status_code == 200 and r.get_json()['orders'] == []
        finally:
            with app.app_context():
                AcmeClientOrder.query.filter_by(acme_client_account_id=other_id).delete()
                AcmeClientAccount.query.filter_by(id=other_id).delete()
                db.session.commit()

    def test_orders_is_post_as_get(self, client, slug_endpoint):
        key, _, kid = _proxy_account(client, slug=_SLUG)
        account_id = kid.rsplit('/', 1)[-1]
        r = _post(client, f'/acme/proxy/{_SLUG}/acct/{account_id}/orders', {'x': 1}, key, kid=kid)
        assert r.status_code == 400 and _type(r) == 'malformed'


class TestProxySlug:
    """#411: new-account resolves its slug like /directory does."""

    def test_unknown_slug_is_refused_and_creates_nothing(self, app, client):
        key, jwk = _key()
        r = _post(client, '/acme/proxy/no-such-endpoint/new-account',
                  {'termsOfServiceAgreed': True}, key, jwk=jwk)
        assert r.status_code == 404 and _type(r) == 'malformed'
        assert 'Location' not in r.headers
        assert _accounts(app, jwk) == 0

    def test_disabled_slug_is_refused(self, app, client, slug_endpoint):
        with app.app_context():
            AcmeClientAccount.query.get(slug_endpoint).proxy_enabled = False
            db.session.commit()
        key, jwk = _key()
        r = _post(client, f'/acme/proxy/{_SLUG}/new-account',
                  {'termsOfServiceAgreed': True}, key, jwk=jwk)
        assert r.status_code == 404
        assert _accounts(app, jwk) == 0

    def test_unknown_slug_account_url_is_refused(self, client):
        key, _, kid = _proxy_account(client)
        account_id = kid.rsplit('/', 1)[-1]
        r = _post(client, f'/acme/proxy/no-such-endpoint/acct/{account_id}', None, key, kid=kid)
        assert r.status_code == 404 and _type(r) == 'malformed'

    def test_known_slug_account_url_answers(self, client, slug_endpoint):
        key, _, kid = _proxy_account(client, slug=_SLUG)
        assert kid.startswith(f'http://localhost/acme/proxy/{_SLUG}/acct/')
        assert _post(client, _path(kid), None, key, kid=kid).status_code == 200


_BAD_PAYLOADS = [
    ('[]', 'malformed'),
    ('"x"', 'malformed'),
    ('{"termsOfServiceAgreed": "yes"}', 'malformed'),
    ('{"contact": "mailto:a@example.com"}', 'invalidContact'),
    ('{"contact": ["https://example.com"]}', 'unsupportedContact'),
]


@pytest.mark.parametrize('path', ['/acme/proxy/new-account', '/acme/new-account'])
@pytest.mark.parametrize('raw,error', _BAD_PAYLOADS)
def test_new_account_payload_is_validated(app, client, path, raw, error):
    """#412 on the proxy, and the same rules on the native server."""
    key, jwk = _key()
    r = _post(client, path, None, key, jwk=jwk, raw_payload=raw)
    assert r.status_code == 400, r.get_json()
    assert _type(r) == error
    assert _accounts(app, jwk) == 0


class TestNativeClosedAccounts:
    """#413: the native server refuses deactivated and revoked accounts."""

    @pytest.mark.parametrize('status', ['deactivated', 'revoked'])
    @pytest.mark.parametrize('payload', [
        {'onlyReturnExisting': True},
        {'termsOfServiceAgreed': True},
    ])
    def test_closed_account_is_unauthorized(self, app, client, status, payload):
        key, jwk = _key()
        assert _post(client, '/acme/new-account', {'termsOfServiceAgreed': True},
                     key, jwk=jwk).status_code == 201
        _set_status(app, jwk, status)
        r = _post(client, '/acme/new-account', payload, key, jwk=jwk)
        assert r.status_code == 401 and _type(r) == 'unauthorized'
        assert 'Location' not in r.headers

    @pytest.mark.parametrize('flag', ['false', 'true', 1, 0])
    def test_only_return_existing_must_be_a_boolean(self, app, client, flag):
        key, jwk = _key()
        r = _post(client, '/acme/new-account', {'onlyReturnExisting': flag}, key, jwk=jwk)
        assert r.status_code == 400 and _type(r) == 'malformed'
        assert _accounts(app, jwk) == 0

    def test_valid_account_lookup_still_answers(self, client):
        key, jwk = _key()
        created = _post(client, '/acme/new-account', {'termsOfServiceAgreed': True}, key, jwk=jwk)
        r = _post(client, '/acme/new-account', {'onlyReturnExisting': True}, key, jwk=jwk)
        assert r.status_code == 200
        assert r.headers['Location'] == created.headers['Location']

    def test_account_update_validates_contact(self, client):
        key, jwk = _key()
        kid = _post(client, '/acme/new-account', {'termsOfServiceAgreed': True},
                    key, jwk=jwk).headers['Location']
        r = _post(client, _path(kid), {'contact': 'mailto:a@example.com'}, key, kid=kid)
        assert r.status_code == 400 and _type(r) == 'invalidContact'
        assert _post(client, _path(kid), None, key, kid=kid).get_json()['contact'] == []


@pytest.mark.parametrize('base', ['/acme/proxy', '/acme'])
class TestAccountUrlBothServers:
    """RFC 8555 §7.3.2 and §7.3.6 on the proxy and native account URLs."""

    def _account(self, client, base):
        key, jwk = _key()
        r = _post(client, f'{base}/new-account', {'termsOfServiceAgreed': True}, key, jwk=jwk)
        assert r.status_code == 201, r.get_json()
        return key, r.headers['Location']

    def test_an_echoed_account_object_is_accepted(self, client, base):
        key, kid = self._account(client, base)
        r = _post(client, _path(kid), {
            'status': 'valid', 'contact': ['mailto:new@example.com'],
            'termsOfServiceAgreed': True, 'orders': f'{kid}/orders'}, key, kid=kid)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['status'] == 'valid'
        assert r.get_json()['contact'] == ['mailto:new@example.com']

    def test_a_status_other_than_deactivated_is_ignored(self, client, base):
        key, kid = self._account(client, base)
        r = _post(client, _path(kid), {'status': 'revoked'}, key, kid=kid)
        assert r.status_code == 200 and r.get_json()['status'] == 'valid'

    def test_a_refused_update_changes_nothing(self, client, base):
        key, kid = self._account(client, base)
        r = _post(client, _path(kid), {'status': 'deactivated', 'contact': 'x'}, key, kid=kid)
        assert r.status_code == 400 and _type(r) == 'invalidContact'
        assert _post(client, _path(kid), None, key, kid=kid).get_json()['status'] == 'valid'

    def test_a_deactivated_account_gets_unauthorized(self, client, base):
        key, kid = self._account(client, base)
        assert _post(client, _path(kid), {'status': 'deactivated'}, key, kid=kid).status_code == 200
        r = _post(client, _path(kid), None, key, kid=kid)
        assert r.status_code == 401 and _type(r) == 'unauthorized'


def test_apply_account_update_validates_before_writing():
    from types import SimpleNamespace
    from services.acme.account_requests import AccountRequestError, apply_account_update
    account = SimpleNamespace(status='valid', contact='[]')
    with pytest.raises(AccountRequestError):
        apply_account_update(account, {'status': 'deactivated', 'contact': 'x'})
    assert (account.status, account.contact) == ('valid', '[]')


def _eab(jwk, kid, secret, url):
    protected = _b64(json.dumps({'alg': 'HS256', 'kid': kid, 'url': url}).encode())
    payload = _b64(json.dumps(jwk).encode())
    signature = _b64(hmac.new(secret, f'{protected}.{payload}'.encode(), hashlib.sha256).digest())
    return {'protected': protected, 'payload': payload, 'signature': signature}


@pytest.mark.parametrize('base', ['/acme/proxy', '/acme'])
class TestEabSingleUse:
    """An EAB credential binds one account, on the proxy as on the native server."""

    @pytest.fixture
    def credential(self, app, base):
        kid = 'eab-single-use' + base.replace('/', '-')
        with app.app_context():
            AcmeEabCredential.query.filter_by(kid=kid).delete()
            db.session.add(AcmeEabCredential(kid=kid, hmac_key_b64=_b64(b'eab-secret'),
                                             status='active'))
            db.session.commit()
        yield kid
        with app.app_context():
            AcmeEabCredential.query.filter_by(kid=kid).delete()
            db.session.commit()

    def _register(self, client, base, kid):
        key, jwk = _key()
        eab = _eab(jwk, kid, b'eab-secret', f'http://localhost{base}/new-account')
        r = _post(client, f'{base}/new-account',
                  {'termsOfServiceAgreed': True, 'externalAccountBinding': eab}, key, jwk=jwk)
        return jwk, r

    def test_the_credential_is_bound_to_the_new_account(self, app, client, base, credential):
        _, r = self._register(client, base, credential)
        assert r.status_code == 201, r.get_json()
        with app.app_context():
            row = AcmeEabCredential.query.filter_by(kid=credential).first()
            assert row.status == 'used'
            assert row.used_by_account_id == r.headers['Location'].rsplit('/', 1)[-1]

    def test_a_lost_race_leaves_no_account(self, app, client, monkeypatch, base, credential):
        consume = AcmeService.mark_eab_used

        def _another_registration_wins(service, eab_kid, account_id):
            consume(service, eab_kid, 'another-account')
            return consume(service, eab_kid, account_id)

        monkeypatch.setattr(AcmeService, 'mark_eab_used', _another_registration_wins)
        jwk, r = self._register(client, base, credential)
        assert r.status_code == 400 and _type(r) == 'malformed'
        assert 'Location' not in r.headers
        assert _accounts(app, jwk) == 0


@pytest.mark.parametrize('status', ['deactivated', 'revoked'])
class TestClosedAccountRequests:
    """RFC 8555 §7.3.6: every kid-signed request of a closed account gets 401."""

    @pytest.mark.parametrize('base', ['/acme/proxy', '/acme'])
    @pytest.mark.parametrize('route', ['new-order', 'acct/{id}', 'acct/{id}/orders'])
    def test_a_closed_account_is_unauthorized(self, app, client, status, base, route):
        key, jwk = _key()
        kid = _post(client, f'{base}/new-account', {'termsOfServiceAgreed': True},
                    key, jwk=jwk).headers['Location']
        _set_status(app, jwk, status)
        path = f"{base}/{route.format(id=kid.rsplit('/', 1)[-1])}"
        payload = ({'identifiers': [{'type': 'dns', 'value': 'a.example.com'}]}
                   if route == 'new-order' else None)
        r = _post(client, path, payload, key, kid=kid)
        assert r.status_code == 401 and _type(r) == 'unauthorized', r.get_json()

    @pytest.mark.parametrize('base', ['/acme/proxy', '/acme'])
    @pytest.mark.parametrize('route', ['new-order', 'acct/{id}', 'acct/{id}/orders'])
    def test_a_bad_signature_is_malformed_not_unauthorized(self, app, client, status, base, route):
        """The status is told only to the holder of the account key."""
        key, jwk = _key()
        kid = _post(client, f'{base}/new-account', {'termsOfServiceAgreed': True},
                    key, jwk=jwk).headers['Location']
        _set_status(app, jwk, status)
        other_key, _ = _key()
        path = f"{base}/{route.format(id=kid.rsplit('/', 1)[-1])}"
        r = _post(client, path, None, other_key, kid=kid)
        assert r.status_code == 400 and _type(r) == 'malformed', r.get_json()


@pytest.mark.parametrize('base', ['/acme/proxy', '/acme'])
class TestJwsProblemTypes:
    """RFC 8555 §6.7: a JWS failure carries its registered problem type on both servers."""

    @pytest.mark.parametrize('route', ['new-order', 'order/abc', 'revoke-cert'])
    def test_an_unknown_kid_is_account_does_not_exist(self, client, base, route):
        key, _ = _key()
        r = _post(client, f'{base}/{route}', {}, key, kid=f'http://localhost{base}/acct/nope')
        assert r.status_code == 400 and _type(r) == 'accountDoesNotExist', r.get_json()

    def test_a_stale_nonce_is_bad_nonce(self, client, base):
        key, jwk = _key()
        r = _post(client, f'{base}/new-account', {'termsOfServiceAgreed': True}, key, jwk=jwk,
                  nonce='not-a-nonce-this-server-issued')
        assert r.status_code == 400 and _type(r) == 'badNonce', r.get_json()
        assert r.headers.get('Replay-Nonce')

    def test_a_stale_nonce_says_what_acme_sh_looks_for(self, client, base):
        key, jwk = _key()
        r = _post(client, f'{base}/new-account', {'termsOfServiceAgreed': True}, key, jwk=jwk,
                  nonce='not-a-nonce-this-server-issued')
        assert 'JWS has an invalid anti-replay nonce' in r.get_json()['detail']

    def test_an_eab_with_an_unusable_key_is_malformed(self, app, client, base):
        kid = 'eab-bad-key' + base.replace('/', '-')
        with app.app_context():
            AcmeEabCredential.query.filter_by(kid=kid).delete()
            db.session.add(AcmeEabCredential(kid=kid, hmac_key_b64=_b64(b'eab-secret'),
                                             status='active'))
            db.session.commit()
        try:
            key, jwk = _key()
            eab = _eab({'kty': 'oct', 'k': 'AAAA'}, kid, b'eab-secret',
                       f'http://localhost{base}/new-account')
            r = _post(client, f'{base}/new-account',
                      {'termsOfServiceAgreed': True, 'externalAccountBinding': eab}, key, jwk=jwk)
            assert r.status_code == 400 and _type(r) == 'malformed', r.get_json()
        finally:
            with app.app_context():
                AcmeEabCredential.query.filter_by(kid=kid).delete()
                db.session.commit()

    def test_an_unusable_key_is_bad_public_key(self, client, base):
        key, jwk = _key()
        r = _post(client, f'{base}/new-account', {'termsOfServiceAgreed': True}, key,
                  jwk={'kty': 'oct', 'k': 'AAAA'})
        assert r.status_code == 400 and _type(r) == 'badPublicKey', r.get_json()


def _set_eab_required(app, on):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='acme_eab_required').first()
        if row is None:
            row = SystemConfig(key='acme_eab_required')
            db.session.add(row)
        row.value = 'true' if on else 'false'
        db.session.commit()


@pytest.mark.parametrize('base', ['/acme/proxy', '/acme'])
class TestKnownKeyBeforeEab:
    """RFC 8555 §7.3.1: a known key gets its account back before any EAB check."""

    @pytest.fixture(autouse=True)
    def _eab_off_after(self, app):
        yield
        _set_eab_required(app, False)

    def _create(self, client, base):
        key, jwk = _key()
        r = _post(client, f'{base}/new-account', {'termsOfServiceAgreed': True}, key, jwk=jwk)
        assert r.status_code == 201, r.get_json()
        return key, jwk, r.headers['Location']

    def test_no_eab_returns_the_account(self, app, client, base):
        key, jwk, kid = self._create(client, base)
        _set_eab_required(app, True)
        r = _post(client, f'{base}/new-account', {'termsOfServiceAgreed': True}, key, jwk=jwk)
        assert r.status_code == 200, r.get_json()
        assert r.headers['Location'] == kid
        assert _accounts(app, jwk) == 1

    def test_a_used_eab_returns_the_account(self, app, client, base):
        cred = 'eab-known-key' + base.replace('/', '-')
        with app.app_context():
            AcmeEabCredential.query.filter_by(kid=cred).delete()
            db.session.add(AcmeEabCredential(kid=cred, hmac_key_b64=_b64(b'eab-secret'),
                                             status='active'))
            db.session.commit()
        _set_eab_required(app, True)
        try:
            key, jwk = _key()
            url = f'http://localhost{base}/new-account'
            payload = {'termsOfServiceAgreed': True,
                       'externalAccountBinding': _eab(jwk, cred, b'eab-secret', url)}
            first = _post(client, f'{base}/new-account', payload, key, jwk=jwk)
            assert first.status_code == 201, first.get_json()
            payload['externalAccountBinding'] = _eab(jwk, cred, b'eab-secret', url)
            r = _post(client, f'{base}/new-account', payload, key, jwk=jwk)
            assert r.status_code == 200, r.get_json()
            assert r.headers['Location'] == first.headers['Location']
            assert _accounts(app, jwk) == 1
        finally:
            with app.app_context():
                AcmeEabCredential.query.filter_by(kid=cred).delete()
                db.session.commit()

    def test_a_closed_account_is_still_unauthorized(self, app, client, base):
        key, jwk, _ = self._create(client, base)
        _set_status(app, jwk, 'deactivated')
        _set_eab_required(app, True)
        r = _post(client, f'{base}/new-account', {'termsOfServiceAgreed': True}, key, jwk=jwk)
        assert r.status_code == 401 and _type(r) == 'unauthorized'

    def test_an_unknown_key_still_needs_eab(self, app, client, base):
        _set_eab_required(app, True)
        key, jwk = _key()
        r = _post(client, f'{base}/new-account', {'termsOfServiceAgreed': True}, key, jwk=jwk)
        assert r.status_code == 400 and _type(r) == 'externalAccountRequired'
        assert _accounts(app, jwk) == 0
