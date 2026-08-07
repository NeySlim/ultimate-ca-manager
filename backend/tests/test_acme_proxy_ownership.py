"""#260 — ACME proxy resource ownership.

The proxy's authz, challenge, get_order and cert endpoints verified the JWS
signature but never checked that the requesting account owned the resource:
any registered account could read any other account's authorization status,
challenge details, order status, and download their certificates by
enumerating the base64-encoded upstream URLs.

Service-level tests cover the binding logic (deny cross-account, fail closed
on missing identity, fail open on legacy unbound rows, 404 on untracked
resources — upstream must never be contacted on a denial). Endpoint-level
tests prove the HTTP wiring: 403 unauthorized / 404 for a foreign account,
200 for the owner (including the challenge happy path).
"""
import base64
import hashlib
import json

import pytest

from models import db, SystemConfig, AcmeAccount, AcmeClientAccount, AcmeClientOrder
from services.acme.acme_proxy_account import PROXY_ACCOUNT_ID_KEY
from services.acme.acme_proxy_service import (
    AcmeProxyService,
    ProxyResourceNotFoundError,
)

_STUB_DIRECTORY_URL = 'https://acme-stub.example/directory'
UPSTREAM = 'https://acme-stub.example'

ORDER_URL = f'{UPSTREAM}/acme/order/owner/1'
AUTHZ_URL = f'{UPSTREAM}/acme/authz-v3/111'
CHALL_URL = f'{UPSTREAM}/acme/chall-v3/111/AbCdEf'
CERT_URL = f'{UPSTREAM}/acme/cert/aaa'


def _b64(url: str) -> str:
    return base64.urlsafe_b64encode(url.encode()).rstrip(b'=').decode()


def _seed_order(**overrides):
    kwargs = dict(
        domains='["owned.example.com"]',
        environment='staging',
        challenge_type='dns-01',
        status='pending',
        order_url=ORDER_URL,
        upstream_order_url=ORDER_URL,
        upstream_authz_urls=json.dumps([AUTHZ_URL]),
        certificate_url=CERT_URL,
        is_proxy_order=True,
        account_id='acct-owner-1',
        client_jwk_thumbprint='thumb-owner-1',
    )
    kwargs.update(overrides)
    order = AcmeClientOrder(**kwargs)
    db.session.add(order)
    db.session.commit()
    return order


@pytest.fixture(autouse=True)
def _clean_orders(app):
    with app.app_context():
        AcmeClientOrder.query.filter_by(
            domains='["owned.example.com"]'
        ).delete()
        db.session.commit()
        yield
        AcmeClientOrder.query.filter_by(
            domains='["owned.example.com"]'
        ).delete()
        db.session.commit()


def _make_svc(app, monkeypatch, upstream_response=None):
    with app.app_context():
        svc = AcmeProxyService('https://ucm.example/acme/proxy')
    svc.upstream_directory_url = _STUB_DIRECTORY_URL

    if upstream_response is None:
        def _no_upstream(*_a, **_k):
            raise AssertionError('upstream must not be called on a denial')
        monkeypatch.setattr(svc, '_post_with_account', _no_upstream)
    else:
        monkeypatch.setattr(
            svc, '_post_with_account', lambda *_a, **_k: upstream_response,
        )
    return svc


class _FakeResp:
    def __init__(self, payload, headers=None, status_code=200):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = json.dumps(payload)
        self.content = self.text.encode()

    def json(self):
        return self._payload


class TestOrderOwnership:
    def test_cross_account_denied(self, app, monkeypatch):
        with app.app_context():
            _seed_order()
            svc = _make_svc(app, monkeypatch)
            with pytest.raises(PermissionError):
                svc.get_order(
                    _b64(ORDER_URL),
                    requester_account_id='acct-intruder',
                    requester_thumbprint='thumb-intruder',
                )

    def test_no_identity_on_bound_order_denied(self, app, monkeypatch):
        with app.app_context():
            _seed_order()
            svc = _make_svc(app, monkeypatch)
            with pytest.raises(PermissionError):
                svc.get_order(_b64(ORDER_URL))

    def test_owner_allowed(self, app, monkeypatch):
        upstream = _FakeResp({'status': 'valid', 'finalize': f'{ORDER_URL}/finalize'})
        with app.app_context():
            _seed_order()
            svc = _make_svc(app, monkeypatch, upstream_response=upstream)
            data = svc.get_order(
                _b64(ORDER_URL),
                requester_account_id='acct-owner-1',
                requester_thumbprint='thumb-owner-1',
            )
            assert data['status'] == 'valid'

    def test_legacy_unbound_order_allowed(self, app, monkeypatch):
        upstream = _FakeResp({'status': 'valid', 'finalize': f'{ORDER_URL}/finalize'})
        with app.app_context():
            _seed_order(account_id=None, client_jwk_thumbprint=None)
            svc = _make_svc(app, monkeypatch, upstream_response=upstream)
            data = svc.get_order(
                _b64(ORDER_URL),
                requester_account_id='acct-anyone',
                requester_thumbprint='thumb-anyone',
            )
            assert data['status'] == 'valid'

    def test_untracked_order_not_found(self, app, monkeypatch):
        with app.app_context():
            svc = _make_svc(app, monkeypatch)
            with pytest.raises(ProxyResourceNotFoundError):
                svc.get_order(
                    _b64(f'{UPSTREAM}/acme/order/ghost/9'),
                    requester_account_id='acct-owner-1',
                    requester_thumbprint='thumb-owner-1',
                )


