"""tests.acme_accounts_support: a file's ACME accounts leave with it, and what names them."""
import uuid

from models import db
from models.acme_models import (AcmeAccount, AcmeAuthorization, AcmeChallenge, AcmeClientOrder,
                                AcmeOrder)
from tests.acme_accounts_support import account_ids, drop_accounts_but


def _account(tag):
    row = AcmeAccount(account_id=f'support-{tag}-{uuid.uuid4().hex[:8]}', jwk='{}',
                      jwk_thumbprint=f'support-{uuid.uuid4().hex}')
    db.session.add(row)
    db.session.flush()
    return row.account_id


def test_the_new_accounts_leave_with_their_rows_and_the_old_stay(app):
    with app.app_context():
        kept_account = _account('kept')
        kept_order = AcmeOrder(account_id=kept_account, identifiers='[]')
        db.session.add(kept_order)
        db.session.commit()
        kept_order_id = kept_order.order_id
    before = account_ids(app)
    with app.app_context():
        gone = _account('gone')
        order = AcmeOrder(account_id=gone, identifiers='[]')
        db.session.add(order)
        db.session.flush()
        by_order = AcmeAuthorization(order_id=order.order_id, identifier='{}')
        by_account = AcmeAuthorization(account_id=gone, identifier='{}')
        db.session.add_all([by_order, by_account])
        db.session.flush()
        db.session.add(AcmeChallenge(authorization_id=by_order.authorization_id, type='http-01'))
        client = AcmeClientOrder(domains='["support.example"]', account_id=gone)
        db.session.add(client)
        db.session.commit()
        authorizations = [by_order.authorization_id, by_account.authorization_id]
        client_id = client.id

    assert drop_accounts_but(app, before) == 1

    with app.app_context():
        try:
            assert AcmeAccount.query.filter_by(account_id=gone).count() == 0
            assert AcmeOrder.query.filter_by(account_id=gone).count() == 0
            assert AcmeAuthorization.query.filter(AcmeAuthorization.authorization_id.in_(authorizations)).count() == 0
            assert AcmeChallenge.query.filter(AcmeChallenge.authorization_id.in_(authorizations)).count() == 0
            assert db.session.get(AcmeClientOrder, client_id).account_id is None
            assert AcmeOrder.query.filter_by(order_id=kept_order_id).count() == 1
        finally:
            db.session.delete(db.session.get(AcmeClientOrder, client_id))
            AcmeOrder.query.filter_by(order_id=kept_order_id).delete()
            AcmeAccount.query.filter_by(account_id=kept_account).delete()
            db.session.commit()


def test_nothing_new_is_nothing_removed(app):
    assert drop_accounts_but(app, account_ids(app)) == 0
