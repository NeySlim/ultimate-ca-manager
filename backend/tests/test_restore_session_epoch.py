"""The session epoch only moves forward, once per advance, from any number of workers at
once, even when the first restore of an installation creates the row on several together;
no archive carries it, and a restore never moves it back."""
import os
import threading
import uuid

import pytest
from sqlalchemy import event

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


def test_no_archive_carries_the_epoch_nor_moves_it_back(app):
    from services.backup_service import BackupService
    with app.app_context():
        first = advance_epoch()
        assert EPOCH_KEY not in BackupService()._export_configuration(True)['settings']
        # An archive that names the key, from this installation or another, is not obeyed
        archive = {'configuration': {'settings': {EPOCH_KEY: '0'}, 'encrypted_keys': [EPOCH_KEY]}}
        BackupService()._restore_settings(archive, {})
        db.session.commit()
        assert current_epoch() == first
        assert advance_epoch() == first + 1


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


def _check_race(app, url):
    errors, results = _race(app, url)
    with app.app_context():
        stored = current_epoch()
        db.session.remove()
    assert errors == []
    assert sorted(results) == list(range(1, WORKERS + 1))
    assert stored == WORKERS


def test_workers_advancing_the_absent_epoch_together_each_count_once_sqlite(app, tmp_path):
    from tests.test_backup_cross_installation import _bound_to
    url = f'sqlite:///{tmp_path / "epoch.db"}'
    with _bound_to(app, url):
        _check_race(app, url)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_workers_advancing_the_absent_epoch_together_each_count_once_pg(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    schema = f'epoch_race_{uuid.uuid4().hex[:6]}'
    with _a_schema_of_our_own(schema) as url, _bound_to(app, url, is_postgresql=True):
        _check_race(app, url)
