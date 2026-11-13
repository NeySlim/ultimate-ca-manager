"""An import marks a row from its CA's record as the hourly pass does: only while the record is
still stored, so an unhold committed meanwhile is never undone (a hold left without a record)."""
import base64
import uuid

import pytest
from sqlalchemy import delete, update

from models import Certificate, RevokedSerial, db
from tests.test_import_issuer_signature import _leaf, _pem, _store
from tests.test_revocation_record_rule import (  # noqa: F401  (issuer is a fixture)
    _on_postgresql, _record, _row, issuer)

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _recorded_hold(app, issuer, cn):
    _, refid, ca_cert, ca_key = issuer
    real, key = _leaf(cn, ca_cert, ca_key, days=200)
    row_id = _store(app, real, refid, key=key)
    return real, row_id, _record(app, refid, real, reason='certificateHold', certificate_id=row_id)


def _lifted(row_id, record_id):
    """An unhold committed on another connection."""
    with db.engine.begin() as other:
        other.execute(delete(RevokedSerial).where(RevokedSerial.id == record_id))
        if row_id is not None:
            other.execute(update(Certificate).where(Certificate.id == row_id).values(
                revoked=False, revoke_reason=None, revoked_at=None))


def _lift_after(monkeypatch, name, row_id, record_id):
    from services.cert import issued_lookup
    original = getattr(issued_lookup, name)

    def then_lifted(*args, **kwargs):
        found = original(*args, **kwargs)
        _lifted(row_id, record_id)
        return found
    monkeypatch.setattr(issued_lookup, name, then_lifted)


class TestALiftBetweenTheImportsReadAndItsMark:

    def test_a_stored_row_is_left_unrevoked(self, app, issuer, monkeypatch):
        from services.cert.issued_lookup import apply_persisted_revocation
        _, row_id, record_id = _recorded_hold(app, issuer, 'import-lift-stored.example.test')
        _lift_after(monkeypatch, 'row_persisted_revocation', row_id, record_id)
        with app.app_context():
            assert apply_persisted_revocation(db.session.get(Certificate, row_id)) is False
            db.session.commit()
        assert _row(app, row_id) == (False, None, None)

    def test_a_new_row_is_not_marked(self, app, issuer, monkeypatch):
        from services.cert.issued_lookup import apply_persisted_revocation
        real, row_id, record_id = _recorded_hold(app, issuer, 'import-lift-new.example.test')
        _lift_after(monkeypatch, 'row_persisted_revocation', None, record_id)
        with app.app_context():
            # The row an import is about to add for the same certificate
            stored = db.session.get(Certificate, row_id)
            row = Certificate(refid=str(uuid.uuid4()), descr='new', caref=stored.caref,
                              crt=base64.b64encode(_pem(real).encode()).decode(),
                              serial_number=stored.serial_number)
            assert apply_persisted_revocation(row) is False
            assert not row.revoked
            db.session.rollback()

    def test_a_lift_just_before_the_mark_still_wins(self, app, issuer, monkeypatch):
        """A stored row takes no lock on the record: the mark statement itself checks it. Only the
        record goes here, the row being locked by then."""
        from services.cert import issued_lookup
        from services.cert.issued_lookup import apply_persisted_revocation
        _, row_id, record_id = _recorded_hold(app, issuer, 'import-lift-reread.example.test')
        mark = issued_lookup._mark_while_recorded

        def lifted_then_marked(row, record):
            _lifted(None, record_id)
            return mark(row, record)
        monkeypatch.setattr(issued_lookup, '_mark_while_recorded', lifted_then_marked)
        with app.app_context():
            assert apply_persisted_revocation(db.session.get(Certificate, row_id)) is False
            db.session.commit()
        assert _row(app, row_id) == (False, None, None)

    def test_without_a_lift_the_row_is_marked(self, app, issuer):
        """Non-regression: the record still stored marks the row."""
        from services.cert.issued_lookup import apply_persisted_revocation
        _, row_id, _ = _recorded_hold(app, issuer, 'import-no-lift.example.test')
        with app.app_context():
            assert apply_persisted_revocation(db.session.get(Certificate, row_id)) is True
            db.session.commit()
        assert _row(app, row_id)[:2] == (True, 'certificateHold')


def test_an_unhold_committed_while_the_mark_waits_on_the_row_wins(app, issuer):
    """PostgreSQL: an unhold holds the row and has deleted the record, uncommitted, when the mark
    waits on the row; once it commits, the mark must see the record gone (no hold left without one)."""
    import threading
    from tests.test_revocation_record_rule import _wait_for_a_lock_waiter
    from services.cert.issued_lookup import apply_persisted_revocation
    if not _on_postgresql(app):
        pytest.skip('row locks are PostgreSQL behaviour; SQLite serializes writers')
    _, row_id, record_id = _recorded_hold(app, issuer, 'import-lift-during-wait.example.test')
    outcome = {}
    with app.app_context():
        engine = db.engine

    def import_mark():
        with app.app_context():
            try:
                outcome['mark'] = apply_persisted_revocation(db.session.get(Certificate, row_id))
                db.session.commit()
            except Exception as e:  # noqa: BLE001
                db.session.rollback()
                outcome['mark'] = repr(e)
            finally:
                db.session.remove()

    with engine.connect() as unhold, engine.connect() as watcher:
        tx = unhold.begin()
        unhold.execute(RevokedSerial.__table__.select().where(
            RevokedSerial.id == record_id).with_for_update())
        unhold.execute(update(Certificate).where(Certificate.id == row_id).values(
            revoked=False, revoke_reason=None, revoked_at=None))
        unhold.execute(delete(RevokedSerial).where(RevokedSerial.id == record_id))
        worker = threading.Thread(target=import_mark)
        worker.start()
        outcome['waited'] = _wait_for_a_lock_waiter(watcher, 10)
        tx.commit()
        worker.join(30)
    assert outcome == {'waited': True, 'mark': False}, outcome
    assert _row(app, row_id) == (False, None, None)
    with app.app_context():
        assert RevokedSerial.query.filter_by(id=record_id).count() == 0
