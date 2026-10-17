"""Backups: exposure and false-success findings of the 2026-09 review.

Each test here pins one behaviour the previous code got wrong: an archive
announced as successful while incomplete, an operator reading or pruning
archives, a DB password copied into the audit trail.
"""
import errno
import json
import os
import stat
import threading
import time

import pytest

from models import db, SystemConfig


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


@pytest.fixture(scope='module')
def operator_client(app, create_user):
    """A logged-in operator: holds read/write:settings, never admin:system."""
    create_user(username='op_backup_review', role='operator')
    c = app.test_client()
    r = c.post('/api/v2/auth/login',
               data=json.dumps({'username': 'op_backup_review',
                                'password': 'TestPass123!'}),
               content_type='application/json')
    assert r.status_code == 200, r.data
    return c


class TestArchivesAreAdminOnly:
    """An archive holds every key and secret: reading one is not an
    operator right, whatever the encryption password protects."""

    def test_operator_cannot_list_archives(self, operator_client):
        assert operator_client.get('/api/v2/system/backups').status_code == 403
        assert operator_client.get('/api/v2/system/backup/list').status_code == 403

    def test_operator_cannot_download_an_archive(self, operator_client):
        r = operator_client.get('/api/v2/system/backup/ucm_backup_x.ucmbkp/download')
        assert r.status_code == 403
        r = operator_client.get('/api/v2/settings/backup/ucm_backup_x.ucmbkp/download')
        assert r.status_code == 403

    def test_operator_cannot_read_backup_history(self, operator_client):
        assert operator_client.get('/api/v2/settings/backup/history').status_code == 403

    def test_admin_still_can(self, auth_client):
        assert auth_client.get('/api/v2/system/backups').status_code == 200
        assert auth_client.get('/api/v2/settings/backup/history').status_code == 200


class TestScheduleSettingsAreAdminOnly:
    """The dedicated schedule route requires admin:system; the General
    settings path must not be a way around it."""

    def test_operator_cannot_shorten_retention_through_general(
            self, app, auth_client, operator_client):
        with app.app_context():
            _set('backup_retention_days', '30')

        r = operator_client.patch(
            '/api/v2/settings/general',
            data=json.dumps({'backup_retention_days': 1,
                             'auto_backup_enabled': 'false',
                             'backup_frequency': 'daily'}),
            content_type='application/json')
        assert r.status_code == 403, r.data

        with app.app_context():
            row = SystemConfig.query.filter_by(key='backup_retention_days').first()
            assert row.value == '30'


class TestExportFailuresAbortTheBackup:
    def test_a_failing_exporter_names_its_section(self, app, monkeypatch):
        from services.backup.errors import BackupExportError
        with app.app_context():
            svc = _service()
            import services.backup.backup_service as service_module

            def explode(name, index):
                if name == 'users':
                    raise RuntimeError('table is gone')
                return []

            monkeypatch.setattr(service_module, 'export_section', explode)
            with pytest.raises(BackupExportError) as exc:
                svc.create_backup('Correct-Horse-Battery-9')
            assert 'users' in str(exc.value)
            assert 'table is gone' not in str(exc.value)

    def test_an_undecryptable_ca_key_aborts_instead_of_archiving_ciphertext(
            self, app, monkeypatch, create_ca):
        from services.backup.errors import BackupExportError
        create_ca(cn='Undecryptable Key CA')
        with app.app_context():
            import security.encryption as enc

            def boom(_data):
                raise ValueError('Failed to decrypt private key - wrong encryption key')

            monkeypatch.setattr(enc, 'decrypt_private_key', boom)
            with pytest.raises(BackupExportError) as exc:
                _service()._export_cas(True)
            assert 'could not be decrypted' in str(exc.value)

    def test_a_key_that_does_not_decrypt_to_a_pem_aborts(self, app, monkeypatch,
                                                         create_ca):
        from services.backup.errors import BackupExportError
        create_ca(cn='Not A Pem CA')
        with app.app_context():
            import security.encryption as enc
            # What the old fallback archived: the stored ciphertext, which a
            # restore would have re-encoded and stored as if it were the key.
            monkeypatch.setattr(enc, 'decrypt_private_key',
                                lambda data: 'gAAAAABm-not-a-pem')
            with pytest.raises(BackupExportError):
                _service()._export_cas(True)


