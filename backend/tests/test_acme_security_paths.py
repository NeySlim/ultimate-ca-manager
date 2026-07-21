"""Regression tests for ACME server security paths (RFC 8555).

Covers challenge state transitions, authenticated resource reads,
pre-authorizations, wildcard authorizations, and key-change conflicts.
"""
import base64 as b64
import hashlib
import hmac
import json
from datetime import timedelta

from utils.datetime_utils import utc_now

import pytest

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import NameOID

from models import db, SystemConfig
from models.acme_models import (
    AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge,
    AcmeEabCredential,
)
from services.acme.acme_service import AcmeService


def _int_to_b64(n):
    raw = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    return b64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def _gen_key_and_jwk():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_numbers()
    jwk = {'kty': 'RSA', 'n': _int_to_b64(pub.n), 'e': _int_to_b64(pub.e)}
    return key, jwk


def _b64json(obj):
    return b64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b'=').decode()


def _sign(key, protected_b64, payload_b64):
    signing_input = f'{protected_b64}.{payload_b64}'.encode()
    sig = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return b64.urlsafe_b64encode(sig).rstrip(b'=').decode()


def _build_jws(url, payload, key, jwk=None, kid=None, nonce='nonce'):
    protected = {'alg': 'RS256', 'nonce': nonce, 'url': url}
    if kid:
        protected['kid'] = kid
    else:
        protected['jwk'] = jwk
    protected_b64 = _b64json(protected)
    payload_b64 = '' if payload is None else _b64json(payload)
    return {
        'protected': protected_b64,
        'payload': payload_b64,
        'signature': _sign(key, protected_b64, payload_b64),
    }


def _nonce(client):
    r = client.get('/acme/new-nonce')
    return r.headers.get('Replay-Nonce', 'fallback')


def _thumbprint(jwk):
    # Mirror the service implementation (RFC 7638)
    canonical = json.dumps(
        {'e': jwk['e'], 'kty': jwk['kty'], 'n': jwk['n']},
        separators=(',', ':'), sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode()).digest()
    return b64.urlsafe_b64encode(digest).rstrip(b'=').decode()


def _post_jws(client, path, jws, content_type='application/jose+json'):
    return client.post(
        path,
        data=json.dumps(jws),
        content_type=content_type,
    )


def _csr_b64(key, common_name='finalize.example.com'):
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(common_name)]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    der = csr.public_bytes(serialization.Encoding.DER)
    return b64.urlsafe_b64encode(der).rstrip(b'=').decode()


@pytest.fixture
def acme_account(app):
    """Create a persisted ACME account with a known key pair."""
    key, jwk = _gen_key_and_jwk()
    with app.app_context():
        acct = AcmeAccount(
            jwk=json.dumps(jwk),
            jwk_thumbprint=_thumbprint(jwk),
            status='valid',
        )
        db.session.add(acct)
        db.session.commit()
        acct_id = acct.account_id
    return {'key': key, 'jwk': jwk, 'account_id': acct_id}


class TestChallengeTerminalState:
    """Path #3: settled challenges must not be re-validated."""

    def _make_challenge(self, app, account_id, status):
        with app.app_context():
            order = AcmeOrder(
                account_id=account_id,
                status='pending',
                identifiers=json.dumps([{'type': 'dns', 'value': 'x.example.com'}]),
            )
            db.session.add(order)
            db.session.commit()
            authz = AcmeAuthorization(
                order_id=order.order_id,
                account_id=account_id,
                identifier=json.dumps({'type': 'dns', 'value': 'x.example.com'}),
                status='valid' if status == 'valid' else 'pending',
            )
            db.session.add(authz)
            db.session.commit()
            chall = AcmeChallenge(
                authorization_id=authz.authorization_id,
                type='http-01',
                status=status,
                url='http://localhost/acme/challenge/placeholder',
            )
            db.session.add(chall)
            db.session.commit()
            # Persist the real URL now that we have the challenge_id
            chall.url = f'http://localhost/acme/challenge/{chall.challenge_id}'
            db.session.commit()
            return chall.challenge_id

    def test_valid_challenge_not_revalidated(self, app, client, acme_account, monkeypatch):
        chall_id = self._make_challenge(app, acme_account['account_id'], 'valid')

        # Any attempt to re-run validation would call this — make it explode.
        from services.acme.acme_service import AcmeService
        def _boom(*a, **k):
            raise AssertionError("validation must not run on a settled challenge")
        monkeypatch.setattr(AcmeService, 'validate_http01_challenge', _boom)

        url = f'http://localhost/acme/challenge/{chall_id}'
        jws = _build_jws(url, {}, acme_account['key'],
                         kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
                         nonce=_nonce(client))
        r = client.post(f'/acme/challenge/{chall_id}',
                        data=json.dumps(jws),
                        content_type='application/jose+json')
        assert r.status_code == 200
        assert r.get_json()['status'] == 'valid'

    def test_invalid_challenge_not_retried(self, app, client, acme_account, monkeypatch):
        chall_id = self._make_challenge(app, acme_account['account_id'], 'invalid')

        from services.acme.acme_service import AcmeService
        def _boom(*a, **k):
            raise AssertionError("validation must not retry an invalid challenge")
        monkeypatch.setattr(AcmeService, 'validate_http01_challenge', _boom)

        url = f'http://localhost/acme/challenge/{chall_id}'
        jws = _build_jws(url, {}, acme_account['key'],
                         kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
                         nonce=_nonce(client))
        r = client.post(f'/acme/challenge/{chall_id}',
                        data=json.dumps(jws),
                        content_type='application/jose+json')
        assert r.status_code == 200
        assert r.get_json()['status'] == 'invalid'


