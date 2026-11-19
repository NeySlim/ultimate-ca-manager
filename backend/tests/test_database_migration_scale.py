"""A migration must not grow with the database it is migrating.

The copy used to read each table with ``list(...mappings())``, so a table of
half a million certificates became half a million dictionaries in the worker's
heap before a single row reached the target. On a real installation that is
the difference between a migration and an out-of-memory kill, and nothing in
the suite could tell the two implementations apart.

These tests are measurements rather than assertions about the code: they run
the same copy over two volumes and watch what it costs.
"""
import json
import os
import tempfile
import tracemalloc

import pytest
from sqlalchemy import create_engine, text

from models import db

pytestmark = pytest.mark.sqlite_only(
    reason='the session database is the migration source, SQLite by design; a PostgreSQL source has its own engine (UCM_TEST_PG_URL)')

# Wide enough rows that materialising them is visible, few enough that the
# test stays under a second per run.
_ROW_PAYLOAD = 'x' * 2000
_SMALL = 1500
_LARGE = 6000


@pytest.fixture(autouse=True)
def _a_source_that_satisfies_its_own_schema(app):
    """These tests read the shared database as a database, not as a fixture.

    Other files write rows through the ORM with foreign keys SQLite never
    enforces, so whether this one sees a consistent source depends on which
    files ran before it on this worker. The migration refuses such a source
    on purpose, and that refusal has its own test.
    """
    from tests.conftest import clean_dangling_rows, clean_unreadable_secrets
    from services.database_admin.migration import _check_source_integrity
    from services.database_admin.preflight import PreflightError

    clean_dangling_rows(app)
    clean_unreadable_secrets(app)

    # Having cleaned, say so: a source the migration would refuse makes every
    # test here fail for a reason that has nothing to do with what they
    # measure, and a skip naming the row beats four red tests naming nothing.
    with app.app_context():
        try:
            _check_source_integrity()
        except PreflightError as refused:
            pytest.skip(f'the shared database is not migratable: {refused}')
    yield


@pytest.fixture
def audit_volume(app):
    """Fills and empties the one table that is safe to fill: the audit log.

    It carries no relation, nothing else in the suite counts its rows, and
    it is the table most likely to be large on a real installation.
    """
    def fill(count):
        with app.app_context():
            db.session.execute(text("DELETE FROM audit_logs"))
            db.session.execute(
                text("INSERT INTO audit_logs (action, details, timestamp) "
                     "VALUES (:action, :details, '2026-01-01')"),
                [{'action': f'scale-{index}', 'details': _ROW_PAYLOAD}
                 for index in range(count)])
            db.session.commit()

    yield fill

    with app.app_context():
        db.session.execute(text("DELETE FROM audit_logs"))
        db.session.commit()


def _migrate_and_measure(app, target_path):
    """Run a full migration, returning (stats, peak bytes allocated)."""
    from services.database_admin.migration import migrate_data

    with app.app_context():
        tracemalloc.start()
        try:
            ok, message, stats = migrate_data(f'sqlite:///{target_path}')
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

    assert ok, message
    return stats, peak


class TestMemoryDoesNotFollowTheVolume:
    def test_the_peak_barely_moves_when_the_table_grows(
            self, app, audit_volume, tmp_path):
        """Four times the rows must not mean four times the memory: the copy
        streams, so what it holds is one batch, whatever the table holds."""
        audit_volume(_SMALL)
        small_stats, small_peak = _migrate_and_measure(
            app, tmp_path / 'small.db')

        audit_volume(_LARGE)
        large_stats, large_peak = _migrate_and_measure(
            app, tmp_path / 'large.db')

        assert large_stats['rows_migrated'] - small_stats['rows_migrated'] >= \
            (_LARGE - _SMALL) * 0.9, 'the volumes were not actually different'

        # Room for the copy plan, the inspectors and the verification, which
        # do grow slightly with the number of rows; nothing like the factor
        # of four the table grew by.
        assert large_peak < small_peak * 2, (
            f'memory followed the volume: {small_peak / 1e6:.1f} MB for '
            f'{_SMALL} rows, {large_peak / 1e6:.1f} MB for {_LARGE}')

    def test_the_peak_stays_below_the_data_it_copies(
            self, app, audit_volume, tmp_path):
        """A materialising copy holds the whole table at once, so its peak
        cannot be smaller than the table."""
        audit_volume(_LARGE)
        stats, peak = _migrate_and_measure(app, tmp_path / 'bounded.db')

        copied_bytes = _LARGE * len(_ROW_PAYLOAD)

        assert stats['rows_migrated'] >= _LARGE
        assert peak < copied_bytes, (
            f'{peak / 1e6:.1f} MB held for {copied_bytes / 1e6:.1f} MB of data')


