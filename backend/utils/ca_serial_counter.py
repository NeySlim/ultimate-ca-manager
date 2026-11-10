"""The count of certificates a CA issued, kept in ``certificate_authorities.serial``.

Signed serials are random (RFC 5280 §4.1.2.2); this counter only counts. It is
incremented by one UPDATE in the database, so concurrent workers never lose a count.
"""
from sqlalchemy import func, update
from sqlalchemy.orm.attributes import set_committed_value


def next_ca_serial(ca) -> int:
    """Count one more issuance under *ca* in the current transaction; return the new count."""
    from models import CA, db
    table = CA.__table__
    # A Core statement: no autoflush, the row lock (PostgreSQL) is held until the commit
    count = db.session.execute(
        update(table).where(table.c.id == ca.id)
        .values(serial=func.coalesce(table.c.serial, 0) + 1)
        .returning(table.c.serial)).scalar_one()
    set_committed_value(ca, 'serial', count)
    return count