class TestAuthzOwnership:
    def test_cross_account_denied_before_upstream(self, app, monkeypatch):
        with app.app_context():
            _seed_order()
            svc = _make_svc(app, monkeypatch)
            with pytest.raises(PermissionError):
                svc.get_authz(
                    _b64(AUTHZ_URL),
                    requester_account_id='acct-intruder',
                    requester_thumbprint='thumb-intruder',
                )

    def test_untracked_authz_not_found(self, app, monkeypatch):
        with app.app_context():
            svc = _make_svc(app, monkeypatch)
            with pytest.raises(ProxyResourceNotFoundError):
                svc.get_authz(
                    _b64(f'{UPSTREAM}/acme/authz-v3/999'),
                    requester_account_id='acct-owner-1',
                    requester_thumbprint='thumb-owner-1',
                )

    def test_owner_allowed(self, app, monkeypatch):
        upstream = _FakeResp({
            'status': 'valid',
            'identifier': {'type': 'dns', 'value': 'owned.example.com'},
            'challenges': [
                {'type': 'dns-01', 'url': CHALL_URL, 'status': 'valid', 'token': 't'},
            ],
        })
        with app.app_context():
            _seed_order()
            svc = _make_svc(app, monkeypatch, upstream_response=upstream)
            result = svc.get_authz(
                _b64(AUTHZ_URL),
                requester_account_id='acct-owner-1',
                requester_thumbprint='thumb-owner-1',
            )
            assert result is not None
            data, identifier = result
            assert identifier['value'] == 'owned.example.com'
            assert data['challenges'][0]['type'] == 'dns-01'


class TestChallengeOwnership:
    """The owning order is resolved through the authz URL upstream returns in
    Link rel="up" — challenge and authz URLs live in disjoint namespaces, so
    the URL itself can never be matched against the stored authz URLs."""

    def _upstream_challenge(self, status='valid'):
        return _FakeResp(
            {'type': 'dns-01', 'url': CHALL_URL, 'status': status, 'token': 't'},
            headers={'Link': f'<{AUTHZ_URL}>;rel="up"'},
        )

    def test_cross_account_denied(self, app, monkeypatch):
        with app.app_context():
            _seed_order()
            svc = _make_svc(
                app, monkeypatch, upstream_response=self._upstream_challenge(),
            )
            with pytest.raises(PermissionError):
                svc.respond_challenge(
                    _b64(CHALL_URL),
                    requester_account_id='acct-intruder',
                    requester_thumbprint='thumb-intruder',
                )

    def test_owner_happy_path(self, app, monkeypatch):
        with app.app_context():
            _seed_order()
            svc = _make_svc(
                app, monkeypatch, upstream_response=self._upstream_challenge(),
            )
            data, link = svc.respond_challenge(
                _b64(CHALL_URL),
                requester_account_id='acct-owner-1',
                requester_thumbprint='thumb-owner-1',
            )
            assert data['status'] == 'valid'
            assert data['url'].startswith('https://ucm.example/acme/proxy/challenge/')
            assert link is not None and 'rel="up"' in link

    def test_unmatched_challenge_not_found(self, app, monkeypatch):
        upstream = _FakeResp(
            {'type': 'dns-01', 'url': CHALL_URL, 'status': 'valid', 'token': 't'},
            headers={'Link': f'<{UPSTREAM}/acme/authz-v3/999>;rel="up"'},
        )
        with app.app_context():
            _seed_order(status='valid')  # nothing pending for the loose fallback
            svc = _make_svc(app, monkeypatch, upstream_response=upstream)
            with pytest.raises(ProxyResourceNotFoundError):
                svc.respond_challenge(
                    _b64(CHALL_URL),
                    requester_account_id='acct-owner-1',
                    requester_thumbprint='thumb-owner-1',
                )


