"""Module-scoped cleanup for files that create SSH CAs and certificates: rows that were not
there when the module started are deleted after it, whether its tests passed or failed."""
import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True, scope='module')
def ssh_rows_stay_in_their_module():
    from tests.conftest import _SESSION_APP
    from models import db

    def ids(table):
        return {r[0] for r in db.session.execute(text(f'SELECT id FROM {table}')).all()}

    app = _SESSION_APP[0] if _SESSION_APP else None
    if app is None:
        yield
        return
    with app.app_context():
        cas, certs = ids('ssh_cas'), ids('ssh_certificates')
        db.session.rollback()
    yield
    with app.app_context():
        try:
            for table, kept in (('ssh_certificates', certs), ('ssh_cas', cas)):
                for row_id in ids(table) - kept:
                    db.session.execute(text(f'DELETE FROM {table} WHERE id = :i'), {'i': row_id})
            # Rows hanging from a deleted CA (SQLite does not cascade without its foreign keys)
            db.session.execute(text('DELETE FROM ssh_krls WHERE ssh_ca_id NOT IN (SELECT id FROM ssh_cas)'))
            db.session.commit()
        finally:
            db.session.remove()
