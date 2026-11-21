"""The session epoch advances once per call, from any number of nodes at once, even on
an installation whose first restore creates the row on several nodes together."""
import os
import threading
import uuid

import pytest
from sqlalchemy import event, text

from auth.session_epoch import EPOCH_KEY, advance_epoch, current_epoch
from models import SystemConfig, db

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
WORKERS = 6


def test_the_first_advance_creates_the_row_and_the_next_one_counts(app):
    with app.app_context():
        SystemConfig.query.filter_by(key=EPOCH_KEY).delete()
        db.session.commit()
        assert current_epoch() == 0
        assert advance_epoch() == 1
        assert advance_epoch() == 2
        assert SystemConfig.query.filter_by(key=EPOCH_KEY).count() == 1


def test_an_advance_returns_the_epoch_it_stored_not_a_later_one(app):
    """Another node advancing right after this commit does not change what this call returns."""
    with app.app_context():
        before = advance_epoch()
        session = db.session()

        def another_node_advances(_session):
            with db.engine.connect() as conn:
                conn.execute(text("UPDATE system_config SET value = '9999' WHERE key = :key"),
                             {'key': EPOCH_KEY})
                conn.commit()

        event.listen(session, 'after_commit', another_node_advances, once=True)
        try:
            assert advance_epoch() == before + 1
        finally:
            db.session.remove()
            SystemConfig.query.filter_by(key=EPOCH_KEY).update({'value': str(before + 1)})
            db.session.commit()


def _race(app, url):
    """Every worker reaches its INSERT before any of them commits it."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    errors, results, at_insert = [], [], threading.Barrier(WORKERS)

    def hold_inserts(conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith('INSERT INTO SYSTEM_CONFIG'):
            try:
                at_insert.wait(5)
            except threading.BrokenBarrierError:
                pass

    def worker():
        engine = create_engine(url, pool_size=1, max_overflow=0)
        event.listen(engine, 'before_cursor_execute', hold_inserts)
        try:
            with app.app_context():
                db.session.registry.set(Session(bind=engine))
                results.append(advance_epoch())
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))
        finally:
            engine.dispose()

    threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return errors, results


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_nodes_advancing_the_absent_epoch_together_each_count_once(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    schema = f'epoch_race_{uuid.uuid4().hex[:6]}'
    with _a_schema_of_our_own(schema) as url, _bound_to(app, url, is_postgresql=True):
        errors, results = _race(app, url)
        with app.app_context():
            stored = current_epoch()
            db.session.remove()
    assert errors == []
    assert sorted(results) == list(range(1, WORKERS + 1))
    assert stored == WORKERS
