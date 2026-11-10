"""Rows the tests write directly, in a shape PostgreSQL's constraints accept.

What the two seeding helpers create is recorded and removed after the module
(`remove_seeded`, called from conftest).
"""
from flask import current_app
from sqlalchemy import text

from models import AcmeAccount, db

_SEEDED = []  # (application, table, key column, value)


def ensure_acme_account(account_id):
    """The local ACME account an order names: PostgreSQL enforces the foreign key."""
    if account_id and AcmeAccount.query.filter_by(account_id=account_id).first() is None:
        db.session.add(AcmeAccount(account_id=account_id, jwk='{}',
                                   jwk_thumbprint=f'seeded-{account_id}'))
        db.session.flush()
        _SEEDED.append((current_app._get_current_object(), 'acme_accounts', 'account_id', account_id))


def placeholder_certificate_id():
    """A certificate row an order can point at where the test only needs an id."""
    from models import Certificate

    row = Certificate.query.filter_by(refid='test-placeholder-certificate').first()
    if row is None:
        row = Certificate(refid='test-placeholder-certificate', descr='test placeholder')
        db.session.add(row)
        db.session.commit()
        _SEEDED.append((current_app._get_current_object(), 'certificates', 'id', row.id))
    return row.id


def remove_seeded():
    """Delete the recorded rows, references to them cleared where the column allows
    it; a row still held by a non-nullable reference is left."""
    from services.database_admin.helpers import _force_register_all_models

    _force_register_all_models()
    while _SEEDED:
        application, table, column, value = _SEEDED.pop()
        with application.app_context():
            db.session.rollback()
            held = False
            for child in db.metadata.sorted_tables:
                for fk in child.foreign_keys:
                    if fk.column.table.name != table or fk.column.name != column:
                        continue
                    where = f'"{child.name}"."{fk.parent.name}" = :v'
                    if fk.parent.nullable:
                        db.session.execute(text(
                            f'UPDATE "{child.name}" SET "{fk.parent.name}" = NULL WHERE {where}'), {'v': value})
                    elif db.session.execute(text(f'SELECT 1 FROM "{child.name}" WHERE {where}'),
                                            {'v': value}).first():
                        held = True
            if not held:
                db.session.execute(text(f'DELETE FROM "{table}" WHERE "{column}" = :v'), {'v': value})
            db.session.commit()


def delete_client_accounts(query, **kwargs):
    """Delete the CA accounts ``query`` selects, their orders detached first as the
    product does: PostgreSQL refuses the delete while an order points at one."""
    from models import AcmeClientAccount, AcmeClientOrder

    ids = [row.id for row in query.with_entities(AcmeClientAccount.id)]
    if ids:
        AcmeClientOrder.query.filter(AcmeClientOrder.acme_client_account_id.in_(ids)).update(
            {AcmeClientOrder.acme_client_account_id: None}, synchronize_session=False)
    return query.delete(**kwargs)


def delete_cas(query):
    """Delete the CAs ``query`` selects with what references them, which
    PostgreSQL would otherwise refuse: their certificates, ACME domain
    mappings, CRLs, OCSP responses, SCEP requests and revoked serials."""
    from models import Certificate
    from models.acme_models import AcmeDomain, AcmeLocalDomain
    from models.crl import CRLMetadata
    from models.ocsp import OCSPResponse
    from models.revoked_serial import RevokedSerial
    from models.scep import SCEPRequest

    for ca in query.all():
        Certificate.query.filter_by(caref=ca.refid).delete(synchronize_session=False)
        RevokedSerial.query.filter_by(caref=ca.refid).delete(synchronize_session=False)
        SCEPRequest.query.filter_by(ca_refid=ca.refid).delete(synchronize_session=False)
        AcmeDomain.query.filter_by(issuing_ca_id=ca.id).update(
            {AcmeDomain.issuing_ca_id: None}, synchronize_session=False)
        AcmeLocalDomain.query.filter_by(issuing_ca_id=ca.id).delete(synchronize_session=False)
        CRLMetadata.query.filter_by(ca_id=ca.id).delete(synchronize_session=False)
        OCSPResponse.query.filter_by(ca_id=ca.id).delete(synchronize_session=False)
        db.session.delete(ca)
