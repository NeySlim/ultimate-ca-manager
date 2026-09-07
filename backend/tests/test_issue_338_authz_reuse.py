"""Issue #338: a reused ACME authorization records the challenge that was
performed, at the time it was performed, and the Orders tab derives an
order's method from the validated challenge(s), not from the first
challenge row (always dns-01, the first type offered)."""
import json
from datetime import timedelta

import pytest

from models import db
from models.acme_models import (
    AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge,
)
from services.acme.acme_service import AcmeService
from api.v2.acme.orders import order_validation_method
from utils.datetime_utils import utc_now
from tests.conftest import assert_success
from tests.test_acme_security_paths import (
    _build_jws, _gen_key_and_jwk, _nonce, _thumbprint,
)


@pytest.fixture
def account(app):
    key, jwk = _gen_key_and_jwk()
    with app.app_context():
        acct = AcmeAccount(
            jwk=json.dumps(jwk), jwk_thumbprint=_thumbprint(jwk), status='valid',
        )
        db.session.add(acct)
        db.session.commit()
        return {'key': key, 'account_id': acct.account_id, 'pk': acct.id}


def _order(account_id, *values):
    order = AcmeOrder(
        account_id=account_id,
        status='pending',
        identifiers=json.dumps([{'type': 'dns', 'value': v} for v in values]),
    )
    db.session.add(order)
    db.session.flush()
    return order


def _authz(account_id, value, order_id=None, status='pending'):
    authz = AcmeAuthorization(
        order_id=order_id,
        account_id=account_id,
        identifier=json.dumps({'type': 'dns', 'value': value}),
        wildcard=False,
        status=status,
        expires=utc_now() + timedelta(days=7),
    )
    db.session.add(authz)
    db.session.flush()
    return authz


def _challenge(authz, ctype, status='pending', validated=None, error=None):
    challenge = AcmeChallenge(
        authorization_id=authz.authorization_id,
        type=ctype,
        status=status,
        url=f'http://localhost/acme/challenge/{authz.authorization_id}-{ctype}',
        validated=validated,
        error=json.dumps(error) if error else None,
    )
    authz.challenges.append(challenge)
    db.session.flush()
    return challenge


def _http01_validated_authz(account_id, value, validated_at, order_id=None,
                            legacy_siblings=False):
    """A valid authorization proven by http-01 at ``validated_at``.

    ``legacy_siblings`` adds the pending dns-01 / tls-alpn-01 rows that
    authorizations validated before sibling deprovisioning still carry.
    """
    authz = _authz(account_id, value, order_id=order_id, status='valid')
    if legacy_siblings:
        _challenge(authz, 'dns-01')
    _challenge(authz, 'http-01', status='valid', validated=validated_at)
    if legacy_siblings:
        _challenge(authz, 'tls-alpn-01')
    return authz


class TestAuthorizationReuse:
    def test_reuse_carries_the_performed_challenge_and_its_timestamp(
        self, app, account
    ):
        with app.app_context():
            acct = account['account_id']
            validated_at = (utc_now() - timedelta(minutes=13)).replace(microsecond=0)
            first = _order(acct, 'host.example.test')
            source = _http01_validated_authz(
                acct, 'host.example.test', validated_at, order_id=first.order_id,
            )
            source_url = source.challenges.filter_by(type='http-01').one().url

            renewal = _order(acct, 'host.example.test')
            before = utc_now() - timedelta(seconds=1)
            authz = AcmeService(base_url='http://localhost')._create_authorization(
                renewal.order_id, {'type': 'dns', 'value': 'host.example.test'},
                account_id=acct,
            )

            assert authz.status == 'valid'
            assert authz.authorization_id != source.authorization_id
            assert authz.expires == source.expires
            challenges = list(authz.challenges)
            assert [c.type for c in challenges] == ['http-01']
            copied = challenges[0]
            assert copied.status == 'valid'
            assert copied.validated == validated_at
            assert copied.validated < before
            assert copied.url != source_url

    def test_reuse_skips_pending_siblings_of_a_legacy_authorization(
        self, app, account
    ):
        with app.app_context():
            acct = account['account_id']
            validated_at = utc_now() - timedelta(hours=1)
            first = _order(acct, 'legacy.example.test')
            _http01_validated_authz(
                acct, 'legacy.example.test', validated_at,
                order_id=first.order_id, legacy_siblings=True,
            )
            renewal = _order(acct, 'legacy.example.test')
            authz = AcmeService(base_url='http://localhost')._create_authorization(
                renewal.order_id, {'type': 'dns', 'value': 'legacy.example.test'},
                account_id=acct,
            )
            assert [(c.type, c.status) for c in authz.challenges] == [('http-01', 'valid')]

    def test_new_order_over_the_wire_lists_only_the_performed_challenge(
        self, app, client, account
    ):
        acct = account['account_id']
        kid = f'http://localhost/acme/acct/{acct}'
        with app.app_context():
            validated_at = (utc_now() - timedelta(minutes=13)).replace(microsecond=0)
            first = _order(acct, 'wire.example.test')
            _http01_validated_authz(
                acct, 'wire.example.test', validated_at, order_id=first.order_id,
            )
            db.session.commit()
            expected_validated = validated_at.isoformat() + 'Z'

        path = '/acme/new-order'
        jws = _build_jws(
            f'http://localhost{path}',
            {'identifiers': [{'type': 'dns', 'value': 'wire.example.test'}]},
            account['key'], kid=kid, nonce=_nonce(client),
        )
        response = client.post(path, data=json.dumps(jws), content_type='application/jose+json')
        assert response.status_code == 201
        order_body = response.get_json()
        assert order_body['status'] == 'ready'

        authz_path = order_body['authorizations'][0].removeprefix('http://localhost')
        jws = _build_jws(
            f'http://localhost{authz_path}', None, account['key'],
            kid=kid, nonce=_nonce(client),
        )
        response = client.post(authz_path, data=json.dumps(jws), content_type='application/jose+json')
        assert response.status_code == 200
        body = response.get_json()
        assert body['status'] == 'valid'
        assert [(c['type'], c['status'], c['validated']) for c in body['challenges']] == [
            ('http-01', 'valid', expected_validated),
        ]