class TestScheduledBackupPassword:
    def test_a_ciphertext_that_does_not_decrypt_is_not_used_as_the_password(
            self, app):
        from services.backup import schedule
        from services.backup.errors import ScheduledBackupError
        with app.app_context():
            stored = 'gAAAAA' + 'A' * 80  # Fernet-shaped, not our ciphertext
            _set('backup_password', stored)
            try:
                with pytest.raises(ScheduledBackupError):
                    schedule._get_backup_password()
            finally:
                SystemConfig.query.filter_by(key='backup_password').delete()
                db.session.commit()


class TestScheduledRunReportsOutcome:
    def test_a_failed_creation_is_raised_to_the_scheduler(self, app, monkeypatch):
        from services.backup import schedule
        with app.app_context():
            _set('auto_backup_enabled', 'true')
            _set('backup_frequency', 'daily')
            _set('backup_password', 'Correct-Horse-Battery-9')
            SystemConfig.query.filter_by(key='backup.last_run').delete()
            db.session.commit()
            monkeypatch.setattr(
                'services.backup.schedule.BackupService.create_backup',
                lambda self, pw, **k: (_ for _ in ()).throw(RuntimeError('disk full')))
            try:
                with pytest.raises(RuntimeError):
                    schedule.run_scheduled_backup()
                # Nothing was recorded as a run, so the next tick retries
                assert SystemConfig.query.filter_by(key='backup.last_run').first() is None
            finally:
                _set('auto_backup_enabled', 'false')
                SystemConfig.query.filter_by(key='backup_password').delete()
                db.session.commit()

    def test_scheduler_separates_failed_skipped_and_done(self):
        from services.scheduler_service import ScheduledTask, SchedulerService
        sched = SchedulerService()

        done = ScheduledTask('done', lambda: None, 60)
        skipped = ScheduledTask('skipped', lambda: {'status': 'skipped',
                                                    'reason': 'not_due'}, 60)
        failed = ScheduledTask('failed',
                               lambda: (_ for _ in ()).throw(RuntimeError('nope')), 60)
        for task in (done, skipped, failed):
            sched._run_task(task)

        assert done.to_dict()['last_status'] == 'ok'
        assert skipped.to_dict()['last_status'] == 'skipped'
        assert skipped.to_dict()['last_reason'] == 'not_due'
        assert failed.to_dict()['last_status'] == 'failed'
        assert 'nope' in failed.to_dict()['last_error']


