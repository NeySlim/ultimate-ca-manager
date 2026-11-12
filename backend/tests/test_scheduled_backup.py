"""Tests for scheduled backups (previously a stub: schedule PATCH was a no-op,
history was hardcoded, no scheduler task). Source of truth = the General
settings the UI writes (auto_backup_enabled / backup_frequency /
backup_retention_days / backup_password)."""
import json
from datetime import timedelta
import pytest

from models import db, SystemConfig
from utils.datetime_utils import utc_now, utc_isoformat


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


class TestScheduleReadsGeneralSettings:
    def test_get_schedule_reflects_general_keys(self, app):
        with app.app_context():
            from services.backup.schedule import get_schedule
            _set('auto_backup_enabled', 'true')
            _set('backup_frequency', 'weekly')
            _set('backup_retention_days', '14')
            sched = get_schedule()
            assert sched['enabled'] is True
            assert sched['frequency'] == 'weekly'
            assert sched['retention_days'] == 14

    def test_disabled_when_flag_false(self, app):
        with app.app_context():
            from services.backup.schedule import get_schedule
            _set('auto_backup_enabled', 'false')
            assert get_schedule()['enabled'] is False


class TestDueLogic:
    def test_due_when_never_run(self, app):
        with app.app_context():
            from services.backup.schedule import _is_due
            assert _is_due({'frequency': 'daily', 'last_run': None}, utc_now()) is True

    def test_not_due_within_period(self, app):
        with app.app_context():
            from services.backup.schedule import _is_due
            recent = utc_isoformat(utc_now() - timedelta(hours=1))
            assert _is_due({'frequency': 'daily', 'last_run': recent}, utc_now()) is False

    def test_due_after_period(self, app):
        with app.app_context():
            from services.backup.schedule import _is_due
            old = utc_isoformat(utc_now() - timedelta(days=2))
            assert _is_due({'frequency': 'daily', 'last_run': old}, utc_now()) is True

    def test_weekly_not_due_after_two_days(self, app):
        with app.app_context():
            from services.backup.schedule import _is_due
            two_days = utc_isoformat(utc_now() - timedelta(days=2))
            assert _is_due({'frequency': 'weekly', 'last_run': two_days}, utc_now()) is False

    def test_an_upgraded_install_without_a_conclusion_marker_counts_as_concluded(self, app):
        """last_run written before the marker existed: no early archive past the lease."""
        with app.app_context():
            from services.backup.schedule import _is_due
            three_hours = utc_isoformat(utc_now() - timedelta(hours=3))
            assert _is_due({'frequency': 'daily', 'last_run': three_hours,
                            'concluded_run': None}, utc_now()) is False

    def test_a_reservation_never_concluded_is_due_once_its_lease_is_over(self, app):
        with app.app_context():
            from services.backup.schedule import _is_due
            three_hours = utc_isoformat(utc_now() - timedelta(hours=3))
            one_hour = utc_isoformat(utc_now() - timedelta(hours=1))
            older = utc_isoformat(utc_now() - timedelta(days=1))
            assert _is_due({'frequency': 'daily', 'last_run': three_hours,
                            'concluded_run': older}, utc_now()) is True
            assert _is_due({'frequency': 'daily', 'last_run': one_hour,
                            'concluded_run': older}, utc_now()) is False
            assert _is_due({'frequency': 'daily', 'last_run': three_hours,
                            'concluded_run': three_hours}, utc_now()) is False


class TestConclusionMarker:
    def test_an_existing_marker_is_not_inserted_again(self, app):
        """The INSERT of a compare-and-set fails on the unique key: a PostgreSQL log ERROR."""
        from sqlalchemy import event
        from services.backup.schedule import _CONCLUDED_KEY, _start_marking_conclusions
        with app.app_context():
            saved = SystemConfig.query.filter_by(key=_CONCLUDED_KEY).first()
            saved = saved.value if saved else None
            _set(_CONCLUDED_KEY, 'an earlier run')
            statements = []

            def record(conn, cursor, statement, *args):
                statements.append(statement)
            engine = db.engine
            event.listen(engine, 'before_cursor_execute', record)
            try:
                _start_marking_conclusions('an earlier run')
            finally:
                event.remove(engine, 'before_cursor_execute', record)
            try:
                assert not [s for s in statements if s.lstrip().upper().startswith('INSERT')]
                assert SystemConfig.query.filter_by(key=_CONCLUDED_KEY).one().value == 'an earlier run'
            finally:
                if saved is None:
                    SystemConfig.query.filter_by(key=_CONCLUDED_KEY).delete()
                    db.session.commit()
                else:
                    _set(_CONCLUDED_KEY, saved)

    def test_a_missing_marker_is_created(self, app):
        from services.backup.schedule import _CONCLUDED_KEY, _start_marking_conclusions
        with app.app_context():
            saved = SystemConfig.query.filter_by(key=_CONCLUDED_KEY).first()
            saved = saved.value if saved else None
            SystemConfig.query.filter_by(key=_CONCLUDED_KEY).delete()
            db.session.commit()
            try:
                _start_marking_conclusions('prev')
                assert SystemConfig.query.filter_by(key=_CONCLUDED_KEY).one().value == 'prev'
            finally:
                SystemConfig.query.filter_by(key=_CONCLUDED_KEY).delete()
                db.session.commit()
                if saved is not None:
                    _set(_CONCLUDED_KEY, saved)


