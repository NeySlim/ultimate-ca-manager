"""CRL numbers: one increasing sequence per CRL issuer (RFC 5280 §5.2.3).

The number is allocated under the lock of the issuer's counter row, held until
the caller commits the CRL row, so two processes never sign two CRLs under one
number. The counter is the floor, so the sequence survives a restore and a re-import.
"""
from cryptography import x509
from sqlalchemy import func, select

from models import db, CA
from models.crl import CRLMetadata, CRLNumberCounter
from utils.crl_issuer import crl_issuer_key


def _locked_counter(issuer_key: str) -> CRLNumberCounter:
    """The issuer's counter row, locked until the caller commits.

    The upsert is a write and comes first: on SQLite it takes the database write
    lock before anything is read; on PostgreSQL FOR UPDATE takes the row lock.
    """
    dialect = db.session.connection().dialect.name
    if dialect == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    db.session.execute(insert(CRLNumberCounter.__table__)
                       .values(issuer_key=issuer_key, last_number=0)
                       .on_conflict_do_nothing(index_elements=['issuer_key']))
    return (CRLNumberCounter.query.filter_by(issuer_key=issuer_key)
            .with_for_update().populate_existing().one())


def allocate_crl_number(ca: CA, ca_cert: x509.Certificate) -> int:
    """The next number for this CA's CRLs, base and delta alike.

    Taken under the lock and recorded in the caller's transaction: the caller
    commits it with the CRL row, or rolls both back.
    """
    counter = _locked_counter(crl_issuer_key(ca_cert))
    highest = db.session.execute(
        select(func.max(CRLMetadata.crl_number)).where(CRLMetadata.ca_id == ca.id)
    ).scalar() or 0
    number = max(counter.last_number or 0, highest) + 1
    counter.last_number = number
    db.session.flush()
    return number


def record_crl_number(ca: CA, ca_cert: x509.Certificate, number: int) -> None:
    """Raise the floor to a number published outside this server (external CRL)."""
    counter = _locked_counter(crl_issuer_key(ca_cert))
    if number > (counter.last_number or 0):
        counter.last_number = number
    db.session.flush()
