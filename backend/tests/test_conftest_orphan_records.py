"""A certificate row deleted behind the service does not hand its revocation records to
the next certificate that takes its id: the suite detaches them after each file."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from models import db
from tests import conftest


def test_orphan_revocation_records_are_detached(app, create_ca, drop_new_cas_and_certificates):
    from models import CA
    from models.revoked_serial import RevokedSerial
    with app.app_context():
        ca = db.session.get(CA, create_ca(cn='Orphan Records CA')['id'])
        gone = (db.session.execute(text('SELECT COALESCE(MAX(id), 0) FROM certificates')).scalar() or 0) + 1000
        serial = f'{gone:x}'
        now = datetime.utcnow()
        row = RevokedSerial(caref=ca.refid, serial_number=serial, certificate_id=gone,
                            revoked_at=now, valid_to=now + timedelta(days=1))
        db.session.add(row)
        db.session.commit()
        row_id = row.id
        try:
            assert conftest._leak_counts()[conftest._ORPHAN_RECORDS] >= 1
            conftest._detach_orphan_records()
            assert conftest._leak_counts()[conftest._ORPHAN_RECORDS] == 0
            db.session.expire_all()  # the helper wrote through its own session
            assert db.session.get(RevokedSerial, row_id).certificate_id is None
        finally:
            db.session.delete(db.session.get(RevokedSerial, row_id))
            db.session.commit()


def test_a_refused_detach_leaves_the_session_usable(app, monkeypatch):
    """A write refused once (a table locked by a reader thread) is a warning, and the next
    file still reads the shared tables."""
    with app.app_context():
        def refuse():
            db.session.execute(text('SELECT * FROM no_such_table_for_this_test'))
        monkeypatch.setattr(db.session, 'commit', refuse)
        with pytest.warns(UserWarning, match='orphan revocation records not detached: OperationalError'):
            conftest._detach_orphan_records()
        monkeypatch.undo()
    assert conftest._leak_counts() is not None
