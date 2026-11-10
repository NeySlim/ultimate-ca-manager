"""The count of certificates a CA issued, kept in ``certificate_authorities.serial``.

Signed serials are random (RFC 5280 §4.1.2.2); this counter only counts. It is
incremented by one UPDATE in the database, so concurrent workers never lose a count.
"""
from sqlalchemy import func, select, update
from sqlalchemy.orm.attributes import set_committed_value


def next_ca_serial(ca) -> int:
    """Count one more issuance under *ca* in the current transaction; return the new count."""
    from models import CA, db
    table = CA.__table__
    # A Core statement: no autoflush, the row lock (PostgreSQL) is held until the commit
    bump = (update(table).where(table.c.id == ca.id)
            .values(serial=func.coalesce(table.c.serial, 0) + 1))
    if not db.session.get_bind().dialect.update_returning:
        # SQLite before 3.35: no RETURNING; the UPDATE holds the write lock until the commit
        db.session.execute(bump)
        count = db.session.execute(
            select(table.c.serial).where(table.c.id == ca.id)).scalar_one()
    else:
        count = db.session.execute(bump.returning(table.c.serial)).scalar_one()
    set_committed_value(ca, 'serial', count)
    return count


INDEX = 'uix_certificates_ca_serial'
# PostgreSQL names the index, SQLite the columns
_COLLISION_MARKERS = (INDEX, 'certificates.caref, certificates.serial_number')


def is_serial_collision(exc) -> bool:
    """True when *exc* is the unique (caref, serial_number) index refusing a row."""
    from sqlalchemy.exc import IntegrityError
    return isinstance(exc, IntegrityError) and any(m in str(exc.orig) for m in _COLLISION_MARKERS)


def rollback_unless_serial_collision(exc):
    """Roll the session back, except on a serial collision: retry_on_serial_collision
    then rolls back its savepoint only, keeping what the caller flushed before."""
    from models import db
    if not is_serial_collision(exc):
        db.session.rollback()


def retry_on_serial_collision(issue):
    """Sign once more with a fresh random serial when the first one is already
    taken under the CA. Each attempt runs in a savepoint: a collision undoes that
    attempt only, never the caller's transaction; a second collision is raised."""
    import functools
    import logging

    @functools.wraps(issue)
    def issue_with_retry(*args, **kwargs):
        from models import db
        for attempt in (1, 2):
            savepoint = db.session.begin_nested()
            try:
                return issue(*args, **kwargs)
            except Exception as exc:
                if not is_serial_collision(exc):
                    raise
                # A savepoint already released by the attempt's commit has nothing to undo
                if db.session().get_nested_transaction() is savepoint:
                    savepoint.rollback()
                if attempt == 2:
                    raise
                logging.getLogger(__name__).warning(
                    'Random serial already issued by this CA; signing again with a new one')
    return issue_with_retry