@pytest.fixture
def acme_read_resources(app, acme_account):
    """Create order-linked and standalone resources owned by one account."""
    with app.app_context():
        order = AcmeOrder(
            account_id=acme_account['account_id'],
            status='pending',
            identifiers=json.dumps([{'type': 'dns', 'value': 'read.example.com'}]),
        )
        db.session.add(order)
        db.session.flush()

        order_authz = AcmeAuthorization(
            order_id=order.order_id,
            account_id=acme_account['account_id'],
            identifier=json.dumps({'type': 'dns', 'value': 'read.example.com'}),
            status='pending',
        )
        standalone_authz = AcmeAuthorization(
            order_id=None,
            account_id=acme_account['account_id'],
            identifier=json.dumps({'type': 'dns', 'value': 'preauth.example.com'}),
            status='pending',
        )
        db.session.add_all([order_authz, standalone_authz])
        db.session.commit()

        return {
            'order_id': order.order_id,
            'order_authz_id': order_authz.authorization_id,
            'standalone_authz_id': standalone_authz.authorization_id,
        }


class TestPostAsGetProtection:
    """RFC 8555 resources require authenticated POST-as-GET requests."""

    @staticmethod
    def _other_account(app):
        key, jwk = _gen_key_and_jwk()
        with app.app_context():
            account = AcmeAccount(
                jwk=json.dumps(jwk),
                jwk_thumbprint=_thumbprint(jwk),
                status='valid',
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.account_id
        return {'key': key, 'account_id': account_id}

    def test_order_authz_and_certificate_reject_missing_jws(
        self, client, acme_read_resources
    ):
        paths = (
            f'/acme/order/{acme_read_resources["order_id"]}',
            f'/acme/authz/{acme_read_resources["order_authz_id"]}',
            f'/acme/cert/{acme_read_resources["order_id"]}',
        )

        for path in paths:
            response = client.post(
                path,
                data='{}',
                content_type='application/jose+json',
            )
            assert response.status_code == 400, path
            assert response.get_json()['type'].endswith(':malformed'), path

    def test_order_authz_and_certificate_require_empty_payload(
        self, client, acme_account, acme_read_resources
    ):
        paths = (
            f'/acme/order/{acme_read_resources["order_id"]}',
            f'/acme/authz/{acme_read_resources["order_authz_id"]}',
            f'/acme/cert/{acme_read_resources["order_id"]}',
        )

        for path in paths:
            jws = _build_jws(
                f'http://localhost{path}',
                {},
                acme_account['key'],
                kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
                nonce=_nonce(client),
            )
            response = client.post(
                path,
                data=json.dumps(jws),
                content_type='application/jose+json',
            )
            assert response.status_code == 400, path
            assert response.get_json()['type'].endswith(':malformed'), path

    def test_order_authz_and_certificate_reject_other_account(
        self, app, client, acme_read_resources
    ):
        other = self._other_account(app)
        paths = (
            f'/acme/order/{acme_read_resources["order_id"]}',
            f'/acme/authz/{acme_read_resources["order_authz_id"]}',
            f'/acme/cert/{acme_read_resources["order_id"]}',
        )

        for path in paths:
            url = f'http://localhost{path}'
            jws = _build_jws(
                url,
                None,
                other['key'],
                kid=f'http://localhost/acme/acct/{other["account_id"]}',
                nonce=_nonce(client),
            )
            response = client.post(
                path,
                data=json.dumps(jws),
                content_type='application/jose+json',
            )
            assert response.status_code == 403, path
            assert response.get_json()['type'].endswith(':unauthorized'), path

    def test_owner_can_read_order_and_standalone_authz_without_up_link(
        self, client, acme_account, acme_read_resources
    ):
        resources = (
            ('order', acme_read_resources['order_id']),
            ('authz', acme_read_resources['standalone_authz_id']),
        )

        for resource, resource_id in resources:
            path = f'/acme/{resource}/{resource_id}'
            url = f'http://localhost{path}'
            jws = _build_jws(
                url,
                None,
                acme_account['key'],
                kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
                nonce=_nonce(client),
            )
            response = client.post(
                path,
                data=json.dumps(jws),
                content_type='application/jose+json',
            )
            assert response.status_code == 200, path
            if resource == 'authz':
                assert all(
                    'rel="up"' not in link
                    for link in response.headers.getlist('Link')
                )

    def test_certificate_get_is_not_public(self, client, acme_read_resources):
        response = client.get(f'/acme/cert/{acme_read_resources["order_id"]}')
        assert response.status_code in (404, 405)


class TestPreAuthorizationAndWildcard:
    """Regression coverage for standalone authz and wildcard normalization."""

    def test_standalone_authorization_becomes_valid(self, app, acme_account):
        with app.app_context():
            authz = AcmeAuthorization(
                order_id=None,
                account_id=acme_account['account_id'],
                identifier=json.dumps({'type': 'dns', 'value': 'pre.example.com'}),
                status='pending',
            )
            db.session.add(authz)
            db.session.flush()
            challenge = AcmeChallenge(
                authorization_id=authz.authorization_id,
                type='dns-01',
                status='valid',
            )
            db.session.add(challenge)
            db.session.commit()

            AcmeService(base_url='http://localhost')._update_authorization_status(authz)

            assert authz.status == 'valid'
            assert authz.order_id is None

    def test_wildcard_order_does_not_reuse_base_domain_authz(self, app, acme_account):
        """A valid non-wildcard authorization for example.com must NOT be reused
        for a *.example.com order: identifiers normalize to the same JSON, but
        reuse must honor the wildcard flag (RFC 8555 §8.4 — wildcard needs
        dns-01). Otherwise apex web-control (http-01) would yield a wildcard."""
        with app.app_context():
            acct = acme_account['account_id']
            # Existing VALID non-wildcard authz for the base domain.
            base = AcmeAuthorization(
                order_id=None,
                account_id=acct,
                identifier=json.dumps({'type': 'dns', 'value': 'reuse.example.com'}),
                wildcard=False,
                status='valid',
                expires=utc_now() + timedelta(days=7),
            )
            db.session.add(base)
            db.session.flush()
            svc = AcmeService(base_url='http://localhost')
            order = AcmeOrder(
                account_id=acct,
                status='pending',
                identifiers=json.dumps([{'type': 'dns', 'value': '*.reuse.example.com'}]),
            )
            db.session.add(order)
            db.session.flush()

            authz = svc._create_authorization(
                order.order_id,
                {'type': 'dns', 'value': '*.reuse.example.com'},
                account_id=acct,
            )
            # A fresh pending wildcard authz — the valid base-domain one is not reused.
            assert authz.wildcard is True
            assert authz.status == 'pending'
            assert authz.authorization_id != base.authorization_id

    def test_base_domain_order_does_not_reuse_wildcard_authz(self, app, acme_account):
        """Converse: a valid wildcard authz must not satisfy a base-domain order."""
        with app.app_context():
            acct = acme_account['account_id']
            wild = AcmeAuthorization(
                order_id=None,
                account_id=acct,
                identifier=json.dumps({'type': 'dns', 'value': 'conv.example.com'}),
                wildcard=True,
                status='valid',
                expires=utc_now() + timedelta(days=7),
            )
            db.session.add(wild)
            db.session.flush()
            svc = AcmeService(base_url='http://localhost')
            order = AcmeOrder(
                account_id=acct,
                status='pending',
                identifiers=json.dumps([{'type': 'dns', 'value': 'conv.example.com'}]),
            )
            db.session.add(order)
            db.session.flush()

            authz = svc._create_authorization(
                order.order_id,
                {'type': 'dns', 'value': 'conv.example.com'},
                account_id=acct,
            )
            assert authz.wildcard is False
            assert authz.status == 'pending'
            assert authz.authorization_id != wild.authorization_id

    def test_new_order_accepts_wildcard_and_exposes_dns01_only(
        self, client, acme_account
    ):
        path = '/acme/new-order'
        jws = _build_jws(
            f'http://localhost{path}',
            {'identifiers': [{'type': 'dns', 'value': '*.wild.example.com'}]},
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )
        response = client.post(
            path,
            data=json.dumps(jws),
            content_type='application/jose+json',
        )
        assert response.status_code == 201
        order_body = response.get_json()
        assert order_body['identifiers'] == [
            {'type': 'dns', 'value': '*.wild.example.com'}
        ]

        authz_path = order_body['authorizations'][0].removeprefix('http://localhost')
        authz_jws = _build_jws(
            f'http://localhost{authz_path}',
            None,
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )
        authz_response = client.post(
            authz_path,
            data=json.dumps(authz_jws),
            content_type='application/jose+json',
        )
        assert authz_response.status_code == 200
        authz_body = authz_response.get_json()
        assert authz_body['identifier'] == {
            'type': 'dns',
            'value': 'wild.example.com',
        }
        assert authz_body['wildcard'] is True
        assert [challenge['type'] for challenge in authz_body['challenges']] == [
            'dns-01'
        ]

    def test_wildcard_preauth_response_and_dns_query_use_base_domain(
        self, app, client, acme_account, monkeypatch
    ):
        with app.app_context():
            service = AcmeService(base_url='http://localhost')
            authz = service.create_pre_authorization(
                acme_account['account_id'],
                {'type': 'dns', 'value': '*.prewild.example.com'},
            )
            challenge = authz.challenges.first()
            key_authz = service._compute_key_authorization(
                challenge.token,
                _thumbprint(acme_account['jwk']),
            )
            txt_value = b64.urlsafe_b64encode(
                hashlib.sha256(key_authz.encode()).digest()
            ).rstrip(b'=').decode()
            queried = []

            class TxtAnswer:
                strings = [txt_value.encode()]

            def resolve(name, record_type):
                queried.append((name, record_type))
                return [TxtAnswer()]

            import dns.resolver
            monkeypatch.setattr(dns.resolver, 'resolve', resolve)

            account = AcmeAccount.query.filter_by(
                account_id=acme_account['account_id']
            ).first()
            assert service.validate_dns01_challenge(challenge, account) is True
            authz_id = authz.authorization_id

            assert queried == [('_acme-challenge.prewild.example.com', 'TXT')]
            assert authz.identifier_obj == {
                'type': 'dns',
                'value': 'prewild.example.com',
            }
            assert authz.wildcard is True
            assert authz.status == 'valid'

        path = f'/acme/authz/{authz_id}'
        jws = _build_jws(
            f'http://localhost{path}',
            None,
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )
        response = client.post(
            path,
            data=json.dumps(jws),
            content_type='application/jose+json',
        )
        assert response.status_code == 200
        assert response.get_json()['identifier']['value'] == 'prewild.example.com'
        assert response.get_json()['wildcard'] is True
        assert all('rel="up"' not in link for link in response.headers.getlist('Link'))


class TestRfc8555ErrorTypes:
    def test_new_order_collects_identifier_subproblems(
        self, client, acme_account
    ):
        path = '/acme/new-order'
        identifiers = [
            {'type': 'email', 'value': 'admin@example.com'},
            {'type': 'ip', 'value': 'not-an-ip'},
            {'type': 'dns', 'value': 'valid.example.com'},
        ]
        jws = _build_jws(
            f'http://localhost{path}',
            {'identifiers': identifiers},
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )

        response = _post_jws(client, path, jws)

        assert response.status_code == 400
        problem = response.get_json()
        assert problem['type'].endswith(':compound')
        assert [item['identifier'] for item in problem['subproblems']] == identifiers[:2]
        assert [item['type'] for item in problem['subproblems']] == [
            'urn:ietf:params:acme:error:unsupportedIdentifier',
            'urn:ietf:params:acme:error:malformed',
        ]
        assert all(item['detail'] for item in problem['subproblems'])

    def test_new_order_single_identifier_error_keeps_specific_type(
        self, client, acme_account
    ):
        path = '/acme/new-order'
        identifier = {'type': 'uri', 'value': 'https://example.com'}
        jws = _build_jws(
            f'http://localhost{path}',
            {'identifiers': [identifier]},
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )

        response = _post_jws(client, path, jws)

        problem = response.get_json()
        assert problem['type'].endswith(':unsupportedIdentifier')
        assert problem['subproblems'][0]['identifier'] == identifier

    @pytest.mark.parametrize(
        ('contact', 'error_type'),
        [
            ('tel:+12025550123', 'unsupportedContact'),
            ('https://example.com/contact', 'unsupportedContact'),
            ('mailto:not-an-email', 'invalidContact'),
            ('mailto:@example.com', 'invalidContact'),
        ],
    )
    def test_new_account_validates_contact_uris(
        self, client, contact, error_type
    ):
        key, jwk = _gen_key_and_jwk()
        path = '/acme/new-account'
        jws = _build_jws(
            f'http://localhost{path}',
            {'termsOfServiceAgreed': True, 'contact': [contact]},
            key,
            jwk=jwk,
            nonce=_nonce(client),
        )

        response = _post_jws(client, path, jws)

        assert response.status_code == 400
        assert response.get_json()['type'].endswith(f':{error_type}')

    def test_new_account_accepts_mailto_contact(self, client):
        key, jwk = _gen_key_and_jwk()
        path = '/acme/new-account'
        contact = 'mailto:admin@example.com'
        jws = _build_jws(
            f'http://localhost{path}',
            {'termsOfServiceAgreed': True, 'contact': [contact]},
            key,
            jwk=jwk,
            nonce=_nonce(client),
        )

        response = _post_jws(client, path, jws)

        assert response.status_code == 201
        assert response.get_json()['contact'] == [contact]

    def _make_owned_cert_certid(self, app, account_id, aki_hex='aa:bb:cc:dd', serial=0x123456):
        """Persist a certificate owned by account_id (linked via an AcmeOrder)
        and return its RFC 9773 CertID (b64url(AKI).b64url(serial))."""
        from models import Certificate
        import base64 as _b64
        # A real (self-signed) cert PEM so global iterators like export-all
        # don't choke on undecodable data (shared session-scoped test DB).
        _k = rsa.generate_private_key(65537, 2048)
        _name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'owned.example.com')])
        _crt = (x509.CertificateBuilder()
                .subject_name(_name).issuer_name(_name)
                .public_key(_k.public_key())
                .serial_number(serial)
                .not_valid_before(utc_now() - timedelta(minutes=5))
                .not_valid_after(utc_now() + timedelta(days=90))
                .sign(_k, hashes.SHA256()))
        _crt_b64 = _b64.b64encode(_crt.public_bytes(serialization.Encoding.PEM)).decode()
        with app.app_context():
            cert = Certificate(
                refid='ari-owned',
                descr='ari owned',
                crt=_crt_b64,
                # Stored decimal, as the real issuance path does.
                serial_number=str(serial),
                aki=aki_hex,
            )
            db.session.add(cert)
            db.session.flush()
            order = AcmeOrder(
                account_id=account_id,
                status='valid',
                identifiers=json.dumps([{'type': 'dns', 'value': 'owned.example.com'}]),
                certificate_id=cert.id,
            )
            db.session.add(order)
            db.session.commit()
            aki_bytes = bytes.fromhex(aki_hex.replace(':', ''))
            serial_bytes = serial.to_bytes((serial.bit_length() + 7) // 8, 'big')
            return (b64.urlsafe_b64encode(aki_bytes).rstrip(b'=').decode()
                    + '.' + b64.urlsafe_b64encode(serial_bytes).rstrip(b'=').decode())

    def test_new_order_stores_ari_replaces(self, app, client, acme_account):
        path = '/acme/new-order'
        # RFC 9773 §5: replaces must identify a cert this account holds.
        replaces = self._make_owned_cert_certid(app, acme_account['account_id'])
        jws = _build_jws(
            f'http://localhost{path}',
            {
                'identifiers': [
                    {'type': 'dns', 'value': 'replacement.example.com'}
                ],
                'replaces': replaces,
            },
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )

        response = _post_jws(client, path, jws)

        assert response.status_code == 201
        order_id = response.headers['Location'].rstrip('/').split('/')[-1]
        with app.app_context():
            order = AcmeOrder.query.filter_by(order_id=order_id).first()
            assert order.replaces == replaces

    def test_new_order_ignores_ari_replaces_not_owned_by_account(
        self, app, client, acme_account
    ):
        """A well-formed certid pointing at a cert this account does not hold is
        dropped (order created, replaces not recorded) — prevents tampering with
        another account's ARI window (RFC 9773 §5)."""
        path = '/acme/new-order'
        replaces = f'{_int_to_b64(0xAABBCC)}.{_int_to_b64(0x123456)}'
        jws = _build_jws(
            f'http://localhost{path}',
            {
                'identifiers': [
                    {'type': 'dns', 'value': 'replacement.example.com'}
                ],
                'replaces': replaces,
            },
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )

        response = _post_jws(client, path, jws)

        assert response.status_code == 201
        order_id = response.headers['Location'].rstrip('/').split('/')[-1]
        with app.app_context():
            order = AcmeOrder.query.filter_by(order_id=order_id).first()
            assert order.replaces is None

    @pytest.mark.parametrize('replaces', ['not-a-certid', 'abc.***', 'abc=.def'])
    def test_new_order_rejects_malformed_ari_replaces(
        self, client, acme_account, replaces
    ):
        path = '/acme/new-order'
        jws = _build_jws(
            f'http://localhost{path}',
            {
                'identifiers': [
                    {'type': 'dns', 'value': 'replacement.example.com'}
                ],
                'replaces': replaces,
            },
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )

        response = _post_jws(client, path, jws)

        assert response.status_code == 400
        assert response.get_json()['type'].endswith(':malformed')

    def test_post_jws_requires_jose_content_type(self, client):
        response = client.post('/acme/new-account', json={})
        assert response.status_code == 415
        assert response.get_json()['type'].endswith(':malformed')

    def test_consumed_nonce_returns_bad_nonce(self, client, acme_account):
        path = '/acme/new-order'
        nonce = _nonce(client)
        jws = _build_jws(
            f'http://localhost{path}',
            {'identifiers': [{'type': 'dns', 'value': 'nonce.example.com'}]},
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=nonce,
        )
        first = _post_jws(client, path, jws)
        assert first.status_code == 201

        second = _post_jws(client, path, jws)
        assert second.status_code == 400
        assert second.get_json()['type'].endswith(':badNonce')

    def test_new_account_invalid_jwk_returns_bad_public_key(self, client):
        path = '/acme/new-account'
        protected = _b64json({
            'alg': 'RS256',
            'nonce': _nonce(client),
            'url': f'http://localhost{path}',
            'jwk': {'kty': 'unsupported'},
        })
        jws = {
            'protected': protected,
            'payload': _b64json({'termsOfServiceAgreed': True}),
            'signature': _b64json({'not': 'a signature'}),
        }
        response = _post_jws(client, path, jws)
        assert response.status_code == 400
        assert response.get_json()['type'].endswith(':badPublicKey')

    @pytest.mark.parametrize('reason', [-1, 7, 11, '1', None, True])
    def test_invalid_revocation_reason(self, client, acme_account, reason):
        path = '/acme/revoke-cert'
        jws = _build_jws(
            f'http://localhost{path}',
            {'certificate': 'AA', 'reason': reason},
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )
        response = _post_jws(client, path, jws)
        assert response.status_code == 400
        assert response.get_json()['type'].endswith(':badRevocationReason')

    @pytest.mark.parametrize('resource', ['order', 'authz', 'challenge', 'cert'])
    def test_unknown_resource_uses_registered_malformed_type(
        self, client, acme_account, resource
    ):
        path = f'/acme/{resource}/missing-resource'
        jws = _build_jws(
            f'http://localhost{path}',
            None if resource != 'challenge' else {},
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )
        response = _post_jws(client, path, jws)
        assert response.status_code == 404
        assert response.get_json()['type'].endswith(':malformed')


class TestRfc8555StateMachine:
    def test_failed_challenge_invalidates_authorization_and_order(
        self, app, acme_account, monkeypatch
    ):
        with app.app_context():
            service = AcmeService(base_url='http://localhost')
            order = service.create_order(
                acme_account['account_id'],
                [{'type': 'dns', 'value': 'failure.example.com'}],
            )
            authz = order.authorizations.first()
            challenge = next(
                candidate for candidate in authz.challenges
                if candidate.type == 'http-01'
            )

            class Response:
                text = 'wrong-key-authorization'

                @staticmethod
                def raise_for_status():
                    return None

            import requests
            monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: Response())
            account = AcmeAccount.query.filter_by(
                account_id=acme_account['account_id']
            ).first()

            assert service.validate_http01_challenge(challenge, account) is False
            assert challenge.status == 'invalid'
            assert authz.status == 'invalid'
            assert order.status == 'invalid'
            assert json.loads(order.error)['type'].endswith(':incorrectResponse')

    def test_multiple_failed_authorizations_create_compound_order_error(
        self, app, acme_account
    ):
        with app.app_context():
            service = AcmeService(base_url='http://localhost')
            order = service.create_order(
                acme_account['account_id'],
                [
                    {'type': 'dns', 'value': 'first-failure.example.com'},
                    {'type': 'dns', 'value': 'second-failure.example.com'},
                ],
            )
            authorizations = order.authorizations.all()
            first_challenge = authorizations[0].challenges.first()
            second_challenge = authorizations[1].challenges.first()

            service._invalidate_challenge(
                first_challenge, 'dns', 'First authorization failed'
            )
            db.session.commit()
            assert json.loads(order.error)['type'].endswith(':dns')

            service._invalidate_challenge(
                second_challenge, 'incorrectResponse',
                'Second authorization failed',
            )
            db.session.commit()

            problem = json.loads(order.error)
            assert problem['type'].endswith(':compound')
            assert [item['identifier'] for item in problem['subproblems']] == [
                {'type': 'dns', 'value': 'first-failure.example.com'},
                {'type': 'dns', 'value': 'second-failure.example.com'},
            ]
            assert [item['detail'] for item in problem['subproblems']] == [
                'First authorization failed',
                'Second authorization failed',
            ]

    def test_expired_order_is_lazily_marked_invalid(
        self, app, client, acme_account
    ):
        with app.app_context():
            from utils.datetime_utils import utc_now
            order = AcmeOrder(
                account_id=acme_account['account_id'],
                status='pending',
                identifiers=json.dumps([
                    {'type': 'dns', 'value': 'expired-order.example.com'}
                ]),
                expires=utc_now() - timedelta(seconds=1),
            )
            db.session.add(order)
            db.session.commit()
            order_id = order.order_id

        path = f'/acme/order/{order_id}'
        jws = _build_jws(
            f'http://localhost{path}',
            None,
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )
        response = _post_jws(client, path, jws)
        assert response.status_code == 200
        assert response.get_json()['status'] == 'invalid'
        assert response.get_json()['error']['detail'] == 'Order has expired'

    def test_expired_authorization_invalidates_parent_order(
        self, app, client, acme_account
    ):
        with app.app_context():
            from utils.datetime_utils import utc_now
            order = AcmeOrder(
                account_id=acme_account['account_id'],
                status='pending',
                identifiers=json.dumps([
                    {'type': 'dns', 'value': 'expired-authz.example.com'}
                ]),
            )
            db.session.add(order)
            db.session.flush()
            authz = AcmeAuthorization(
                order_id=order.order_id,
                account_id=acme_account['account_id'],
                identifier=json.dumps({
                    'type': 'dns', 'value': 'expired-authz.example.com'
                }),
                status='pending',
                expires=utc_now() - timedelta(seconds=1),
            )
            db.session.add(authz)
            db.session.commit()
            authz_id = authz.authorization_id
            order_id = order.order_id

        path = f'/acme/authz/{authz_id}'
        jws = _build_jws(
            f'http://localhost{path}',
            None,
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )
        response = _post_jws(client, path, jws)
        assert response.status_code == 200
        assert response.get_json()['status'] == 'invalid'
        with app.app_context():
            order = AcmeOrder.query.filter_by(order_id=order_id).first()
            assert order.status == 'invalid'
            assert json.loads(order.error)['detail'] == 'Authorization has expired'

    def test_invalid_order_response_includes_error(
        self, app, client, acme_account
    ):
        problem = {
            'type': 'urn:ietf:params:acme:error:caa',
            'detail': 'CAA policy denied issuance',
        }
        with app.app_context():
            order = AcmeOrder(
                account_id=acme_account['account_id'],
                status='invalid',
                identifiers=json.dumps([
                    {'type': 'dns', 'value': 'denied.example.com'}
                ]),
                error=json.dumps(problem),
            )
            db.session.add(order)
            db.session.commit()
            order_id = order.order_id

        path = f'/acme/order/{order_id}'
        jws = _build_jws(
            f'http://localhost{path}',
            None,
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )
        response = _post_jws(client, path, jws)
        assert response.status_code == 200
        assert response.get_json()['error'] == problem

    def test_finalize_sets_processing_and_maps_caa_error(
        self, app, client, acme_account, monkeypatch
    ):
        with app.app_context():
            order = AcmeOrder(
                account_id=acme_account['account_id'],
                status='ready',
                identifiers=json.dumps([
                    {'type': 'dns', 'value': 'finalize.example.com'}
                ]),
            )
            db.session.add(order)
            db.session.commit()
            order_id = order.order_id

        observed = {}

        def reject_caa(_service, candidate_order_id, _csr_pem):
            current = AcmeOrder.query.filter_by(order_id=candidate_order_id).first()
            observed['status'] = current.status
            return False, 'CAA check failed: issuer is not authorized'

        monkeypatch.setattr(AcmeService, 'finalize_order', reject_caa)
        path = f'/acme/order/{order_id}/finalize'
        jws = _build_jws(
            f'http://localhost{path}',
            {'csr': _csr_b64(acme_account['key'])},
            acme_account['key'],
            kid=f'http://localhost/acme/acct/{acme_account["account_id"]}',
            nonce=_nonce(client),
        )
        response = _post_jws(client, path, jws)
        assert response.status_code == 400
        assert response.get_json()['type'].endswith(':caa')
        assert observed['status'] == 'processing'
        with app.app_context():
            failed_order = AcmeOrder.query.filter_by(order_id=order_id).first()
            assert failed_order.status == 'invalid'
            assert json.loads(failed_order.error)['type'].endswith(':caa')

    def test_processing_transition_reaches_issuance_mixin(
        self, app, acme_account, monkeypatch
    ):
        with app.app_context():
            order = AcmeOrder(
                account_id=acme_account['account_id'],
                status='ready',
                identifiers=json.dumps([
                    {'type': 'dns', 'value': 'finalize.example.com'}
                ]),
            )
            db.session.add(order)
            db.session.commit()

            service = AcmeService(base_url='http://localhost')
            service.begin_order_processing(order)
            service._finalizing_order_id = order.order_id

            from utils import caa_checker
            monkeypatch.setattr(
                caa_checker,
                'check_caa_for_domains',
                lambda *_args, **_kwargs: (True, 'allowed'),
            )
            monkeypatch.setattr(
                service,
                '_resolve_ca_for_domains',
                lambda _domains: 'test-ca',
            )
            monkeypatch.setattr(
                service,
                '_sign_certificate_with_ca',
                lambda **_kwargs: (False, None, 'signing failed'),
            )

            csr_der = b64.urlsafe_b64decode(
                _csr_b64(acme_account['key']) + '=='
            )
            csr_pem = x509.load_der_x509_csr(csr_der).public_bytes(
                serialization.Encoding.PEM
            ).decode()
            success, error = service.finalize_order(order.order_id, csr_pem)
            service._finalizing_order_id = None

            assert success is False
            assert error == 'signing failed'
            db.session.refresh(order)
            assert order.status == 'invalid'


