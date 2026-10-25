"""Security regressions for ACME proxy (EAB gate, order/cert binding)."""
import base64
import json

import pytest

from models import db, SystemConfig, AcmeClientAccount, AcmeClientOrder
from services.acme.acme_proxy_account import PROXY_ACCOUNT_ID_KEY
from services.acme.jws_problems import UNKNOWN_ACCOUNT


_STUB_DIRECTORY_URL = 'https://acme-stub.example/directory'


def _set_eab_required(app, enabled):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='acme_eab_required').first()
        if not row:
            row = SystemConfig(key='acme_eab_required', description='test')
            db.session.add(row)
        row.value = 'true' if enabled else 'false'
        db.session.commit()


def _get_nonce(client):
    r = client.get('/acme/proxy/new-nonce')
    return r.headers.get('Replay-Nonce', 'fallback-nonce')


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


def _post_new_order(client, jwk, private_key, kid):
    jws_order = _build_jws(
        'http://localhost/acme/proxy/new-order',
        {'identifiers': [{'type': 'dns', 'value': 'test.example.com'}]},
        jwk, private_key, nonce=_get_nonce(client), use_kid=kid,
    )
    return client.post(
        '/acme/proxy/new-order',
        data=json.dumps(jws_order),
        content_type='application/jose+json',
    )


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
def _reset_eab_required_after_test(app):
    yield
    _set_eab_required(app, False)


@pytest.fixture
def proxy_protocol_upstream_stub(app, monkeypatch):
    """Stub upstream directory fetch for proxy protocol security tests."""
    fake_directory = {
        'newNonce': 'https://acme-stub.example/acme/new-nonce',
        'newAccount': 'https://acme-stub.example/acme/new-account',
        'newOrder': 'https://acme-stub.example/acme/new-order',
        'meta': {},
    }

    class _FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return fake_directory

    from tests.acme_proxy_upstream_stub import stub_acme_proxy_upstream
    stub_acme_proxy_upstream(monkeypatch, fake_directory)

    with app.app_context():
        SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).delete()
        AcmeClientAccount.query.filter_by(
            directory_url=_STUB_DIRECTORY_URL
        ).delete()
        db.session.commit()
        acct = AcmeClientAccount(
            directory_url=_STUB_DIRECTORY_URL,
            label='Proxy Security Stub',
            email='proxy-security@example.com',
        )
        db.session.add(acct)
        db.session.commit()
        db.session.add(SystemConfig(
            key=PROXY_ACCOUNT_ID_KEY,
            value=str(acct.id),
            description='test proxy security',
        ))
        db.session.commit()
    yield
    with app.app_context():
        SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).delete()
        AcmeClientAccount.query.filter_by(
            directory_url=_STUB_DIRECTORY_URL
        ).delete()
        db.session.commit()


class TestAcmeProxyEabNewOrder:
    def test_new_order_requires_kid_when_eab_enabled(
        self, app, client, proxy_protocol_upstream_stub,
    ):
        _set_eab_required(app, True)
        private_key, jwk = _generate_rsa_key_and_jwk()
        nonce = _get_nonce(client)
        url = 'http://localhost/acme/proxy/new-order'
        payload = {'identifiers': [{'type': 'dns', 'value': 'test.example.com'}]}
        jws = _build_jws(url, payload, jwk, private_key, nonce=nonce)

        r = client.post(
            '/acme/proxy/new-order',
            data=json.dumps(jws),
            content_type='application/jose+json',
        )
        assert r.status_code == 400
        assert 'kid' in r.get_json().get('detail', '').lower()

    def test_new_order_allows_kid_when_eab_enabled(
        self, app, client, proxy_protocol_upstream_stub,
    ):
        _set_eab_required(app, False)
        private_key, jwk = _generate_rsa_key_and_jwk()

        nonce1 = _get_nonce(client)
        url_acct = 'http://localhost/acme/proxy/new-account'
        jws_acct = _build_jws(
            url_acct, {'termsOfServiceAgreed': True}, jwk, private_key, nonce=nonce1,
        )
        r_acct = client.post(
            '/acme/proxy/new-account',
            data=json.dumps(jws_acct),
            content_type='application/jose+json',
        )
        assert r_acct.status_code == 201
        kid = r_acct.headers['Location']

        _set_eab_required(app, True)

        r_order = _post_new_order(client, jwk, private_key, kid)

        detail = (r_order.get_json() or {}).get('detail', '')
        assert 'Missing JWK' not in detail
        assert 'kid required' not in detail.lower()
        assert 'Account not found' not in detail and UNKNOWN_ACCOUNT not in detail
        assert 'No DNS provider configured' in detail  # past the kid check


