"""What a replacing restore leaves behind: no ACME state without its account.

Each case runs on its own installation, on SQLite and on PostgreSQL (which enforces the keys).
"""
import json
import uuid

import pytest

from models import db
from tests.test_backup_cross_installation import Keys, _installation
from tests.test_restore_replace_dependents import (
    ENGINES, _orphans, _restore, _snapshot, _target, _user,
)

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()


@pytest.fixture(params=ENGINES)
def target(request, app, tmp_path):
    schema = f'replace_matrix_{uuid.uuid4().hex[:12]}'
    with _target(app, request.param, tmp_path, schema):
        yield request.param


# -- ACME server state --------------------------------------------------------

STATES = ('order', 'valid_authorization', 'pre_authorization', 'challenge')


def _acme_account(token):
    from models.acme_models import AcmeAccount
    row = AcmeAccount(account_id=token, jwk=json.dumps({'kty': 'EC', 'kid': token}),
                      jwk_thumbprint=f'thumb-{token}', status='valid')
    db.session.add(row)
    db.session.flush()
    return row


def _acme_state(token, state):
    """In-flight protocol rows of one account: {table: [protocol id, ...]}."""
    from models.acme_models import AcmeAuthorization, AcmeChallenge, AcmeOrder
    identifier = json.dumps({'type': 'dns', 'value': 'matrix.example.test'})
    made = {}
    order = None
    if state != 'pre_authorization':
        order = AcmeOrder(account_id=token, status='pending', identifiers=f'[{identifier}]')
        db.session.add(order)
        db.session.flush()
        made['acme_orders'] = [order.order_id]
    if state == 'order':
        return made
    # Linked by its order alone, by its account alone (RFC 8555 §7.4.1), or by both
    authorization = AcmeAuthorization(
        order_id=order.order_id if order else None,
        account_id=None if state == 'valid_authorization' else token,
        identifier=identifier, status='pending' if state == 'challenge' else 'valid')
    db.session.add(authorization)
    db.session.flush()
    made['acme_authorizations'] = [authorization.authorization_id]
    if state == 'challenge':
        challenge = AcmeChallenge(authorization_id=authorization.authorization_id,
                                  type='http-01', status='pending')
        db.session.add(challenge)
        db.session.flush()
        made['acme_challenges'] = [challenge.challenge_id]
    return made


def _protocol_rows():
    from models.acme_models import AcmeAuthorization, AcmeChallenge, AcmeOrder
    return {
        'acme_orders': {(r.order_id, r.account_id, r.status) for r in AcmeOrder.query},
        'acme_authorizations': {(r.authorization_id, r.order_id, r.account_id, r.status)
                                for r in AcmeAuthorization.query},
        'acme_challenges': {(r.challenge_id, r.authorization_id, r.status)
                            for r in AcmeChallenge.query},
    }


def _archive_of_another_installation(app, directory, token=None):
    """A full archive written by an installation of its own, holding this account or none."""
    db.session.commit()
    keys = Keys(directory, 'matrix-source')
    with _installation(app, f"sqlite:///{directory / 'source.db'}", keys), app.app_context():
        _user('replace-admin')
        if token is not None:
            _acme_account(token)
        blob = _snapshot()
    return blob


@pytest.mark.parametrize('archive', ['same_older', 'other'])
@pytest.mark.parametrize('state', STATES)
@pytest.mark.parametrize('account', ['kept', 'removed'])
def test_no_acme_server_state_outlives_its_account(target, app, tmp_path, archive, state,
                                                   account):
    token = f'matrix-{uuid.uuid4().hex[:16]}'
    _user('replace-admin')
    blob = None
    if archive == 'same_older':
        if account == 'kept':
            _acme_account(token)
        blob = _snapshot()
    if not (archive == 'same_older' and account == 'kept'):
        _acme_account(token)
    made = _acme_state(token, state)
    db.session.commit()
    before = _protocol_rows()
    if archive == 'other':
        blob = _archive_of_another_installation(
            app, tmp_path, token if account == 'kept' else None)

    results = _restore(blob)

    after = _protocol_rows()
    cleared = {k: v for k, v in results['cleared_dependents'].items() if k.startswith('acme_')}
    if account == 'kept':
        assert after == before
        assert cleared == {}
    else:
        assert after == {name: set() for name in after}
        assert cleared == {name: len(ids) for name, ids in made.items()}
    assert _orphans() == []
