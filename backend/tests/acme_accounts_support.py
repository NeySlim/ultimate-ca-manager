"""The ACME accounts a test file created leave with it (conftest), as the account route
deletes one: challenges and authorizations, orders, the client orders' link, the account."""
from sqlalchemy import or_


def account_ids(app):
    from models import db
    from models.acme_models import AcmeAccount
    with app.app_context():
        try:
            return {row.account_id for row in db.session.query(AcmeAccount.account_id)}
        finally:
            db.session.remove()


def drop_accounts_but(app, kept):
    """Delete every ACME account not in ``kept`` and what names it; returns how many."""
    from models import db
    from models.acme_models import (AcmeAccount, AcmeAuthorization, AcmeChallenge, AcmeClientOrder,
                                    AcmeOrder)
    with app.app_context():
        try:
            gone = sorted({row.account_id for row in db.session.query(AcmeAccount.account_id)} - set(kept))
            if not gone:
                return 0
            orders = [row.order_id for row in db.session.query(AcmeOrder.order_id)
                      .filter(AcmeOrder.account_id.in_(gone))]
            # An authorization names its account, its order, or both (RFC 8555 allows one before any order)
            owned = [AcmeAuthorization.account_id.in_(gone)]
            if orders:
                owned.append(AcmeAuthorization.order_id.in_(orders))
            authorizations = [row.authorization_id for row in db.session.query(
                AcmeAuthorization.authorization_id).filter(or_(*owned))]
            if authorizations:
                AcmeChallenge.query.filter(AcmeChallenge.authorization_id.in_(authorizations)).delete(
                    synchronize_session=False)
                AcmeAuthorization.query.filter(AcmeAuthorization.authorization_id.in_(authorizations)).delete(
                    synchronize_session=False)
            AcmeOrder.query.filter(AcmeOrder.account_id.in_(gone)).delete(synchronize_session=False)
            AcmeClientOrder.query.filter(AcmeClientOrder.account_id.in_(gone)).update(
                {'account_id': None}, synchronize_session=False)
            AcmeAccount.query.filter(AcmeAccount.account_id.in_(gone)).delete(synchronize_session=False)
            db.session.commit()
            return len(gone)
        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.remove()