class TestScheduledTaskGating:
    def test_disabled_is_noop(self, app, monkeypatch):
        with app.app_context():
            from services.backup import schedule
            _set('auto_backup_enabled', 'false')
            called = []
            monkeypatch.setattr('services.backup_service.BackupService.iter_backup',
                                lambda self, pw, **k: called.append(1) or b'x')
            schedule.run_scheduled_backup()
            assert called == []

    def test_enabled_but_no_password_fails_the_task(self, app, monkeypatch):
        """Automatic backups on with no password produces nothing: that is a
        failure the scheduler must show, not a silent skip reported green."""
        with app.app_context():
            from services.backup import schedule
            from services.backup.errors import ScheduledBackupError
            _set('auto_backup_enabled', 'true')
            _set('backup_frequency', 'daily')
            SystemConfig.query.filter_by(key='backup_password').delete()
            SystemConfig.query.filter_by(key='backup.last_run').delete()
            db.session.commit()
            called = []
            monkeypatch.setattr('services.backup_service.BackupService.iter_backup',
                                lambda self, pw, **k: called.append(1) or b'x')
            with pytest.raises(ScheduledBackupError):
                schedule.run_scheduled_backup()
            assert called == []

    def test_disabled_run_reports_why_it_stood_down(self, app):
        with app.app_context():
            from services.backup import schedule
            _set('auto_backup_enabled', 'false')
            assert schedule.run_scheduled_backup() == {
                'status': 'skipped', 'reason': 'disabled'}


class TestScheduleEndpoints:
    def test_patch_persists_to_general_and_get_reflects(self, auth_client):
        r = auth_client.patch('/api/v2/settings/backup/schedule',
                              data=json.dumps({'enabled': True, 'frequency': 'monthly',
                                               'retention_days': 7}),
                              content_type='application/json')
        assert r.status_code == 200
        data = json.loads(r.data)['data']
        assert data['enabled'] is True and data['frequency'] == 'monthly'
        assert data['retention_days'] == 7
        # cleanup
        auth_client.patch('/api/v2/settings/backup/schedule',
                          data=json.dumps({'enabled': False}),
                          content_type='application/json')

    def test_history_not_hardcoded_fake(self, auth_client):
        r = auth_client.get('/api/v2/settings/backup/history')
        assert r.status_code == 200
        items = json.loads(r.data)['data']
        assert not any(b.get('filename', '').endswith('.tar.gz') for b in items)


class TestDecoupledRetention:
    """Retention runs as its own daily task, independent of auto-backup."""

    def _mk(self, d, name, age_days):
        import os, time
        p = d / name
        p.write_bytes(b'x')
        ts = time.time() - age_days * 86400
        os.utime(p, (ts, ts))
        return p

    def test_run_backup_retention_prunes_old_regardless_of_auto(self, app, tmp_path, monkeypatch):
        with app.app_context():
            from services.backup import schedule
            from config.settings import Config
            monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
            # auto-backup OFF on purpose
            _set('auto_backup_enabled', 'false')
            _set('backup_retention_days', '7')
            # None of these carry a validation record, so the two most recent
            # are kept whatever their age and only the third one goes.
            oldest = self._mk(tmp_path, 'ucm_backup_19990101_000000.ucmbkp', 60)
            old = self._mk(tmp_path, 'ucm_backup_20000101_000000.ucmbkp', 30)
            new = self._mk(tmp_path, 'ucm_backup_20990101_000000.ucmbkp', 1)

            removed = schedule.run_backup_retention()

            assert removed == 1
            assert not oldest.exists()
            assert old.exists() and new.exists()

    def test_run_backup_retention_zero_keeps_all(self, app, tmp_path, monkeypatch):
        with app.app_context():
            from services.backup import schedule
            from config.settings import Config
            monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
            _set('backup_retention_days', '0')
            old = self._mk(tmp_path, 'ucm_backup_20000101_000000.ucmbkp', 999)
            assert schedule.run_backup_retention() == 0
            assert old.exists()


class TestDbMigrationSnapshotCap:
    """Pre-migration DB snapshots are capped to the N most recent."""

    def test_prune_keeps_n_most_recent(self, tmp_path, monkeypatch):
        import os, time
        from services.database_admin import helpers
        monkeypatch.setattr(helpers, 'BACKUP_DIR', tmp_path)
        for i in range(8):
            p = tmp_path / f'ucm-sqlite-2026010{i}_000000.db'
            p.write_bytes(b'x')
            ts = time.time() - (8 - i) * 86400  # i=7 newest
            os.utime(p, (ts, ts))
        # a non-snapshot file must be left untouched
        (tmp_path / 'keep.txt').write_bytes(b'x')

        removed = helpers._prune_db_migration_snapshots(keep=3)

        survivors = sorted(p.name for p in tmp_path.glob('ucm-*.db'))
        assert removed == 5
        assert survivors == [
            'ucm-sqlite-20260105_000000.db',
            'ucm-sqlite-20260106_000000.db',
            'ucm-sqlite-20260107_000000.db',
        ]
        assert (tmp_path / 'keep.txt').exists()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
