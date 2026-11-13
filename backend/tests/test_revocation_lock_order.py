"""PostgreSQL: the unhold of a pair and the hourly pass take the records of their serials in one
order (by id), all before any certificate row, so neither waits on what the other holds."""
import threading

import pytest

from models import Certificate, RevokedSerial, db
from tests.test_import_issuer_signature import _leaf, _store
from tests.test_revocation_record_rule import (  # noqa: F401  (issuer is a fixture)
    _on_postgresql, _record, _row, _wait_for_a_lock_waiter, issuer)

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _recorded_pair(app, issuer, cn):
    """Two related rows, each held by its record alone (rows the pass would mark): ``(row id,
    record id)`` per row, the first row stored first and its record last."""
    _, refid, ca_cert, ca_key = issuer
    made = []
    for n in ('first', 'second'):
        real, key = _leaf(f'{cn}-{n}.example.test', ca_cert, ca_key, days=200)
        made.append((_store(app, real, refid, key=key), real))
    records = {row_id: _record(app, refid, real, reason='certificateHold', certificate_id=row_id)
               for row_id, real in reversed(made)}
    with app.app_context():
        first, second = (db.session.get(Certificate, i) for i, _ in made)
        first.related_certificate_id, second.related_certificate_id = second.id, first.id
        db.session.commit()
    return [(row_id, records[row_id]) for row_id, _ in made]


def test_an_unhold_of_a_pair_during_the_pass_does_not_deadlock(app, auth_client, issuer, monkeypatch):
    from services.cert import issued_lookup
    if not _on_postgresql(app):
        pytest.skip('row locks are PostgreSQL behaviour; SQLite serializes writers')
    ids = _recorded_pair(app, issuer, 'order-pass')
    rows = {row_id for row_id, _ in ids}
    with app.app_context():
        engine = db.engine
    paused, release, outcome, first = threading.Event(), threading.Event(), {}, []
    mark = issued_lookup._mark_while_recorded

    def pause_after_the_first_mark(row, record):
        done = mark(row, record)
        if threading.current_thread().name == 'pass' and not first:
            first.append(row.id)
            paused.set()
            release.wait(30)
        return done
    monkeypatch.setattr(issued_lookup, '_mark_while_recorded', pause_after_the_first_mark)

    def hourly_pass():
        with app.app_context():
            try:
                outcome['marked'] = len(issued_lookup.apply_persisted_revocations(rows))
                db.session.commit()
            except Exception as e:  # noqa: BLE001  (the deadlock victim, if any)
                db.session.rollback()
                outcome['pass'] = repr(e)
            finally:
                paused.set()
                db.session.remove()

    def release_once_the_unhold_waits():
        with engine.connect() as conn:
            outcome['waited'] = _wait_for_a_lock_waiter(conn, 10)
        release.set()

    worker = threading.Thread(target=hourly_pass, name='pass')
    worker.start()
    assert paused.wait(30)
    releaser = threading.Thread(target=release_once_the_unhold_waits)
    releaser.start()
    # The member the pass has not reached yet, its partner (marked, uncommitted) with it
    other = next(row_id for row_id in rows if row_id not in first)
    r = auth_client.post(f'/api/v2/certificates/{other}/unhold')
    worker.join(30)
    releaser.join(30)
    assert 'pass' not in outcome and outcome.get('waited'), outcome
    assert r.status_code == 200, r.data
    assert outcome['marked'] == 2
    assert [_row(app, row_id) for row_id in sorted(rows)] == [(False, None, None)] * 2
    with app.app_context():
        assert RevokedSerial.query.filter(RevokedSerial.id.in_([i for _, i in ids])).count() == 0


def test_an_unhold_of_a_pair_takes_its_records_by_id(app, auth_client, issuer):
    """Another taker following the id order holds the lower record and then asks for the higher
    one: an unhold that took the higher one first (its own member's) would deadlock with it."""
    from sqlalchemy import select
    if not _on_postgresql(app):
        pytest.skip('row locks are PostgreSQL behaviour; SQLite serializes writers')
    ids = _recorded_pair(app, issuer, 'order-unhold')
    (first, higher), (second, lower) = ids
    assert lower < higher
    with app.app_context():
        engine = db.engine
    locked, outcome = threading.Event(), {}

    def ordered_taker():
        try:
            with engine.connect() as conn:
                with conn.begin():
                    conn.execute(select(RevokedSerial.id).where(RevokedSerial.id == lower)
                                 .with_for_update(read=True))
                    locked.set()
                    outcome['waited'] = _wait_for_a_lock_waiter(conn, 10)
                    conn.execute(select(RevokedSerial.id).where(RevokedSerial.id == higher)
                                 .with_for_update(read=True))
        except Exception as e:  # noqa: BLE001  (the deadlock victim, if any)
            outcome['taker'] = repr(e)
        finally:
            locked.set()
    worker = threading.Thread(target=ordered_taker)
    worker.start()
    assert locked.wait(30)
    # The first row's record has the higher id: in member order it would be locked first
    r = auth_client.post(f'/api/v2/certificates/{first}/unhold')
    worker.join(30)
    assert 'taker' not in outcome and outcome.get('waited'), outcome
    assert r.status_code == 200, r.data
    assert [_row(app, row_id) for row_id in (first, second)] == [(False, None, None)] * 2


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