def _fail_a_flush():
    """A real failed statement: the session then refuses work until rolled back."""
    from models import AcmeAccount
    db.session.add(AcmeAccount(jwk=None, jwk_thumbprint=None))
    db.session.flush()


class TestAcmeProxyOnlyReturnExisting:
    """RFC 8555 §7.3.1: onlyReturnExisting never creates and needs no EAB."""

    _URL = 'http://localhost/acme/proxy/new-account'

    def _post(self, client, jwk, private_key, payload):
        jws = _build_jws(
            self._URL, payload, jwk, private_key, nonce=_get_nonce(client),
        )
        return client.post(
            '/acme/proxy/new-account',
            data=json.dumps(jws),
            content_type='application/jose+json',
        )

    def _account_count(self, app, jwk):
        from models import AcmeAccount
        from services.acme.jwk_thumbprint import jwk_thumbprint_or_none
        with app.app_context():
            return AcmeAccount.query.filter_by(
                jwk_thumbprint=jwk_thumbprint_or_none(jwk)).count()

    def test_returns_existing_account_without_eab(
        self, app, client, proxy_protocol_upstream_stub,
    ):
        _set_eab_required(app, False)
        private_key, jwk = _generate_rsa_key_and_jwk()
        r_create = self._post(client, jwk, private_key, {'termsOfServiceAgreed': True})
        assert r_create.status_code == 201
        kid = r_create.headers['Location']

        _set_eab_required(app, True)
        r = self._post(client, jwk, private_key, {'onlyReturnExisting': True})

        assert r.status_code == 200
        assert r.headers['Location'] == kid
        assert self._account_count(app, jwk) == 1

        # The kid from the lookup is accepted by new-order.
        r_order = _post_new_order(client, jwk, private_key, r.headers['Location'])
        detail = (r_order.get_json() or {}).get('detail', '')
        assert 'kid required' not in detail.lower()
        assert 'Account not found' not in detail and UNKNOWN_ACCOUNT not in detail
        assert 'No DNS provider configured' in detail  # past the kid check

    @pytest.mark.parametrize('eab_required', [True, False])
    def test_unknown_key_is_account_does_not_exist(
        self, app, client, proxy_protocol_upstream_stub, eab_required,
    ):
        _set_eab_required(app, eab_required)
        private_key, jwk = _generate_rsa_key_and_jwk()

        r = self._post(client, jwk, private_key, {'onlyReturnExisting': True})

        assert r.status_code == 400
        err_type = r.get_json()['type']
        assert err_type.endswith('accountDoesNotExist')
        assert not err_type.endswith('externalAccountRequired')
        assert self._account_count(app, jwk) == 0

    @pytest.mark.parametrize('payload', [
        {},
        {'termsOfServiceAgreed': True},
        {'onlyReturnExisting': False},
    ])
    def test_eab_gate_still_applies_without_only_return_existing(
        self, app, client, proxy_protocol_upstream_stub, payload,
    ):
        _set_eab_required(app, True)
        private_key, jwk = _generate_rsa_key_and_jwk()

        r = self._post(client, jwk, private_key, payload)

        assert r.status_code == 400
        assert r.get_json()['type'].endswith('externalAccountRequired')
        assert self._account_count(app, jwk) == 0

    def _create_closed_account(self, app, client, status):
        from models import AcmeAccount
        from services.acme.jwk_thumbprint import jwk_thumbprint_or_none
        _set_eab_required(app, False)
        private_key, jwk = _generate_rsa_key_and_jwk()
        r_create = self._post(client, jwk, private_key, {'termsOfServiceAgreed': True})
        assert r_create.status_code == 201
        with app.app_context():
            acct = AcmeAccount.query.filter_by(
                jwk_thumbprint=jwk_thumbprint_or_none(jwk)).first()
            acct.status = status
            db.session.commit()
        return private_key, jwk

    @pytest.mark.parametrize(
        'status', ['deactivated', 'revoked', 'pending', 'Deactivated'])
    def test_closed_account_is_unauthorized(
        self, app, client, proxy_protocol_upstream_stub, status,
    ):
        private_key, jwk = self._create_closed_account(app, client, status)

        r = self._post(client, jwk, private_key, {'onlyReturnExisting': True})

        assert r.status_code == 401
        assert r.get_json()['type'].endswith('unauthorized')
        assert 'Location' not in r.headers

    @pytest.mark.parametrize(
        'status', ['deactivated', 'revoked', 'pending', 'Deactivated'])
    def test_create_path_refuses_closed_account(
        self, app, client, proxy_protocol_upstream_stub, status,
    ):
        private_key, jwk = self._create_closed_account(app, client, status)

        r = self._post(client, jwk, private_key, {'termsOfServiceAgreed': True})

        assert r.status_code == 401
        assert r.get_json()['type'].endswith('unauthorized')
        assert 'Location' not in r.headers

    @pytest.mark.parametrize('eab_required', [True, False])
    @pytest.mark.parametrize('flag', ['true', 1, ['x'], 'false', 0])
    def test_non_boolean_flag_is_malformed(
        self, app, client, proxy_protocol_upstream_stub, flag, eab_required,
    ):
        _set_eab_required(app, eab_required)
        private_key, jwk = _generate_rsa_key_and_jwk()

        r = self._post(
            client, jwk, private_key,
            {'onlyReturnExisting': flag, 'termsOfServiceAgreed': True},
        )

        assert r.status_code == 400
        assert r.get_json()['type'].endswith('malformed')
        assert self._account_count(app, jwk) == 0

    def test_null_flag_counts_as_absent(
        self, app, client, proxy_protocol_upstream_stub,
    ):
        payload = {'onlyReturnExisting': None, 'termsOfServiceAgreed': True}
        private_key, jwk = _generate_rsa_key_and_jwk()

        _set_eab_required(app, True)
        r = self._post(client, jwk, private_key, payload)
        assert r.status_code == 400
        assert r.get_json()['type'].endswith('externalAccountRequired')
        assert self._account_count(app, jwk) == 0

        _set_eab_required(app, False)
        r = self._post(client, jwk, private_key, payload)
        assert r.status_code == 201
        assert self._account_count(app, jwk) == 1

    def test_create_database_error_is_server_internal(
        self, app, client, proxy_protocol_upstream_stub, monkeypatch,
    ):
        from services.acme import AcmeService

        def _boom(self, *args, **kwargs):
            _fail_a_flush()

        monkeypatch.setattr(AcmeService, 'create_account', _boom)
        _set_eab_required(app, False)
        private_key, jwk = _generate_rsa_key_and_jwk()

        r = self._post(client, jwk, private_key, {'termsOfServiceAgreed': True})

        assert r.status_code == 500
        assert r.headers['Content-Type'].startswith('application/problem+json')
        assert r.get_json()['type'].endswith('serverInternal')
        assert r.headers.get('Replay-Nonce')
        assert self._account_count(app, jwk) == 0

    def test_account_objects_carry_terms_of_service_agreed(
        self, app, client, proxy_protocol_upstream_stub,
    ):
        _set_eab_required(app, False)
        private_key, jwk = _generate_rsa_key_and_jwk()

        r_create = self._post(client, jwk, private_key, {'termsOfServiceAgreed': True})
        r_lookup = self._post(client, jwk, private_key, {'onlyReturnExisting': True})

        assert r_create.status_code == 201
        assert r_create.get_json()['termsOfServiceAgreed'] is True
        assert r_lookup.status_code == 200
        assert r_lookup.get_json()['termsOfServiceAgreed'] is True

    def test_lookup_database_error_is_server_internal(
        self, app, client, proxy_protocol_upstream_stub,
    ):
        from models import AcmeAccount

        class _FailingQuery:
            def filter_by(self, *args, **kwargs):
                return self

            def first(self):
                _fail_a_flush()

        _set_eab_required(app, True)
        private_key, jwk = _generate_rsa_key_and_jwk()

        # `query` is inherited from db.Model: shadow it, then drop the shadow.
        AcmeAccount.query = _FailingQuery()
        try:
            r = self._post(client, jwk, private_key, {'onlyReturnExisting': True})
        finally:
            del AcmeAccount.query

        assert r.status_code == 500
        assert r.headers['Content-Type'].startswith('application/problem+json')
        assert r.get_json()['type'].endswith('serverInternal')
        assert r.headers.get('Replay-Nonce')
        assert self._account_count(app, jwk) == 0


