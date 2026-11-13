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

    def test_a_lift_after_the_reread_still_wins(self, app, issuer, monkeypatch):
        """SQLite takes its write lock at the mark: the mark itself checks the record."""
        from services.cert.issued_lookup import apply_persisted_revocation
        if _on_postgresql(app):
            pytest.skip("PostgreSQL: the re-read's share lock makes such a lift wait")
        _, row_id, record_id = _recorded_hold(app, issuer, 'import-lift-reread.example.test')
        _lift_after(monkeypatch, '_record_still_held', row_id, record_id)
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
