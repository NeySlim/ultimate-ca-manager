"""PostgreSQL: an import marking a stored row from its record and a revocation of that row take
the row and the record in an order where neither waits on what the other holds."""
import secrets
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


def test_an_unhold_and_a_revocation_lock_the_spellings_of_a_serial_in_one_order(app, issuer):
    """Three records of one serial (decimal, hex, HEX) stored in reverse id order: the unhold's
    lock and the revocation's both take them by id, so they wait on each other without a cycle."""
    from sqlalchemy import select, update
    from models import CA, RevokedSerial
    from services.cert.issued_lookup import lock_serial_records
    from services.cert.mixins.lifecycle import _lock_own_record
    if not _on_postgresql(app):
        pytest.skip('row locks are PostgreSQL behaviour; SQLite serializes writers')
    ca_id, refid, ca_cert, ca_key = issuer
    serial = 0xabc << 100 | secrets.randbits(100)  # its hex holds letters: three spellings
    real, key = _leaf('order-spellings.example.test', ca_cert, ca_key, days=200, serial=serial)
    row_id = _store(app, real, refid, key=key)
    ids = [_record(app, refid, real, reason='certificateHold', column=column)
           for column in (str(serial), format(serial, 'x'), format(serial, 'X'))]
    with app.app_context():
        engine = db.engine
    with engine.begin() as conn:
        # An indexed column changed (no HOT update): the middle, then the first, move to the end
        for record_id in (ids[1], ids[0]):
            conn.execute(update(RevokedSerial).where(RevokedSerial.id == record_id)
                         .values(certificate_id=row_id))
    with app.app_context():
        planned = [r.id for r in RevokedSerial.query.filter(RevokedSerial.id.in_(ids))]
    assert planned == ids[::-1], planned
    outcome = {}

    def locking(name, lock):
        with app.app_context():
            try:
                lock()
                db.session.commit()
                outcome[name] = 'ok'
            except Exception as e:  # noqa: BLE001  (the deadlock victim, if any)
                db.session.rollback()
                outcome[name] = repr(e)
            finally:
                db.session.remove()
    revocation = threading.Thread(target=locking, args=('revoke', lambda: _lock_own_record(
        db.session.get(Certificate, row_id))))
    unhold = threading.Thread(target=locking, args=('unhold', lambda: lock_serial_records(
        db.session.get(CA, ca_id), serial)))
    with engine.connect() as holder, engine.connect() as watcher:
        with holder.begin():
            holder.execute(select(RevokedSerial.id).where(RevokedSerial.id == ids[1]).with_for_update())
            revocation.start()
            assert _wait_for_a_lock_waiter(watcher, 10)
            unhold.start()
            assert _wait_for_a_lock_waiter(watcher, 10, at_least=2)
        revocation.join(30)
        unhold.join(30)
    assert outcome == {'revoke': 'ok', 'unhold': 'ok'}, outcome