class TestRetentionKeepsARestorePoint:
    """Retention protects what can be proven, not what merely looks right."""

    def _validated(self, tmp_path, name, payload, age_days):
        """Write an archive the way the service does, and record it."""
        from services.backup import storage
        path = storage.write_archive_atomically(tmp_path, name, payload)
        storage.validate_and_record(path, payload)
        ts = time.time() - age_days * 86400
        os.utime(path, (ts, ts))
        return path

    def _plain(self, tmp_path, name, payload, age_days):
        """Write an archive with no validation record (an older install)."""
        path = tmp_path / name
        path.write_bytes(payload)
        ts = time.time() - age_days * 86400
        os.utime(path, (ts, ts))
        return path

    def test_a_tampered_archive_does_not_displace_the_last_validated_one(
            self, app, tmp_path, monkeypatch):
        """A file whose bytes changed after it was written is not a restore
        point, however well-formed its header looks."""
        from services.backup import schedule
        from config.settings import Config
        with app.app_context():
            monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
            _set('backup_retention_days', '7')
            # One archive minimum, so what survives here survives because it
            # is provable, not because of the count.
            _set('backup_min_keep', '1')
            good = self._validated(tmp_path, 'ucm_backup_20000101_000000.ucmbkp',
                                   b'UCMB\x02' + b'A' * 600, 30)
            tampered = self._validated(tmp_path, 'ucm_backup_20260101_000000.ucmbkp',
                                       b'UCMB\x02' + b'B' * 600, 20)
            # Same name, same size, same header; one byte of ciphertext differs
            payload = bytearray(tampered.read_bytes())
            payload[-1] ^= 0xFF
            tampered.write_bytes(bytes(payload))
            ts = time.time() - 20 * 86400
            os.utime(tampered, (ts, ts))

            removed = schedule.run_backup_retention()

            assert good.exists(), 'the last provable restore point was pruned'
            assert not tampered.exists()
            assert removed == 1

    def test_the_last_validated_archive_survives_its_retention_age(
            self, app, tmp_path, monkeypatch):
        from services.backup import schedule
        from config.settings import Config
        with app.app_context():
            monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
            _set('backup_retention_days', '7')
            _set('backup_min_keep', '1')
            only = self._validated(tmp_path, 'ucm_backup_20000101_000000.ucmbkp',
                                   b'UCMB\x02' + b'A' * 600, 30)

            assert schedule.run_backup_retention() == 0
            assert only.exists()

    def test_older_archives_go_once_a_newer_validated_one_exists(
            self, app, tmp_path, monkeypatch):
        from services.backup import schedule
        from config.settings import Config
        with app.app_context():
            monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
            _set('backup_retention_days', '7')
            _set('backup_min_keep', '1')
            old = self._validated(tmp_path, 'ucm_backup_20000101_000000.ucmbkp',
                                  b'UCMB\x02' + b'A' * 600, 30)
            older = self._validated(tmp_path, 'ucm_backup_19990101_000000.ucmbkp',
                                    b'UCMB\x02' + b'B' * 600, 60)
            recent = self._validated(tmp_path, 'ucm_backup_20260101_000000.ucmbkp',
                                     b'UCMB\x02' + b'C' * 600, 1)

            assert schedule.run_backup_retention() == 2
            assert recent.exists()
            assert not old.exists() and not older.exists()

    def test_archives_from_before_records_keep_the_two_most_recent(
            self, app, tmp_path, monkeypatch):
        """Nothing proves an unrecorded archive is usable, and nothing proves
        it is not: prudence keeps two."""
        from services.backup import schedule
        from config.settings import Config
        with app.app_context():
            monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
            _set('backup_retention_days', '7')
            oldest = self._plain(tmp_path, 'ucm_backup_19980101_000000.ucmbkp',
                                 b'legacy-archive-bytes', 90)
            middle = self._plain(tmp_path, 'ucm_backup_19990101_000000.ucmbkp',
                                 b'legacy-archive-bytes', 60)
            newest = self._plain(tmp_path, 'ucm_backup_20000101_000000.ucmbkp',
                                 b'legacy-archive-bytes', 30)

            assert schedule.run_backup_retention() == 1
            assert newest.exists() and middle.exists()
            assert not oldest.exists()


class TestPublicationDecidesTheRetryGuard:
    """The guard against writing an archive a minute exists for one case:
    the archive is on disk and its timestamp is not."""

    def _enable(self, tmp_path, monkeypatch):
        from config.settings import Config
        from services.backup import schedule
        monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
        _set('auto_backup_enabled', 'true')
        _set('backup_frequency', 'daily')
        _set('backup_password', 'Correct-Horse-Battery-9')
        SystemConfig.query.filter_by(key='backup.last_run').delete()
        db.session.commit()
        schedule._LAST_ATTEMPT['at'] = None

    def _disable(self):
        from services.backup import schedule
        schedule._LAST_ATTEMPT['at'] = None
        _set('auto_backup_enabled', 'false')
        SystemConfig.query.filter_by(key='backup_password').delete()
        SystemConfig.query.filter_by(key='backup.last_run').delete()
        db.session.commit()

    def test_a_failed_export_is_retried_on_the_next_tick(
            self, app, tmp_path, monkeypatch):
        from services.backup import schedule
        with app.app_context():
            self._enable(tmp_path, monkeypatch)
            try:
                monkeypatch.setattr(
                    'services.backup.schedule.BackupService.create_backup',
                    lambda self, pw, **k: (_ for _ in ()).throw(
                        RuntimeError('transient export failure')))
                with pytest.raises(RuntimeError):
                    schedule.run_scheduled_backup()
                assert not list(tmp_path.glob('ucm_backup_*.ucmbkp'))

                # One minute later the export works: nothing must stand in the way
                monkeypatch.setattr(
                    'services.backup.schedule.BackupService.create_backup',
                    lambda self, pw, **k: b'archive-bytes')
                result = schedule.run_scheduled_backup()
                assert result['status'] == 'ok'
                assert len(list(tmp_path.glob('ucm_backup_*.ucmbkp'))) == 1
            finally:
                self._disable()

    def test_an_archive_that_cannot_be_validated_is_also_retried(
            self, app, tmp_path, monkeypatch):
        """A short write is a failed run, not a restore point."""
        from services.backup import schedule, storage
        from services.backup.errors import BackupValidationError
        with app.app_context():
            self._enable(tmp_path, monkeypatch)
            try:
                monkeypatch.setattr(
                    'services.backup.schedule.BackupService.create_backup',
                    lambda self, pw, **k: b'archive-bytes')
                monkeypatch.setattr(
                    storage, 'digest_of',
                    lambda path: (3, 'deadbeef'))  # as if the file were short
                with pytest.raises(BackupValidationError):
                    schedule.run_scheduled_backup()
                assert schedule._LAST_ATTEMPT['at'] is None, \
                    'a run that produced no provable archive must be retried'
                assert not list(tmp_path.glob('ucm_backup_*.ucmbkp')), \
                    'a failed validation must not leave a listed archive'
            finally:
                self._disable()