class TestTheInstanceKeepsServingWhileItCopies:
    def test_a_request_is_answered_during_the_copy(
            self, app, auth_client, audit_volume, tmp_path, monkeypatch):
        """The copy reads a snapshot on SQLite, so it never holds a write
        lock on the database the application is still serving from. A copy
        that read the live database instead would block every request for its
        whole duration."""
        from services.database_admin import migration as migration_module

        audit_volume(_SMALL)
        answered = {}
        real_copy = migration_module.copy_tables

        def copy_and_serve(source, target_engine, plan, **kwargs):
            response = auth_client.get('/api/v2/cas')
            answered['status'] = response.status_code
            return real_copy(source, target_engine, plan, **kwargs)

        monkeypatch.setattr(migration_module, 'copy_tables', copy_and_serve)

        with app.app_context():
            ok, message, _stats = migration_module.migrate_data(
                f"sqlite:///{tmp_path / 'served.db'}")

        assert ok, message
        assert answered.get('status') == 200, (
            'the instance stopped answering while the migration ran: '
            f'{answered}')

    def test_the_rows_written_during_the_copy_are_reported(
            self, app, audit_volume, tmp_path, monkeypatch):
        """Serving during the copy means rows can be written during it. They
        are not on the target, and the migration has to say so rather than
        report a clean success."""
        from services.database_admin import migration as migration_module

        audit_volume(_SMALL)
        real_copy = migration_module.copy_tables

        def write_then_copy(source, target_engine, plan, **kwargs):
            db.session.execute(
                text("INSERT INTO audit_logs (action, details, timestamp) "
                     "VALUES ('scale-late', 'written during the copy', "
                     "'2026-01-01')"))
            db.session.commit()
            return real_copy(source, target_engine, plan, **kwargs)

        monkeypatch.setattr(migration_module, 'copy_tables', write_then_copy)

        with app.app_context():
            ok, message, stats = migration_module.migrate_data(
                f"sqlite:///{tmp_path / 'drifted.db'}")

        assert ok, message
        assert stats['source_drift'].get('audit_logs') == 1
        assert 'NOT on the target' in message


class TestTheCopyIsBatched:
    def test_a_table_is_read_in_more_than_one_round_trip(
            self, app, audit_volume, tmp_path, monkeypatch):
        """The batch size is what makes the memory bounded; a change that
        quietly raised it to the size of the table would pass the
        measurements above on a small enough test database."""
        from services.database_admin import copy as copy_module

        audit_volume(_LARGE)
        assert copy_module.BATCH_SIZE < _LARGE, (
            'the batch is larger than the volume: nothing below measures '
            'streaming')

        fetch_counts = {'audit_logs': 0}
        real_copy_one = copy_module._copy_one

        def counting_copy_one(source, dst, entry, **kwargs):
            if entry.name == 'audit_logs':
                fetch_counts['audit_logs'] += 1
            return real_copy_one(source, dst, entry, **kwargs)

        monkeypatch.setattr(copy_module, '_copy_one', counting_copy_one)

        with app.app_context():
            from services.database_admin.migration import migrate_data
            ok, message, stats = migrate_data(
                f"sqlite:///{tmp_path / 'batched.db'}")

        assert ok, message
        # One call per table, and the rows inside it arrive in batches: the
        # count that matters is on the target, and it is complete.
        assert fetch_counts['audit_logs'] == 1
        assert stats['tables']['audit_logs'] >= _LARGE

        engine = create_engine(f"sqlite:///{tmp_path / 'batched.db'}")
        try:
            with engine.connect() as conn:
                assert conn.execute(
                    text('SELECT COUNT(*) FROM audit_logs')).scalar() >= _LARGE
        finally:
            engine.dispose()