class TestCertificateOwnership:
    def test_cross_account_denied_before_upstream(self, app, monkeypatch):
        with app.app_context():
            _seed_order()
            svc = _make_svc(app, monkeypatch)
            with pytest.raises(PermissionError):
                svc.get_certificate(
                    _b64(CERT_URL),
                    requester_account_id='acct-intruder',
                    requester_thumbprint='thumb-intruder',
                )

    def test_untracked_certificate_not_found(self, app, monkeypatch):
        with app.app_context():
            svc = _make_svc(app, monkeypatch)
            monkeypatch.setattr(
                svc, '_find_order_for_certificate', lambda _url: None,
            )
            with pytest.raises(ProxyResourceNotFoundError):
                svc.get_certificate(
                    _b64(f'{UPSTREAM}/acme/cert/ghost'),
                    requester_account_id='acct-owner-1',
                    requester_thumbprint='thumb-owner-1',
                )

    def test_owner_not_denied(self, app, monkeypatch):
        with app.app_context():
            _seed_order()
            svc = _make_svc(
                app, monkeypatch,
                upstream_response=_FakeResp({}, status_code=404),
            )
            try:
                svc.get_certificate(
                    _b64(CERT_URL),
                    requester_account_id='acct-owner-1',
                    requester_thumbprint='thumb-owner-1',
                )
            except PermissionError:
                pytest.fail('owner must not be denied their own certificate')
            except ProxyResourceNotFoundError:
                pytest.fail('tracked certificate must resolve for its owner')
            except Exception:
                pass  # upstream/parsing behaviour is out of scope here


# ---------------------------------------------------------------------------
# Endpoint-level: full JWS round-trip through the Flask routes.
# ---------------------------------------------------------------------------

def _generate_rsa_key_and_jwk():
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = private_key.public_key().public_numbers()

    def int_to_b64(n):
        b = n.to_bytes((n.bit_length() + 7) // 8, 'big')
        return base64.urlsafe_b64encode(b).rstrip(b'=').decode()

    jwk = {'kty': 'RSA', 'n': int_to_b64(pub.n), 'e': int_to_b64(pub.e)}
    return private_key, jwk


def _build_jws(url, payload, jwk, private_key, nonce='test-nonce', use_kid=None):
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes

    protected = {'alg': 'RS256', 'nonce': nonce, 'url': url}
    if use_kid:
        protected['kid'] = use_kid
    else:
        protected['jwk'] = jwk

    protected_b64 = base64.urlsafe_b64encode(
        json.dumps(protected).encode()
    ).rstrip(b'=').decode()

    if payload is not None:
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b'=').decode()
    else:
        payload_b64 = ''

    signing_input = f'{protected_b64}.{payload_b64}'.encode()
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()

    return {'protected': protected_b64, 'payload': payload_b64, 'signature': sig_b64}


def _get_nonce(client):
    r = client.get('/acme/proxy/new-nonce')
    return r.headers.get('Replay-Nonce', 'fallback-nonce')


def _register_account(client, private_key, jwk):
    nonce = _get_nonce(client)
    jws = _build_jws(
        'http://localhost/acme/proxy/new-account',
        {'termsOfServiceAgreed': True}, jwk, private_key, nonce=nonce,
    )
    r = client.post(
        '/acme/proxy/new-account',
        data=json.dumps(jws),
        content_type='application/jose+json',
    )
    assert r.status_code == 201
    return r.headers['Location']  # kid


@pytest.fixture
def proxy_upstream_stub(app, monkeypatch):
    from tests.acme_proxy_upstream_stub import stub_acme_proxy_upstream
    stub_acme_proxy_upstream(monkeypatch)

    with app.app_context():
        SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).delete()
        AcmeClientAccount.query.filter_by(
            directory_url=_STUB_DIRECTORY_URL
        ).delete()
        db.session.commit()
        acct = AcmeClientAccount(
            directory_url=_STUB_DIRECTORY_URL,
            label='Proxy Ownership Stub',
            email='proxy-ownership@example.com',
        )
        db.session.add(acct)
        db.session.commit()
        db.session.add(SystemConfig(
            key=PROXY_ACCOUNT_ID_KEY,
            value=str(acct.id),
            description='test proxy ownership',
        ))
        db.session.commit()
    yield
    with app.app_context():
        SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).delete()
        AcmeClientAccount.query.filter_by(
            directory_url=_STUB_DIRECTORY_URL
        ).delete()
        db.session.commit()