class TestValidatedArchivePublication:
    def test_catalog_updates_are_serialized(self, tmp_path, monkeypatch):
        from services.backup import storage
        first = storage.write_archive_atomically(
            tmp_path, 'ucm_backup_a.ucmbkp', b'archive-a')
        second = storage.write_archive_atomically(
            tmp_path, 'ucm_backup_b.ucmbkp', b'archive-b')
        original_write = storage._write_catalog
        first_write_started = threading.Event()
        second_write_started = threading.Event()
        release_first_write = threading.Event()
        write_count = 0
        count_lock = threading.Lock()

        def delayed_write(backup_dir, archives):
            nonlocal write_count
            with count_lock:
                write_count += 1
                call_number = write_count
            if call_number == 1:
                first_write_started.set()
                assert release_first_write.wait(timeout=5)
            else:
                second_write_started.set()
            return original_write(backup_dir, archives)

        monkeypatch.setattr(storage, '_write_catalog', delayed_write)
        errors = []

        def record(path, payload):
            try:
                storage.validate_and_record(path, payload)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=record, args=(first, b'archive-a')),
            threading.Thread(target=record, args=(second, b'archive-b')),
        ]
        threads[0].start()
        assert first_write_started.wait(timeout=5)
        threads[1].start()
        second_write_started.wait(timeout=0.2)
        release_first_write.set()
        for thread in threads:
            thread.join(timeout=5)

        assert all(not thread.is_alive() for thread in threads)
        assert not errors
        assert set(storage.read_catalog(tmp_path)) == {first.name, second.name}

    def test_catalog_failure_removes_the_unvalidated_archive(
            self, tmp_path, monkeypatch):
        from services.backup import storage
        from services.backup.errors import BackupValidationError
        path = storage.write_archive_atomically(
            tmp_path, 'ucm_backup_catalog_failure.ucmbkp', b'archive')
        monkeypatch.setattr(
            storage, '_write_catalog',
            lambda *args: (_ for _ in ()).throw(OSError('disk full')))

        with pytest.raises(BackupValidationError):
            storage.validate_and_record(path, b'archive')

        assert not path.exists()

    def test_archive_and_catalog_directory_entries_are_synced(
            self, tmp_path, monkeypatch):
        from services.backup import storage
        synced = []
        monkeypatch.setattr(
            storage, '_fsync_directory', lambda path: synced.append(path),
            raising=False)

        path = storage.write_archive_atomically(
            tmp_path, 'ucm_backup_synced.ucmbkp', b'archive')
        storage.validate_and_record(path, b'archive')

        assert synced.count(tmp_path) >= 2

    def test_unsupported_directory_fsync_does_not_refuse_backups(
            self, tmp_path, monkeypatch):
        from services.backup import storage
        real_fsync = os.fsync

        def fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(errno.EINVAL, 'directory fsync unsupported')
            return real_fsync(fd)

        monkeypatch.setattr(storage.os, 'fsync', fsync)
        path = storage.publish_validated_archive(
            tmp_path, 'ucm_backup_network_share.ucmbkp', b'archive')

        assert path.read_bytes() == b'archive'
        assert storage.matches_record(
            path, storage.read_catalog(tmp_path)[path.name])

    def test_directory_fsync_io_error_remains_fatal(
            self, tmp_path, monkeypatch):
        from services.backup import storage
        real_fsync = os.fsync

        def fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(errno.EIO, 'directory I/O failure')
            return real_fsync(fd)

        monkeypatch.setattr(storage.os, 'fsync', fsync)
        with pytest.raises(OSError, match='directory I/O failure'):
            storage.publish_validated_archive(
                tmp_path, 'ucm_backup_io_failure.ucmbkp', b'archive')

        assert not list(tmp_path.glob('ucm_backup_*.ucmbkp'))

    def test_legacy_create_route_uses_validated_publication(
            self, auth_client, tmp_path, monkeypatch):
        import api.v2.settings.backup as routes
        from config.settings import Config
        from services.backup import storage
        from services.backup_service import BackupService
        calls = []

        monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
        monkeypatch.setattr(
            BackupService, 'create_backup',
            lambda self, password, **kwargs: b'archive')
        monkeypatch.setattr(routes.AuditService, 'log_action',
                            lambda **kwargs: None)
        monkeypatch.setattr(
            storage, 'publish_validated_archive',
            lambda backup_dir, filename, data: calls.append(
                (backup_dir, filename, data)) or tmp_path / filename,
            raising=False)

        response = auth_client.post(
            '/api/v2/settings/backup/create',
            data=json.dumps({'password': 'Correct-Horse-Battery-9'}),
            content_type='application/json')

        assert response.status_code == 200, response.data
        assert len(calls) == 1
        assert calls[0][0] == tmp_path
        assert calls[0][2] == b'archive'


