"""Regression tests for ACME server security paths (RFC 8555).

Covers challenge state transitions, authenticated resource reads,
pre-authorizations, wildcard authorizations, and key-change conflicts.
"""
import base64 as b64
import hashlib
import json

import pytest

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes

from models import db
from models.acme_models import (
    AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge,
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
    import hashlib
    canonical = json.dumps(
        {'e': jwk['e'], 'kty': jwk['kty'], 'n': jwk['n']},
        separators=(',', ':'), sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode()).digest()
    return b64.urlsafe_b64encode(digest).rstrip(b'=').decode()


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
            response = client.post(path, json={})
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
