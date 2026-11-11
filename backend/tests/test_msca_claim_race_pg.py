"""An approval whose claim a concurrent poll wins imports nothing, on PostgreSQL.

The poll's conditional update holds the request row; the approval's update waits on
it, then matches no row. That lost claim must not fall back to the inventory import.
"""
import os
import threading
import time
import uuid

import pytest
from sqlalchemy import text

from models import Certificate, MSCARequest, db
from tests.test_msca_lifecycle import _create_msca_cert, _make_key_csr_cert

_PG_URL = os.environ.get('UCM_TEST_PG_URL')


def _wait_for_a_waiter(engine, xid, timeout=10):
    """Until a backend waits on transaction `xid`; the approval's update is then blocked."""
    deadline = time.monotonic() + timeout
    with engine.connect() as probe:
        while time.monotonic() < deadline:
            waiting = probe.execute(text(
                "SELECT count(*) FROM pg_locks WHERE NOT granted "
                "AND locktype = 'transactionid' AND transactionid::text = :xid"), {'xid': xid}).scalar()
            probe.rollback()
            if waiting:
                return True
            time.sleep(0.05)
    return False


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_approval_losing_its_claim_to_a_poll_imports_nothing(app, monkeypatch):
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
    from services.msca.inventory import MicrosoftCAInventoryMixin
    from services.msca_service import MicrosoftCAService
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    _, _, new_pem = _make_key_csr_cert('claim-race.test.local', days=730)
    monkeypatch.setattr(MicrosoftCAAdminChannelMixin, '_run_ps', staticmethod(lambda *a, **k: ''))
    monkeypatch.setattr(MicrosoftCAInventoryMixin, '_fetch_cert_pem',
                        staticmethod(lambda *a, **k: new_pem))

    with _a_schema_of_our_own(f'msca_claim_race_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True) as engine:
        cert_id, msca_id, _ = _create_msca_cert(app, 'claim-race.test.local')
        with app.app_context():
            req = MSCARequest(msca_id=msca_id, csr_id=cert_id, template='WebServer',
                              status='pending', request_id=93)
            db.session.add(req)
            db.session.commit()
            req_id = req.id
            db.session.remove()

        outcome = {}

        def approve():
            with app.app_context():
                outcome['result'] = MicrosoftCAService.approve_request(msca_id, 93)
                db.session.remove()

        with engine.connect() as poll:
            poll.execute(text("UPDATE msca_requests SET status = 'issued', cert_pem = :pem "
                              "WHERE id = :id AND cert_id IS NULL AND status <> 'issued'"),
                         {'pem': new_pem, 'id': req_id})
            xid = poll.execute(text('SELECT pg_current_xact_id()::text')).scalar()
            worker = threading.Thread(target=approve)
            worker.start()
            assert _wait_for_a_waiter(engine, xid)
            poll.commit()
        worker.join(30)

        result = outcome['result']
        assert result['imported_cert_id'] is None
        assert 'import_error' not in result
        with app.app_context():
            assert MSCARequest.query.filter_by(msca_id=msca_id, request_id=93).count() == 1
            rows = Certificate.query.filter_by(subject_cn='claim-race.test.local').all()
            assert [row.id for row in rows] == [cert_id]
            db.session.remove()
