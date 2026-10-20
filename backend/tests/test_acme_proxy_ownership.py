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
def _drop_orders_created_here(app):
    """Orders a test creates leave with it: later suites check FK integrity."""
    with app.app_context():
        floor = db.session.query(db.func.max(AcmeClientOrder.id)).scalar() or 0
    yield
    with app.app_context():
        db.session.rollback()
        AcmeClientOrder.query.filter(AcmeClientOrder.id > floor).delete(
            synchronize_session=False)
        db.session.commit()


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


class TestSharedUpstreamAuthz:
    """#307 - one upstream authorization, several downstream accounts.

    The proxy signs upstream with a single account, so Let's Encrypt hands the
    same authorization (and challenge) URL to every downstream account that
    orders the domain. Each local order must resolve to its own owner, and the
    shared challenge's dns-01 automation must fire only once.
    """

    _SECOND = f'{UPSTREAM}/acme/order/owner/2'

    def _authz_resp(self, status='pending'):
        return _FakeResp({
            'status': status,
            'identifier': {'type': 'dns', 'value': 'owned.example.com'},
            'challenges': [
                {'type': 'dns-01', 'url': CHALL_URL, 'status': status, 'token': 't'},
            ],
        })

    def _seed_second(self):
        return _seed_order(
            account_id='acct-b', client_jwk_thumbprint='thumb-b',
            order_url=self._SECOND, upstream_order_url=self._SECOND,
            certificate_url=f'{UPSTREAM}/acme/cert/bbb',
        )

    def test_each_account_resolves_to_its_own_order(self, app, monkeypatch):
        with app.app_context():
            _seed_order(account_id='acct-a', client_jwk_thumbprint='thumb-a')
            self._seed_second()
            svc = _make_svc(
                app, monkeypatch, upstream_response=self._authz_resp('valid'),
            )
            for acct, thumb in (('acct-a', 'thumb-a'), ('acct-b', 'thumb-b')):
                _authz, identifier = svc.get_authz(
                    _b64(AUTHZ_URL),
                    requester_account_id=acct, requester_thumbprint=thumb,
                )
                assert identifier['value'] == 'owned.example.com'

    def test_third_account_still_denied(self, app, monkeypatch):
        with app.app_context():
            _seed_order(account_id='acct-a', client_jwk_thumbprint='thumb-a')
            self._seed_second()
            svc = _make_svc(app, monkeypatch)  # asserts upstream is never called
            with pytest.raises(PermissionError):
                svc.get_authz(
                    _b64(AUTHZ_URL),
                    requester_account_id='acct-c',
                    requester_thumbprint='thumb-c',
                )

    def test_sibling_initiated_challenge_blocks_second_automation(
        self, app, monkeypatch,
    ):
        import services.acme.acme_proxy_service as mod

        started = []

        class _Recorder:
            def __init__(self, *a, **k):
                started.append('thread-created')

            def start(self):
                started.append('thread-started')

        with app.app_context():
            order_a = _seed_order(
                account_id='acct-a', client_jwk_thumbprint='thumb-a',
            )
            order_a.set_challenges_dict({CHALL_URL: {'status': 'initiated'}})
            db.session.commit()
            self._seed_second()

            svc = _make_svc(
                app, monkeypatch, upstream_response=self._authz_resp('pending'),
            )
            monkeypatch.setattr(mod.threading, 'Thread', _Recorder)
            monkeypatch.setattr(
                'api.v2.acme_domains.find_provider_for_domain',
                lambda *_a, **_k: {'provider': object()},
            )
            monkeypatch.setattr(svc, '_get_account_thumbprint', lambda: 'x')

            _authz, identifier = svc.get_authz(
                _b64(AUTHZ_URL),
                requester_account_id='acct-b', requester_thumbprint='thumb-b',
            )
            assert identifier['value'] == 'owned.example.com'
            assert started == [], (
                'account B must not start a second dns-01 automation for a '
                'challenge a sibling order already initiated'
            )


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
                svc, '_find_order_for_certificate', lambda *_args, **_kwargs: None,
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


class TestSameAccountPendingOrderReuse:
    """#303 (minor 4): a retried new-order for the same account and the same
    identifier set returns the still-pending order instead of opening a new
    upstream order every time."""

    def _seed(self, thumbprint='thumb-reuse', domains='["reuse.example.com"]',
              status='pending', upstream='https://ca.example/acme/order/reuse-1'):
        return _seed_order(
            account_id='acct-reuse', client_jwk_thumbprint=thumbprint,
            domains=domains, status=status,
            order_url=upstream, upstream_order_url=upstream,
            certificate_url=f'{UPSTREAM}/acme/cert/reuse',
        )

    def test_reuses_pending_order_when_upstream_still_pending(self, app, monkeypatch):
        with app.app_context():
            self._seed()
            svc = _make_svc(app, monkeypatch, upstream_response=_FakeResp({
                'status': 'pending',
                'authorizations': ['https://ca.example/acme/authz-v3/r1'],
                'finalize': 'https://ca.example/acme/order/reuse-1/finalize',
            }))
            result = svc._find_reusable_pending_order(
                ['reuse.example.com'], 'thumb-reuse')
            assert result is not None
            order_payload, order_id = result
            assert order_payload['finalize'].endswith(f'/order/{order_id}/finalize')
            assert order_payload['authorizations'][0].startswith(svc.base_url)

    def test_no_reuse_for_other_thumbprint_or_domains(self, app, monkeypatch):
        with app.app_context():
            self._seed()
            svc = _make_svc(app, monkeypatch)  # upstream never called
            assert svc._find_reusable_pending_order(
                ['reuse.example.com'], 'thumb-other') is None
            assert svc._find_reusable_pending_order(
                ['different.example.com'], 'thumb-reuse') is None
            assert svc._find_reusable_pending_order(
                ['reuse.example.com'], None) is None

    def test_no_reuse_when_upstream_no_longer_pending(self, app, monkeypatch):
        with app.app_context():
            self._seed(upstream='https://ca.example/acme/order/reuse-2')
            svc = _make_svc(app, monkeypatch, upstream_response=_FakeResp({
                'status': 'invalid',
                'authorizations': [],
            }))
            assert svc._find_reusable_pending_order(
                ['reuse.example.com'], 'thumb-reuse') is None