class TestOrderValidationMethod:
    def test_method_is_the_validated_challenge_not_the_first_row(
        self, app, account
    ):
        with app.app_context():
            order = _order(account['account_id'], 'valid.example.test')
            _http01_validated_authz(
                account['account_id'], 'valid.example.test', utc_now(),
                order_id=order.order_id, legacy_siblings=True,
            )
            assert order_validation_method(order) == 'HTTP-01'

    def test_method_lists_each_identifier_validation_once(self, app, account):
        with app.app_context():
            acct = account['account_id']
            order = _order(acct, 'a.example.test', 'b.example.test', 'c.example.test')
            a = _authz(acct, 'a.example.test', order_id=order.order_id, status='valid')
            _challenge(a, 'dns-01', status='valid', validated=utc_now())
            b = _authz(acct, 'b.example.test', order_id=order.order_id, status='valid')
            _challenge(b, 'http-01', status='valid', validated=utc_now())
            c = _authz(acct, 'c.example.test', order_id=order.order_id, status='valid')
            _challenge(c, 'dns-01', status='valid', validated=utc_now())
            assert order_validation_method(order) == 'DNS-01, HTTP-01'

    def test_method_names_the_attempted_challenge_when_validation_failed(
        self, app, account
    ):
        with app.app_context():
            acct = account['account_id']
            order = _order(acct, 'forbidden.example.test')
            order.status = 'invalid'
            authz = _authz(acct, 'forbidden.example.test', order_id=order.order_id, status='invalid')
            _challenge(authz, 'dns-01')
            _challenge(authz, 'http-01', status='invalid', error={
                'type': 'urn:ietf:params:acme:error:rejectedIdentifier',
                'detail': 'Identifier targets a forbidden address',
            })
            _challenge(authz, 'tls-alpn-01')
            assert order_validation_method(order) == 'HTTP-01'

    def test_method_merges_validated_and_failed_identifiers(self, app, account):
        # dns-01 proved a.example, http-01 failed on b.example: both are named.
        with app.app_context():
            acct = account['account_id']
            order = _order(acct, 'a.mixed.example.test', 'b.mixed.example.test')
            order.status = 'invalid'
            a = _authz(acct, 'a.mixed.example.test', order_id=order.order_id, status='valid')
            _challenge(a, 'dns-01', status='valid', validated=utc_now())
            b = _authz(acct, 'b.mixed.example.test', order_id=order.order_id, status='invalid')
            _challenge(b, 'dns-01')
            _challenge(b, 'http-01', status='invalid', error={
                'type': 'urn:ietf:params:acme:error:connection',
                'detail': 'Connection refused',
            })
            assert order_validation_method(order) == 'DNS-01, HTTP-01'

    def test_method_is_na_when_no_challenge_was_answered(self, app, account):
        with app.app_context():
            acct = account['account_id']
            pending = _order(acct, 'pending.example.test')
            authz = _authz(acct, 'pending.example.test', order_id=pending.order_id)
            for ctype in ('dns-01', 'http-01', 'tls-alpn-01'):
                _challenge(authz, ctype)
            assert order_validation_method(pending) == 'N/A'

            expired = _order(acct, 'expired.example.test')
            authz = _authz(acct, 'expired.example.test', order_id=expired.order_id)
            for ctype in ('dns-01', 'http-01', 'tls-alpn-01'):
                _challenge(authz, ctype)
            AcmeService(base_url='http://localhost')._expire_authorization(
                authz, update_order=True,
            )
            assert expired.status == 'invalid'
            assert all(c.status == 'invalid' for c in authz.challenges)
            assert order_validation_method(expired) == 'N/A'

            empty = _order(acct, 'empty.example.test')
            assert order_validation_method(empty) == 'N/A'

    def test_orders_endpoints_expose_the_validated_method(
        self, app, auth_client, account
    ):
        acct = account['account_id']
        with app.app_context():
            order = _order(acct, 'api.example.test')
            _http01_validated_authz(
                acct, 'api.example.test', utc_now(),
                order_id=order.order_id, legacy_siblings=True,
            )
            db.session.commit()
            order_id = order.order_id

        data = assert_success(auth_client.get('/api/v2/acme/orders?domain=api.example.test'))
        row = next(o for o in data['items'] if o['order_id'] == order_id)
        assert row['method'] == 'HTTP-01'

        data = assert_success(auth_client.get(f"/api/v2/acme/accounts/{account['pk']}/orders"))
        row = next(o for o in data if o['order_id'] == order_id)
        assert row['method'] == 'HTTP-01'