class TestEndpointOwnership:
    def _seed_alice_order(self, app, alice_kid):
        """Order owned by the account behind alice_kid (real stored binding)."""
        with app.app_context():
            alice_account_id = alice_kid.rstrip('/').rsplit('/', 1)[-1]
            alice = AcmeAccount.query.filter_by(account_id=alice_account_id).first()
            assert alice is not None
            _seed_order(
                account_id=alice_account_id,
                client_jwk_thumbprint=alice.jwk_thumbprint,
            )

    def _post_as_get(self, client, path, private_key, kid):
        nonce = _get_nonce(client)
        jws = _build_jws(
            f'http://localhost{path}', None, None, private_key,
            nonce=nonce, use_kid=kid,
        )
        return client.post(
            path, data=json.dumps(jws), content_type='application/jose+json',
        )

    def test_order_poll_cross_account_403_owner_200(
        self, app, client, monkeypatch, proxy_upstream_stub,
    ):
        alice_key, alice_jwk = _generate_rsa_key_and_jwk()
        bob_key, bob_jwk = _generate_rsa_key_and_jwk()
        alice_kid = _register_account(client, alice_key, alice_jwk)
        bob_kid = _register_account(client, bob_key, bob_jwk)
        self._seed_alice_order(app, alice_kid)

        upstream = _FakeResp({'status': 'valid', 'finalize': f'{ORDER_URL}/finalize'})
        monkeypatch.setattr(
            AcmeProxyService, '_post_with_account',
            lambda self, *_a, **_k: upstream,
        )

        path = f'/acme/proxy/order/{_b64(ORDER_URL)}'
        r_bob = self._post_as_get(client, path, bob_key, bob_kid)
        assert r_bob.status_code == 403
        assert 'unauthorized' in r_bob.get_json()['type']

        r_alice = self._post_as_get(client, path, alice_key, alice_kid)
        assert r_alice.status_code == 200
        assert r_alice.get_json()['status'] == 'valid'

    def test_challenge_cross_account_403_owner_200(
        self, app, client, monkeypatch, proxy_upstream_stub,
    ):
        alice_key, alice_jwk = _generate_rsa_key_and_jwk()
        bob_key, bob_jwk = _generate_rsa_key_and_jwk()
        alice_kid = _register_account(client, alice_key, alice_jwk)
        bob_kid = _register_account(client, bob_key, bob_jwk)
        self._seed_alice_order(app, alice_kid)

        upstream = _FakeResp(
            {'type': 'dns-01', 'url': CHALL_URL, 'status': 'valid', 'token': 't'},
            headers={'Link': f'<{AUTHZ_URL}>;rel="up"'},
        )
        monkeypatch.setattr(
            AcmeProxyService, '_post_with_account',
            lambda self, *_a, **_k: upstream,
        )

        path = f'/acme/proxy/challenge/{_b64(CHALL_URL)}'
        r_bob = self._post_as_get(client, path, bob_key, bob_kid)
        assert r_bob.status_code == 403
        assert 'unauthorized' in r_bob.get_json()['type']

        r_alice = self._post_as_get(client, path, alice_key, alice_kid)
        assert r_alice.status_code == 200
        assert r_alice.get_json()['status'] == 'valid'

    def test_authz_cross_account_403(
        self, app, client, monkeypatch, proxy_upstream_stub,
    ):
        alice_key, alice_jwk = _generate_rsa_key_and_jwk()
        bob_key, bob_jwk = _generate_rsa_key_and_jwk()
        alice_kid = _register_account(client, alice_key, alice_jwk)
        bob_kid = _register_account(client, bob_key, bob_jwk)
        self._seed_alice_order(app, alice_kid)

        def _no_upstream(self, *_a, **_k):
            raise AssertionError('upstream must not be called for a denied authz')
        monkeypatch.setattr(AcmeProxyService, '_post_with_account', _no_upstream)

        path = f'/acme/proxy/authz/{_b64(AUTHZ_URL)}'
        r_bob = self._post_as_get(client, path, bob_key, bob_kid)
        assert r_bob.status_code == 403
        assert 'unauthorized' in r_bob.get_json()['type']

    def test_cert_cross_account_403_and_untracked_404(
        self, app, client, monkeypatch, proxy_upstream_stub,
    ):
        alice_key, alice_jwk = _generate_rsa_key_and_jwk()
        bob_key, bob_jwk = _generate_rsa_key_and_jwk()
        alice_kid = _register_account(client, alice_key, alice_jwk)
        bob_kid = _register_account(client, bob_key, bob_jwk)
        self._seed_alice_order(app, alice_kid)

        def _no_upstream(self, *_a, **_k):
            raise AssertionError('upstream must not be called for a denied cert')
        monkeypatch.setattr(AcmeProxyService, '_post_with_account', _no_upstream)

        r_bob = self._post_as_get(
            client, f'/acme/proxy/cert/{_b64(CERT_URL)}', bob_key, bob_kid,
        )
        assert r_bob.status_code == 403
        assert 'unauthorized' in r_bob.get_json()['type']

        r_ghost = self._post_as_get(
            client, f'/acme/proxy/cert/{_b64(UPSTREAM + "/acme/cert/ghost")}',
            bob_key, bob_kid,
        )
        assert r_ghost.status_code == 404