class TestExternalAccountBinding:
    @staticmethod
    def _eab(jwk, kid, key, url):
        protected = _b64json({'alg': 'HS256', 'kid': kid, 'url': url})
        payload = _b64json(jwk)
        signature = b64.urlsafe_b64encode(
            hmac.new(key, f'{protected}.{payload}'.encode(), hashlib.sha256).digest()
        ).rstrip(b'=').decode()
        return {
            'protected': protected,
            'payload': payload,
            'signature': signature,
        }

    def test_eab_url_must_match_and_consumption_is_deferred(
        self, app, acme_account
    ):
        kid = 'rfc8555-eab-deferred'
        key = b'eab-regression-secret'
        key_b64 = b64.urlsafe_b64encode(key).rstrip(b'=').decode()
        with app.app_context():
            config = SystemConfig.query.filter_by(key='acme_eab_keys').first()
            if config is None:
                config = SystemConfig(key='acme_eab_keys', value='{}')
                db.session.add(config)
            config.value = json.dumps({kid: key_b64})
            db.session.commit()

            service = AcmeService(base_url='http://localhost')
            wrong = self._eab(
                acme_account['jwk'], kid, key,
                'http://localhost/acme/not-new-account',
            )
            valid, error = service.validate_eab(
                wrong,
                acme_account['jwk'],
                'http://localhost/acme/new-account',
            )
            assert valid is False
            assert 'url' in error.lower()

            correct = self._eab(
                acme_account['jwk'], kid, key,
                'http://localhost/acme/new-account',
            )
            valid, error = service.validate_eab(
                correct,
                acme_account['jwk'],
                'http://localhost/acme/new-account',
            )
            assert valid is True, error
            assert kid in json.loads(config.value)

            service.mark_eab_used(kid, acme_account['account_id'])
            assert kid not in json.loads(config.value)

    def test_lost_single_use_race_does_not_leave_unbound_account(
        self, app, client, monkeypatch
    ):
        kid = 'rfc8555-eab-race'
        hmac_key = b'eab-race-secret'
        key_b64 = b64.urlsafe_b64encode(hmac_key).rstrip(b'=').decode()
        account_key, account_jwk = _gen_key_and_jwk()
        with app.app_context():
            config = SystemConfig.query.filter_by(key='acme_eab_keys').first()
            if config is None:
                config = SystemConfig(key='acme_eab_keys', value='{}')
                db.session.add(config)
            config.value = json.dumps({kid: key_b64})
            db.session.commit()

        path = '/acme/new-account'
        eab = self._eab(
            account_jwk,
            kid,
            hmac_key,
            f'http://localhost{path}',
        )
        jws = _build_jws(
            f'http://localhost{path}',
            {
                'termsOfServiceAgreed': True,
                'externalAccountBinding': eab,
            },
            account_key,
            jwk=account_jwk,
            nonce=_nonce(client),
        )
        monkeypatch.setattr(
            AcmeService,
            'mark_eab_used',
            lambda *_args, **_kwargs: False,
        )
        response = _post_jws(client, path, jws)
        assert response.status_code == 400
        with app.app_context():
            assert AcmeAccount.query.filter_by(
                jwk_thumbprint=_thumbprint(account_jwk)
            ).first() is None

    def test_table_credential_is_consumed_and_bound_after_validation(
        self, app, acme_account
    ):
        kid = 'rfc8555-eab-table'
        key = b'eab-table-secret'
        key_b64 = b64.urlsafe_b64encode(key).rstrip(b'=').decode()
        with app.app_context():
            credential = AcmeEabCredential(
                kid=kid,
                _hmac_key_b64=key_b64,
                status='active',
            )
            db.session.add(credential)
            db.session.commit()

            service = AcmeService(base_url='http://localhost')
            eab = self._eab(
                acme_account['jwk'],
                kid,
                key,
                'http://localhost/acme/new-account',
            )
            valid, error = service.validate_eab(
                eab,
                acme_account['jwk'],
                'http://localhost/acme/new-account',
            )
            assert valid is True, error
            assert credential.status == 'active'
            assert credential.used_by_account_id is None

            assert service.mark_eab_used(
                kid,
                acme_account['account_id'],
            ) is True
            assert credential.status == 'used'
            assert credential.used_by_account_id == acme_account['account_id']
            assert credential.used_at is not None


