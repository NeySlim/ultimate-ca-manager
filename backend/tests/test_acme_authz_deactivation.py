"""#422: RFC 8555 §7.5.2 authorization deactivation on the native ACME server.

A pending or valid authorization of the requesting account can be deactivated;
its open orders become invalid. A reused authorization is a copy carrying its
source's expiry (#338), so the account's other valid copies of the same proof
go with it, while an independent validation stays.
"""
import json
from datetime import timedelta

import pytest

from models import db
from models.acme_models import AcmeAccount, AcmeAuthorization, AcmeChallenge, AcmeOrder
from services.acme.acme_service import AcmeService
from utils.datetime_utils import utc_now
from tests.test_acme_security_paths import (
    _build_jws,
    _gen_key_and_jwk,
    _nonce,
    _thumbprint,
    acme_account,  # noqa: F401  (fixture)
)

DOMAIN = 'deact-native.example.com'


def _order(account_id, status='pending'):
    order = AcmeOrder(account_id=account_id, status=status,
                      identifiers=json.dumps([{'type': 'dns', 'value': DOMAIN}]))
    db.session.add(order)
    db.session.flush()
    return order


def _authz(account_id, order=None, status='pending', expires=None):
    authz = AcmeAuthorization(
        order_id=order.order_id if order else None,
        account_id=account_id,
        identifier=json.dumps({'type': 'dns', 'value': DOMAIN}),
        status=status,
        expires=expires or utc_now() + timedelta(days=7),
    )
    db.session.add(authz)
    db.session.flush()
    return authz


def _post(client, account, authorization_id, payload):
    path = f'/acme/authz/{authorization_id}'
    jws = _build_jws(f'http://localhost{path}', payload, account['key'],
                     kid=f'http://localhost/acme/acct/{account["account_id"]}',
                     nonce=_nonce(client))
    return client.post(path, data=json.dumps(jws), content_type='application/jose+json')


def _status(model, ident):
    db.session.expire_all()
    if model is AcmeOrder:
        return AcmeOrder.query.filter_by(order_id=ident).one().status
    return AcmeAuthorization.query.filter_by(authorization_id=ident).one().status


class TestDeactivation:
    def test_pending_authz_is_deactivated_and_its_order_invalid(
            self, app, client, acme_account):  # noqa: F811
        with app.app_context():
            order = _order(acme_account['account_id'])
            authz = _authz(acme_account['account_id'], order)
            db.session.commit()
            order_id, authz_id = order.order_id, authz.authorization_id

        r = _post(client, acme_account, authz_id, {'status': 'deactivated'})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['status'] == 'deactivated'
        with app.app_context():
            assert _status(AcmeAuthorization, authz_id) == 'deactivated'
            assert _status(AcmeOrder, order_id) == 'invalid'
            error = json.loads(AcmeOrder.query.filter_by(order_id=order_id).one().error)
            assert error['type'].endswith(':unauthorized')

    def test_valid_authz_takes_its_reused_copies_but_not_an_independent_one(
            self, app, client, acme_account):  # noqa: F811
        acct = acme_account['account_id']
        expires = (utc_now() + timedelta(days=30)).replace(microsecond=0)
        with app.app_context():
            done = _order(acct, status='valid')
            source = _authz(acct, done, status='valid', expires=expires)
            ready = _order(acct, status='ready')
            copy_ = _authz(acct, ready, status='valid', expires=expires)
            other = _order(acct, status='ready')
            independent = _authz(acct, other, status='valid',
                                 expires=expires + timedelta(days=1))
            db.session.commit()
            ids = dict(done=done.order_id, source=source.authorization_id,
                       ready=ready.order_id, copy=copy_.authorization_id,
                       other=other.order_id, independent=independent.authorization_id)

        r = _post(client, acme_account, ids['source'], {'status': 'deactivated'})
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            assert _status(AcmeAuthorization, ids['source']) == 'deactivated'
            assert _status(AcmeAuthorization, ids['copy']) == 'deactivated'
            assert _status(AcmeOrder, ids['ready']) == 'invalid'
            # A finished order stays finished; an independent proof stays valid
            assert _status(AcmeOrder, ids['done']) == 'valid'
            assert _status(AcmeAuthorization, ids['independent']) == 'valid'
            assert _status(AcmeOrder, ids['other']) == 'ready'

    def test_second_deactivation_answers_deactivated(self, app, client, acme_account):  # noqa: F811
        with app.app_context():
            authz = _authz(acme_account['account_id'])
            db.session.commit()
            authz_id = authz.authorization_id
        assert _post(client, acme_account, authz_id, {'status': 'deactivated'}).status_code == 200
        r = _post(client, acme_account, authz_id, {'status': 'deactivated'})
        assert r.status_code == 200
        assert r.get_json()['status'] == 'deactivated'


