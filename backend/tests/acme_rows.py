"""Rows the ACME tests reference without going through the protocol."""
from models import AcmeAccount, db


def ensure_acme_account(account_id):
    """The local ACME account an order names: PostgreSQL enforces the foreign key."""
    if account_id and AcmeAccount.query.filter_by(account_id=account_id).first() is None:
        db.session.add(AcmeAccount(account_id=account_id, jwk='{}',
                                   jwk_thumbprint=f'seeded-{account_id}'))
        db.session.flush()


def placeholder_certificate_id():
    """A certificate row an order can point at where the test only needs an id."""
    from models import Certificate

    row = Certificate.query.filter_by(refid='test-placeholder-certificate').first()
    if row is None:
        row = Certificate(refid='test-placeholder-certificate', descr='test placeholder')
        db.session.add(row)
        db.session.commit()
    return row.id


def delete_client_accounts(query, **kwargs):
    """Delete the CA accounts ``query`` selects, their orders detached first as the
    product does: PostgreSQL refuses the delete while an order points at one."""
    from models import AcmeClientAccount, AcmeClientOrder

    ids = [row.id for row in query.with_entities(AcmeClientAccount.id)]
    if ids:
        AcmeClientOrder.query.filter(AcmeClientOrder.acme_client_account_id.in_(ids)).update(
            {AcmeClientOrder.acme_client_account_id: None}, synchronize_session=False)
    return query.delete(**kwargs)