class TestClientTxtValues:
    """#306/#307: the proxy also publishes the dns-01 TXT values computed with
    the client thumbprints, so lego/Caddy pre-checks can pass without
    disabling propagation checks."""

    def test_rfc8555_hash(self):
        import base64
        import hashlib
        from services.acme.acme_proxy_service import _dns01_txt_value
        ka = 'token123.thumbABC'
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(ka.encode()).digest()).rstrip(b'=').decode()
        assert _dns01_txt_value(ka) == expected

    def test_sibling_client_values_deduped_and_upstream_excluded(self, app, monkeypatch):
        import json as _json
        from services.acme.acme_proxy_service import _dns01_txt_value
        authz = f'{UPSTREAM}/acme/authz-v3/txt-shared'
        with app.app_context():
            a = _seed_order(
                account_id='acct-txt-a', client_jwk_thumbprint='thumb-txt-a',
                order_url=f'{UPSTREAM}/acme/order/txt/1',
                upstream_order_url=f'{UPSTREAM}/acme/order/txt/1',
                upstream_authz_urls=json.dumps([authz]),
                certificate_url=f'{UPSTREAM}/acme/cert/txt1',
            )
            _seed_order(
                account_id='acct-txt-b', client_jwk_thumbprint='thumb-txt-b',
                order_url=f'{UPSTREAM}/acme/order/txt/2',
                upstream_order_url=f'{UPSTREAM}/acme/order/txt/2',
                upstream_authz_urls=json.dumps([authz]),
                certificate_url=f'{UPSTREAM}/acme/cert/txt2',
            )
            svc = _make_svc(app, monkeypatch)
            upstream_value = _dns01_txt_value('tok.upstream-thumb')
            values = svc._client_txt_values(a, 'tok.upstream-thumb', upstream_value)
            assert sorted(values) == sorted([
                _dns01_txt_value('tok.thumb-txt-a'),
                _dns01_txt_value('tok.thumb-txt-b'),
            ])
            assert upstream_value not in values

    def test_uses_current_authz_for_overlapping_multi_domain_orders(
        self, app, monkeypatch,
    ):
        from services.acme.acme_proxy_service import _dns01_txt_value
        first_authz = f'{UPSTREAM}/acme/authz-v3/txt-first'
        shared_authz = f'{UPSTREAM}/acme/authz-v3/txt-overlap'
        with app.app_context():
            multi = _seed_order(
                account_id='acct-multi', client_jwk_thumbprint='thumb-multi',
                order_url=f'{UPSTREAM}/acme/order/txt/multi',
                upstream_order_url=f'{UPSTREAM}/acme/order/txt/multi',
                upstream_authz_urls=json.dumps([first_authz, shared_authz]),
                certificate_url=f'{UPSTREAM}/acme/cert/txt-multi',
            )
            _seed_order(
                account_id='acct-overlap', client_jwk_thumbprint='thumb-overlap',
                order_url=f'{UPSTREAM}/acme/order/txt/overlap',
                upstream_order_url=f'{UPSTREAM}/acme/order/txt/overlap',
                upstream_authz_urls=json.dumps([shared_authz]),
                certificate_url=f'{UPSTREAM}/acme/cert/txt-overlap',
            )
            svc = _make_svc(app, monkeypatch)
            upstream_value = _dns01_txt_value('tok.upstream-thumb')
            values = svc._client_txt_values(
                multi, 'tok.upstream-thumb', upstream_value,
                authz_url=shared_authz,
            )
            assert _dns01_txt_value('tok.thumb-overlap') in values

    def test_no_thumbprint_returns_empty(self, app, monkeypatch):
        with app.app_context():
            order = _seed_order(
                account_id=None, client_jwk_thumbprint=None,
                order_url=f'{UPSTREAM}/acme/order/txt/3',
                upstream_order_url=f'{UPSTREAM}/acme/order/txt/3',
                upstream_authz_urls=json.dumps([f'{UPSTREAM}/acme/authz-v3/txt-lonely']),
                certificate_url=f'{UPSTREAM}/acme/cert/txt3',
            )
            svc = _make_svc(app, monkeypatch)
            assert svc._client_txt_values(order, 'tok.x', 'zzz') == []