class TestRefusals:
    @pytest.mark.parametrize('status', ['invalid', 'expired', 'revoked'])
    def test_only_pending_or_valid_can_be_deactivated(
            self, app, client, acme_account, status):  # noqa: F811
        with app.app_context():
            authz = _authz(acme_account['account_id'], status=status)
            db.session.commit()
            authz_id = authz.authorization_id
        r = _post(client, acme_account, authz_id, {'status': 'deactivated'})
        assert r.status_code == 400
        assert r.get_json()['type'].endswith(':malformed')
        with app.app_context():
            assert _status(AcmeAuthorization, authz_id) == status

    @pytest.mark.parametrize('payload', [{'status': 'valid'}, {'foo': 1}, {}])
    def test_any_other_payload_stays_malformed(
            self, app, client, acme_account, payload):  # noqa: F811
        with app.app_context():
            authz = _authz(acme_account['account_id'])
            db.session.commit()
            authz_id = authz.authorization_id
        r = _post(client, acme_account, authz_id, payload)
        assert r.status_code == 400
        assert r.get_json()['type'].endswith(':malformed')
        with app.app_context():
            assert _status(AcmeAuthorization, authz_id) == 'pending'

    def test_another_account_cannot_deactivate(self, app, client, acme_account):  # noqa: F811
        key, jwk = _gen_key_and_jwk()
        with app.app_context():
            intruder = AcmeAccount(jwk=json.dumps(jwk), jwk_thumbprint=_thumbprint(jwk),
                                   status='valid')
            db.session.add(intruder)
            authz = _authz(acme_account['account_id'])
            db.session.commit()
            authz_id = authz.authorization_id
            intruder_id = intruder.account_id
        r = _post(client, {'key': key, 'account_id': intruder_id}, authz_id,
                  {'status': 'deactivated'})
        assert r.status_code == 403
        with app.app_context():
            assert _status(AcmeAuthorization, authz_id) == 'pending'


class TestNoResurrection:
    """A validation that finishes after the deactivation leaves it final."""

    def _deactivated_with_challenge(self, app, account_id, challenge_status):
        with app.app_context():
            order = _order(account_id)
            authz = _authz(account_id, order)
            challenge = AcmeChallenge(authorization_id=authz.authorization_id, type='dns-01',
                                      token='tok-422', status=challenge_status)
            db.session.add(challenge)
            db.session.commit()
            AcmeService().deactivate_authorization(authz)
            return order.order_id, authz.authorization_id, challenge.id

    def test_a_late_valid_challenge_does_not_revalidate(self, app, acme_account):  # noqa: F811
        order_id, authz_id, _ = self._deactivated_with_challenge(
            app, acme_account['account_id'], 'valid')
        with app.app_context():
            authz = AcmeAuthorization.query.filter_by(authorization_id=authz_id).one()
            AcmeService()._update_authorization_status(authz)
            db.session.commit()
            assert _status(AcmeAuthorization, authz_id) == 'deactivated'
            assert _status(AcmeOrder, order_id) == 'invalid'

    def test_a_deactivation_committed_during_the_validation_is_seen(
            self, app, acme_account):  # noqa: F811
        """The validating request loaded the authz while it was still pending."""
        from sqlalchemy import text
        with app.app_context():
            order = _order(acme_account['account_id'])
            authz = _authz(acme_account['account_id'], order)
            db.session.add(AcmeChallenge(authorization_id=authz.authorization_id,
                                         type='dns-01', token='tok-422b', status='valid'))
            db.session.commit()
            assert authz.status == 'pending'
            db.session.execute(text("UPDATE acme_authorizations SET status = 'deactivated' "
                                    "WHERE authorization_id = :a"),
                               {'a': authz.authorization_id})
            AcmeService()._update_authorization_status(authz)
            db.session.commit()
            assert _status(AcmeAuthorization, authz.authorization_id) == 'deactivated'
            assert _status(AcmeOrder, order.order_id) == 'pending'

    def test_a_deactivation_committed_before_a_failure_is_seen(
            self, app, acme_account):  # noqa: F811
        from sqlalchemy import text
        with app.app_context():
            order = _order(acme_account['account_id'])
            authz = _authz(acme_account['account_id'], order)
            challenge = AcmeChallenge(authorization_id=authz.authorization_id,
                                      type='dns-01', token='tok-422c', status='processing')
            db.session.add(challenge)
            db.session.commit()
            assert challenge.authorization.status == 'pending'
            db.session.execute(text("UPDATE acme_authorizations SET status = 'deactivated' "
                                    "WHERE authorization_id = :a"),
                               {'a': authz.authorization_id})
            AcmeService()._invalidate_challenge(challenge, 'dns', 'late failure')
            db.session.commit()
            assert _status(AcmeAuthorization, authz.authorization_id) == 'deactivated'
            assert _status(AcmeOrder, order.order_id) == 'pending'

    def test_a_late_failed_challenge_does_not_turn_it_invalid(self, app, acme_account):  # noqa: F811
        _, authz_id, challenge_id = self._deactivated_with_challenge(
            app, acme_account['account_id'], 'processing')
        with app.app_context():
            challenge = db.session.get(AcmeChallenge, challenge_id)
            AcmeService()._invalidate_challenge(challenge, 'dns', 'late failure')
            db.session.commit()
            assert _status(AcmeAuthorization, authz_id) == 'deactivated'
