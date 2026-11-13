"""PostgreSQL: an import marking a stored row from its record and a revocation of that row take
the row and the record in an order where neither waits on what the other holds."""
import threading

import pytest

from models import Certificate, db
from tests.test_import_issuer_signature import _leaf, _store
from tests.test_revocation_record_rule import (  # noqa: F401  (issuer is a fixture)
    _on_postgresql, _record, _row, _wait_for_a_lock_waiter, issuer)

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def test_an_import_mark_during_a_revocation_does_not_deadlock(app, issuer):
    """An import has written the stored row (its lock held) when it marks it from the record, while
    a revocation holds that record and waits on the row: the mark must not wait on the record."""
    from services.cert.issued_lookup import apply_persisted_revocation
    from services.cert.mixins.lifecycle import LifecycleMixin
    if not _on_postgresql(app):
        pytest.skip('row locks are PostgreSQL behaviour; SQLite serializes writers')
    _, refid, ca_cert, ca_key = issuer
    real, key = _leaf('order-import.example.test', ca_cert, ca_key, days=200)
    row_id = _store(app, real, refid, key=key)
    _record(app, refid, real, reason='certificateHold', certificate_id=row_id)
    outcome = {}
    with app.app_context():
        engine = db.engine

    def revocation():
        with app.app_context():
            try:
                LifecycleMixin.revoke_certificate(row_id, reason='keyCompromise')
                db.session.commit()
                outcome['revoke'] = 'ok'
            except Exception as e:  # noqa: BLE001  (the deadlock victim, if any)
                db.session.rollback()
                outcome['revoke'] = repr(e)
            finally:
                db.session.remove()

    with app.app_context():
        row = db.session.get(Certificate, row_id)
        row.descr = 'imported again'
        db.session.flush()
        worker = threading.Thread(target=revocation)
        worker.start()
        with engine.connect() as conn:
            assert _wait_for_a_lock_waiter(conn, 10)
        try:
            outcome['mark'] = apply_persisted_revocation(row)
            db.session.commit()
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            outcome['mark'] = repr(e)
        worker.join(30)
    assert outcome == {'mark': True, 'revoke': 'ok'}, outcome
    assert _row(app, row_id)[:2] == (True, 'keyCompromise')
