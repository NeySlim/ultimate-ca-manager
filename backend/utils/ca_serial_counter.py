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


INDEX = 'uix_certificates_ca_serial'
# PostgreSQL names the index, SQLite the columns
_COLLISION_MARKERS = (INDEX, 'certificates.caref, certificates.serial_number')


def is_serial_collision(exc) -> bool:
    """True when *exc* is the unique (caref, serial_number) index refusing a row."""
    from sqlalchemy.exc import IntegrityError
    return isinstance(exc, IntegrityError) and any(m in str(exc.orig) for m in _COLLISION_MARKERS)


def retry_on_serial_collision(issue):
    """Sign once more with a fresh random serial when the first one is already
    taken under the CA; a second collision is raised, the session rolled back."""
    import functools
    import logging

    @functools.wraps(issue)
    def issue_with_retry(*args, **kwargs):
        from models import db
        for attempt in (1, 2):
            try:
                return issue(*args, **kwargs)
            except Exception as exc:
                if not is_serial_collision(exc):
                    raise
                db.session.rollback()
                if attempt == 2:
                    raise
                logging.getLogger(__name__).warning(
                    'Random serial already issued by this CA; signing again with a new one')
    return issue_with_retry