class TestDatabaseCredentialsStayOutOfTheAudit:
    def test_a_failed_migration_redacts_the_password(self, app, auth_client,
                                                     monkeypatch):
        import api.v2.database as routes
        recorded = []
        monkeypatch.setattr(routes.AuditService, 'log_action',
                            lambda **kw: recorded.append(kw))
        monkeypatch.setattr(
            routes.svc, 'migrate_data',
            lambda url: (False, f'target not empty: {url}',
                         {'tables': 0, 'refusal': 'preflight'}))

        uri = 'postgresql://alice:S3cret-For-Review@db.example:5432/ucm'
        r = auth_client.post('/api/v2/database/migrate',
                             data=json.dumps({'database_url': uri}),
                             content_type='application/json')

        assert r.status_code == 409, r.data
        assert 'S3cret-For-Review' not in r.data.decode()
        assert recorded, 'the failed migration must still be audited'
        blob = json.dumps(recorded, default=str)
        assert 'S3cret-For-Review' not in blob
        assert 'alice' in blob  # user and host stay, only the secret goes

    def test_query_string_passwords_are_redacted_too(self):
        from services.database_admin import _redact_uri
        out = _redact_uri(
            'postgresql://alice@db.example/ucm?password=S3cret&sslmode=require')
        assert 'S3cret' not in out
        assert 'sslmode=require' in out


class TestRedactionCoversEveryPasswordShape:
    """The authority form with no user, and libqp's query spellings."""

    def test_empty_user_and_ssl_password(self):
        from services.database_admin import _redact_uri
        out = _redact_uri('postgresql://:S3cret@db.example/ucm')
        assert 'S3cret' not in out and 'db.example' in out

        out = _redact_uri(
            'postgresql://alice@db.example/ucm?sslpassword=S3cret&sslmode=require')
        assert 'S3cret' not in out
        assert 'sslmode=require' in out

    def test_a_path_setting_is_not_redacted(self):
        from services.database_admin import _redact_uri
        out = _redact_uri('postgresql://alice@db.example/ucm?passfile=/etc/pgpass')
        assert out.endswith('passfile=/etc/pgpass')


