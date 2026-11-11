"""What retention keeps, beyond the calendar.

Age alone was the only criterion, which fails in both directions: a fortnight
of failed backups with a seven-day retention leaves nothing to restore from,
and daily backups of a growing instance fill the filesystem without ever
tripping a date.
"""
import os
import struct
import time

import pytest

from models import SystemConfig, db


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


def _archive(tmp_path, name, payload, age_days, *, record=True):
    """Write an archive the way the service does, optionally recording it."""
    from services.backup import storage
    path = storage.write_archive_atomically(tmp_path, name, payload)
    if record:
        storage.validate_and_record(path, payload)
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


def _body(marker: bytes, size: int = 600) -> bytes:
    import base64
    import json
    metadata = json.dumps({
        'format_version': 3, 'kdf': {'type': 'argon2id', 'time_cost': 3,
                                     'memory_cost': 65536, 'parallelism': 4,
                                     'hash_len': 32},
        'salt_b64': base64.b64encode(b'S' * 16).decode(),
        'nonce_b64': base64.b64encode(b'N' * 12).decode(),
    }, separators=(',', ':')).encode()
    return (b'UCMB' + bytes([3, 1, 2, 0]) + struct.pack('>H', len(metadata))
            + metadata + marker * size)


class TestAMinimumNumberSurvives:
    def test_old_archives_are_kept_up_to_the_minimum(self, app, tmp_path,
                                                     monkeypatch):
        """Every archive is past the retention age, and the instance still has
        something to restore from."""
        from config.settings import Config
        from services.backup import schedule
        with app.app_context():
            monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
            _set('backup_retention_days', '7')
            _set('backup_min_keep', '3')
            _set('backup_max_total_mb', '0')

            archives = [
                _archive(tmp_path, f'ucm_backup_2000010{index}_000000.ucmbkp',
                         _body(bytes([65 + index])), 100 - index)
                for index in range(5)
            ]

            schedule.run_backup_retention()

            surviving = sorted(p.name for p in tmp_path.glob('ucm_backup_*.ucmbkp'))
            assert len(surviving) == 3, surviving
            # The three newest, not any three
            assert surviving == sorted(p.name for p in archives[-3:])

    def test_the_minimum_does_not_protect_a_tampered_archive(self, app, tmp_path,
                                                             monkeypatch):
        from config.settings import Config
        from services.backup import schedule
        with app.app_context():
            monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
            _set('backup_retention_days', '7')
            _set('backup_min_keep', '1')
            _set('backup_max_total_mb', '0')

            good = _archive(tmp_path, 'ucm_backup_20000101_000000.ucmbkp',
                            _body(b'A'), 30)
            newer = _archive(tmp_path, 'ucm_backup_20260101_000000.ucmbkp',
                             _body(b'B'), 20)
            payload = bytearray(newer.read_bytes())
            payload[-1] ^= 0xFF
            newer.write_bytes(bytes(payload))
            stamp = time.time() - 20 * 86400
            os.utime(newer, (stamp, stamp))

            schedule.run_backup_retention()

            assert good.exists(), 'the provable restore point was removed'
            assert not newer.exists(), 'a tampered archive was protected'


class TestTheArchivesStayWithinTheirCeiling:
    def test_the_oldest_go_until_the_total_fits(self, app, tmp_path, monkeypatch):
        from config.settings import Config
        from services.backup import schedule
        with app.app_context():
            monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
            # Nothing is old enough to be pruned by age
            _set('backup_retention_days', '3650')
            _set('backup_min_keep', '1')
            _set('backup_max_total_mb', '1')

            big = 400 * 1024
            for index in range(5):
                _archive(tmp_path, f'ucm_backup_2026010{index}_000000.ucmbkp',
                         _body(bytes([65 + index]), big), 10 - index)

            removed = schedule.run_backup_retention()

            surviving = list(tmp_path.glob('ucm_backup_*.ucmbkp'))
            total = sum(p.stat().st_size for p in surviving)
            assert removed >= 1
            assert total <= 1024 * 1024, f'{total} bytes left above the ceiling'
            assert surviving, 'the ceiling emptied the directory'

    def test_the_ceiling_never_removes_the_last_restore_point(self, app, tmp_path,
                                                              monkeypatch):
        from config.settings import Config
        from services.backup import schedule
        with app.app_context():
            monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
            _set('backup_retention_days', '3650')
            _set('backup_min_keep', '1')
            _set('backup_max_total_mb', '1')   # smaller than the single archive

            only = _archive(tmp_path, 'ucm_backup_20260101_000000.ucmbkp',
                            _body(b'A', 2 * 1024 * 1024), 1)

            schedule.run_backup_retention()

            assert only.exists(), \
                'the size ceiling removed the only archive there was'


class TestTheScheduleReportsWhatHappened:
    def test_the_status_carries_the_last_outcome_and_the_archive_age(
            self, app, tmp_path, monkeypatch):
        from config.settings import Config
        from services.backup import schedule
        with app.app_context():
            monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
            _archive(tmp_path, 'ucm_backup_20260101_000000.ucmbkp', _body(b'A'), 2)
            schedule._record_outcome('ok', 'ucm_backup_20260101_000000.ucmbkp')

            status = schedule.get_schedule()

            assert status['last_outcome'] == 'ok'
            assert status['last_outcome_reason'].startswith('ucm_backup_')
            assert status['last_archive'] == 'ucm_backup_20260101_000000.ucmbkp'
            assert status['last_archive_age_seconds'] >= 2 * 86400 - 60
            assert status['cadence'] == 'rolling_interval'

    def test_a_failed_run_is_visible_in_the_status(self, app, monkeypatch):
        from services.backup import schedule
        with app.app_context():
            _set('auto_backup_enabled', 'true')
            _set('backup_frequency', 'daily')
            SystemConfig.query.filter_by(key='backup_password').delete()
            SystemConfig.query.filter_by(key='backup.last_run').delete()
            db.session.commit()
            try:
                with pytest.raises(Exception):
                    schedule.run_scheduled_backup()
                status = schedule.get_schedule()
                assert status['last_outcome'] == 'failed'
                assert 'password' in (status['last_outcome_reason'] or '')
            finally:
                _set('auto_backup_enabled', 'false')