class TestKeyChangeConflict:
    """Path #5: key-change must reject a key already in use (keyConflict)."""

    def test_key_change_to_existing_account_key_rejected(self, app, client, acme_account):
        # Second account whose key we will try to steal.
        victim_key, victim_jwk = _gen_key_and_jwk()
        with app.app_context():
            victim = AcmeAccount(
                jwk=json.dumps(victim_jwk),
                jwk_thumbprint=_thumbprint(victim_jwk),
                status='valid',
            )
            db.session.add(victim)
            db.session.commit()

        attacker_key = acme_account['key']
        attacker_jwk = acme_account['jwk']
        attacker_id = acme_account['account_id']
        kc_url = 'http://localhost/acme/key-change'

        # Inner JWS: signed with the NEW (victim's) key.
        inner_protected_b64 = _b64json({'alg': 'RS256', 'jwk': victim_jwk, 'url': kc_url})
        inner_payload_b64 = _b64json({
            'account': f'http://localhost/acme/acct/{attacker_id}',
            'oldKey': attacker_jwk,
        })
        inner_sig = _sign(victim_key, inner_protected_b64, inner_payload_b64)
        inner_jws = {
            'protected': inner_protected_b64,
            'payload': inner_payload_b64,
            'signature': inner_sig,
        }

        # Outer JWS: signed with the OLD (attacker's) key, payload = inner JWS.
        outer = _build_jws(kc_url, inner_jws, attacker_key,
                           kid=f'http://localhost/acme/acct/{attacker_id}',
                           nonce=_nonce(client))
        r = client.post('/acme/key-change',
                        data=json.dumps(outer),
                        content_type='application/jose+json')
        assert r.status_code == 409, r.get_data(as_text=True)

        # Attacker key must be unchanged.
        with app.app_context():
            acct = AcmeAccount.query.filter_by(account_id=attacker_id).first()
            assert json.loads(acct.jwk) == attacker_jwk


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