class TestFailedTimestampStopsTheLoop:
    """An archive written but never recorded must not be written again a
    minute later, which is what filled the disk."""

    def test_the_run_does_not_come_due_again_on_the_next_tick(
            self, app, tmp_path, monkeypatch):
        from services.backup import schedule
        from config.settings import Config
        with app.app_context():
            monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
            _set('auto_backup_enabled', 'true')
            _set('backup_frequency', 'daily')
            _set('backup_password', 'Correct-Horse-Battery-9')
            SystemConfig.query.filter_by(key='backup.last_run').delete()
            db.session.commit()
            schedule._LAST_ATTEMPT['at'] = None

            monkeypatch.setattr(
                'services.backup.schedule.BackupService.create_backup',
                lambda self, pw, **k: b'archive-bytes')
            monkeypatch.setattr(
                'services.backup.schedule._record_last_run',
                lambda ts: (_ for _ in ()).throw(
                    schedule.ScheduledBackupError('cannot write')))

            try:
                with pytest.raises(schedule.ScheduledBackupError):
                    schedule.run_scheduled_backup()
                written = list(tmp_path.glob('ucm_backup_*.ucmbkp'))
                assert len(written) == 1

                # Next scheduler tick, one minute later
                assert schedule.run_scheduled_backup() == {
                    'status': 'skipped', 'reason': 'not_due'}
                assert len(list(tmp_path.glob('ucm_backup_*.ucmbkp'))) == 1
            finally:
                schedule._LAST_ATTEMPT['at'] = None
                _set('auto_backup_enabled', 'false')
                SystemConfig.query.filter_by(key='backup_password').delete()
                db.session.commit()


class TestSecretsAndFilesCannotBeDroppedSilently:
    def test_an_undecryptable_dns_credential_aborts_the_backup(
            self, app, monkeypatch):
        from services.backup.errors import BackupExportError
        from models.acme_models import DnsProvider
        with app.app_context():
            provider = DnsProvider(name='review-dns', provider_type='cloudflare')
            provider.credentials = '{"api_token": "t0ken"}'
            db.session.add(provider)
            db.session.commit()
            try:
                import utils.encryption as enc
                stored = provider._credentials
                real_decrypt = enc.decrypt_value
                # Only this provider's value stops decrypting: the shared test
                # database holds other providers, and they must still export.
                monkeypatch.setattr(
                    enc, 'decrypt_value',
                    lambda value: None if value == stored else real_decrypt(value))
                from services.backup.export_generic import IdentityIndex, export_section
                with pytest.raises(BackupExportError) as exc:
                    export_section('dns_providers', IdentityIndex())
                assert 'review-dns' in str(exc.value)
            finally:
                db.session.delete(provider)
                db.session.commit()

    def test_an_unreadable_https_key_aborts_the_backup(self, app, monkeypatch,
                                                       tmp_path):
        from pathlib import Path
        from services.backup.errors import BackupExportError
        from config.settings import Config
        cert = tmp_path / 'server.crt'
        key = tmp_path / 'server.key'
        cert.write_text('-----BEGIN CERTIFICATE-----\n')
        key.write_text('-----BEGIN PRIVATE KEY-----\n')

        real_read_text = Path.read_text

        def read_text(self, *args, **kwargs):
            if self == key:
                raise OSError('Permission denied')
            return real_read_text(self, *args, **kwargs)

        with app.app_context():
            monkeypatch.setattr(Config, 'HTTPS_CERT_PATH', cert, raising=False)
            monkeypatch.setattr(Config, 'HTTPS_KEY_PATH', key, raising=False)
            monkeypatch.setattr(Path, 'read_text', read_text)
            with pytest.raises(BackupExportError):
                _service()._export_https_files()


class TestTaskReportedFailureIsNotGreen:
    def test_a_task_returning_failed_is_recorded_as_failed(self):
        from services.scheduler_service import ScheduledTask, SchedulerService
        task = ScheduledTask('reports-failure',
                             lambda: {'status': 'failed', 'reason': 'no password'},
                             60)
        SchedulerService()._run_task(task)

        recorded = task.to_dict()
        assert recorded['last_status'] == 'failed'
        assert 'no password' in (recorded['last_error'] or '')
        assert task.run_count == 0