class TestAcmeProxyCertOrderBinding:
    def test_find_order_for_certificate_matches_upstream_cert_url(self, app, monkeypatch):
        from services.acme.acme_proxy_service import AcmeProxyService

        cert_url = 'https://ca.example/acme/cert/1'
        order_a_url = 'https://ca.example/acme/order/a'
        order_b_url = 'https://ca.example/acme/order/b'

        with app.app_context():
            order_a = AcmeClientOrder(
                domains='["a.example.com"]',
                environment='staging',
                challenge_type='dns-01',
                status='pending',
                order_url=order_a_url,
                upstream_order_url=order_a_url,
                is_proxy_order=True,
            )
            order_b = AcmeClientOrder(
                domains='["b.example.com"]',
                environment='staging',
                challenge_type='dns-01',
                status='pending',
                order_url=order_b_url,
                upstream_order_url=order_b_url,
                is_proxy_order=True,
            )
            db.session.add_all([order_a, order_b])
            db.session.commit()

            svc = AcmeProxyService('https://ucm.example/acme/proxy')

            def fake_post(url, payload):
                class Resp:
                    status_code = 200

                    def json(self_inner):
                        if url == order_b_url:
                            return {'certificate': cert_url}
                        return {}

                return Resp()

            monkeypatch.setattr(svc, '_post_with_account', fake_post)
            matched = svc._find_order_for_certificate(cert_url)
            assert matched is not None
            assert matched.id == order_b.id


class TestFinalizeFailClosed:
    """An owned order must never finalize without any requester identity."""

    @pytest.fixture(autouse=True)
    def _drop_seeded_orders(self, app):
        # The seeded account id has no acme_accounts row: a leftover order breaks the FK check of a later migration.
        yield
        with app.app_context():
            AcmeClientOrder.query.filter_by(account_id='acct-owner-1').delete()
            db.session.commit()

    def _seed_owned_order(self, app, **overrides):
        with app.app_context():
            AcmeClientOrder.query.filter_by(is_proxy_order=True).delete()
            kwargs = dict(
                domains='["owned.example.com"]',
                environment='staging',
                challenge_type='dns-01',
                status='pending',
                order_url='https://ca.example/acme/order/owned',
                upstream_order_url='https://ca.example/acme/order/owned',
                is_proxy_order=True,
                account_id='acct-owner-1',
                client_jwk_thumbprint='thumb-owner-1',
            )
            kwargs.update(overrides)
            order = AcmeClientOrder(**kwargs)
            db.session.add(order)
            db.session.commit()
            return order.id

    def _make_svc(self, app, monkeypatch):
        from services.acme.acme_proxy_service import AcmeProxyService

        with app.app_context():
            svc = AcmeProxyService('https://ucm.example/acme/proxy')
        monkeypatch.setattr(
            svc, '_decode_proxy_id',
            lambda _id: 'https://ca.example/acme/order/owned',
        )

        def _no_upstream(*_a, **_k):
            raise AssertionError('upstream must not be called on identity failure')

        monkeypatch.setattr(svc, '_post_with_account', _no_upstream)
        return svc

    def test_finalize_without_identity_rejected(self, app, monkeypatch):
        self._seed_owned_order(app)
        svc = self._make_svc(app, monkeypatch)
        with app.app_context(), pytest.raises(PermissionError):
            svc.finalize_order(
                'ignored',
                '-----BEGIN CERTIFICATE REQUEST-----\nMIIB\n-----END CERTIFICATE REQUEST-----\n',
                requester_account_id=None,
                requester_thumbprint=None,
            )

    def test_finalize_with_matching_identity_passes_binding(self, app, monkeypatch):
        self._seed_owned_order(app)
        svc = self._make_svc(app, monkeypatch)

        with app.app_context():
            # Force an early stop once binding succeeded: no valid CSR needed.
            try:
                svc.finalize_order(
                    'ignored',
                    'not-a-real-csr',
                    requester_account_id='acct-owner-1',
                    requester_thumbprint='thumb-owner-1',
                )
            except PermissionError:
                pytest.fail('matching identity must not raise PermissionError')
            except Exception:
                pass  # CSR/upstream handling is out of scope for this test
