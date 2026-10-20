"""The /api/v2/system backup routes: listing, deletion, retention, create, restore.

Behaviour only: each test drives a route through the test client against a
backup directory of its own, and checks what the caller and the disk see.
"""
import io
import json
import os
import threading
import time

import pytest

import fips_mode
from config.settings import Config
from services.backup import manifest
from services.backup.locking import backup_operation_lock

PASSWORD = 'Correct-Horse-Battery-9'


def _name(tag):
    return f'ucm_backup_20260101_000000_000000_{tag}.ucmbkp'


@pytest.fixture
def backup_dir(app, tmp_path, monkeypatch):
    directory = tmp_path / 'backups'
    directory.mkdir()
    monkeypatch.setattr(Config, 'BACKUP_DIR', directory, raising=False)
    return directory


@pytest.fixture
def audit_spy(monkeypatch):
    from services.audit_service import AuditService
    calls = []
    monkeypatch.setattr(AuditService, 'log_action',
                        staticmethod(lambda **kw: calls.append(kw)))
    return calls


@pytest.fixture
def short_waits(monkeypatch):
    """Lock waits short enough for a test, still positive."""
    from api.v2.system import backup as route
    monkeypatch.setattr(route, 'DELETE_LOCK_WAIT', 0.3)
    monkeypatch.setattr(route, 'BULK_DELETE_LOCK_WAIT', 0.3)
    monkeypatch.setattr(route, 'RETENTION_LOCK_WAIT', 0.3)


@pytest.fixture
def lock_held_elsewhere(backup_dir, short_waits):
    """Another thread holds the backup lock for the duration of the test."""
    taken, release = threading.Event(), threading.Event()

    def hold():
        with backup_operation_lock(purpose='another operation'):
            taken.set()
            release.wait(timeout=30)

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    assert taken.wait(timeout=10), 'the holder never took the lock'
    try:
        yield
    finally:
        release.set()
        holder.join(timeout=10)
        assert not holder.is_alive()


def _write(directory, name, size=10, mtime=None):
    path = directory / name
    path.write_bytes(b'x' * size)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _list(client, query=''):
    response = client.get('/api/v2/system/backups' + query)
    assert response.status_code == 200, response.data
    return response.get_json()['data']


def _bulk(client, payload):
    return client.post('/api/v2/system/backups/bulk-delete',
                       data=json.dumps(payload), content_type='application/json')


def _message(response):
    body = response.get_json(silent=True) or {}
    return str(body.get('message') or '')


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

class TestListing:
    def test_page_two_by_size(self, auth_client, backup_dir):
        for index in range(25):
            _write(backup_dir, _name(f's{index:02d}'), size=100 + index)

        data = _list(auth_client, '?page=2&per_page=10&sort=size_asc')

        assert [item['size_bytes'] for item in data['items']] == \
            list(range(110, 120))
        assert data['meta']['total'] == 25
        assert data['meta']['pages'] == 3

    def test_per_page_is_capped_at_100(self, auth_client, backup_dir):
        for index in range(105):
            _write(backup_dir, _name(f'c{index:03d}'))

        data = _list(auth_client, '?per_page=500')

        assert len(data['items']) == 100
        assert data['meta']['per_page'] == 100

    def test_unknown_sort_falls_back_to_newest_first(self, auth_client, backup_dir):
        now = time.time()
        for index, tag in enumerate(('old', 'mid', 'new')):
            _write(backup_dir, _name(tag), mtime=now - 3600 * (3 - index))

        data = _list(auth_client, '?sort=inconnu')

        assert [item['filename'] for item in data['items']] == \
            [_name('new'), _name('mid'), _name('old')]

    def test_search_counts_matches_and_everything(self, auth_client, backup_dir):
        for tag in ('janvier_a', 'JANVIER_b', 'x_janvier', 'fevrier', 'mars'):
            _write(backup_dir, _name(tag), size=10)

        meta = _list(auth_client, '?search=janvier')['meta']

        assert meta['total'] == 3
        assert meta['total_all'] == 5
        assert meta['total_size_bytes'] == 30
        assert meta['total_size_all_bytes'] == 50

    def test_an_empty_directory_has_one_page(self, auth_client, backup_dir):
        meta = _list(auth_client)['meta']
        assert meta['total'] == 0 and meta['pages'] == 1

    def test_item_shape(self, auth_client, backup_dir):
        _write(backup_dir, _name('shape'), size=2048, mtime=1767225600)

        item = _list(auth_client)['items'][0]

        assert item == {'filename': _name('shape'), 'size': '2.0 KB',
                        'size_bytes': 2048,
                        'created_at': '2026-01-01 00:00:00 UTC'}

    def test_a_disk_failure_omits_the_disk_fields(self, auth_client, backup_dir,
                                                  monkeypatch):
        import shutil
        _write(backup_dir, _name('disk'))

        def broken(_path):
            raise OSError('no statvfs')
        monkeypatch.setattr(shutil, 'disk_usage', broken)

        meta = _list(auth_client)['meta']

        assert meta['total'] == 1
        assert not [key for key in meta if key.startswith('disk_')]

    def test_disk_fields_are_present_otherwise(self, auth_client, backup_dir):
        meta = _list(auth_client)['meta']
        for key in ('disk_total_bytes', 'disk_free_bytes', 'disk_free',
                    'disk_used_pct'):
            assert key in meta

    def test_a_directory_not_created_yet_measures_its_parent(
            self, auth_client, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path / 'not' / 'yet',
                            raising=False)

        with caplog.at_level('WARNING', logger='api.v2.system.backup'):
            meta = _list(auth_client)['meta']

        assert meta['total'] == 0
        assert meta['disk_total_bytes'] > 0 and 'disk_free' in meta
        assert 'disk usage' not in caplog.text

    def test_an_empty_filesystem_has_no_percentage(self, auth_client,
                                                   backup_dir, monkeypatch):
        import shutil
        monkeypatch.setattr(shutil, 'disk_usage',
                            lambda _path: shutil._ntuple_diskusage(0, 0, 0))
        assert _list(auth_client)['meta']['disk_used_pct'] is None

    @pytest.mark.parametrize('sort, expected', [
        ('name_asc', ['a', 'B', 'c']), ('name_desc', ['c', 'B', 'a'])])
    def test_name_sort_ignores_case(self, auth_client, backup_dir, sort,
                                    expected):
        for tag in ('B', 'c', 'a'):
            _write(backup_dir, f'ucm_backup_{tag}.ucmbkp')

        names = [item['filename'] for item in _list(auth_client, f'?sort={sort}')['items']]

        assert names == [f'ucm_backup_{tag}.ucmbkp' for tag in expected]

    def test_only_regular_archives_are_listed(self, auth_client, backup_dir,
                                              tmp_path):
        _write(backup_dir, _name('real'))
        outside = tmp_path / 'outside.ucmbkp'
        outside.write_bytes(b'secret')
        os.symlink(outside, backup_dir / _name('link'))
        (backup_dir / _name('dir')).mkdir()
        _write(backup_dir, 'notes.txt')
        _write(backup_dir, 'ucm backup.ucmbkp')

        names = [item['filename'] for item in _list(auth_client)['items']]

        assert names == [_name('real')]

    def test_both_urls_answer_the_same(self, auth_client, backup_dir):
        _write(backup_dir, _name('alias'))
        first = auth_client.get('/api/v2/system/backups?sort=name_asc')
        second = auth_client.get('/api/v2/system/backup/list?sort=name_asc')
        assert first.get_json()['data']['items'] == \
            second.get_json()['data']['items']


# ---------------------------------------------------------------------------
# Download and single deletion
# ---------------------------------------------------------------------------

class TestDownload:
    def test_a_traversal_is_refused(self, auth_client, backup_dir):
        response = auth_client.get(
            '/api/v2/system/backup/..%2F..%2Fetc%2Fpasswd/download')
        assert response.status_code in (400, 403, 404)
        assert b'root:' not in response.data

    def test_a_symlink_is_not_followed(self, auth_client, backup_dir, tmp_path):
        outside = tmp_path / 'outside.txt'
        outside.write_bytes(b'OUTSIDE-SECRET')
        os.symlink(outside, backup_dir / _name('link'))

        response = auth_client.get(f"/api/v2/system/backup/{_name('link')}/download")

        assert response.status_code in (403, 404)
        assert b'OUTSIDE-SECRET' not in response.data

    def test_absent_or_not_a_file_is_a_404(self, auth_client, backup_dir):
        (backup_dir / _name('dir')).mkdir()
        for tag in ('absent', 'dir'):
            response = auth_client.get(f'/api/v2/system/backup/{_name(tag)}/download')
            assert response.status_code == 404, (tag, response.data)
            assert _message(response) == 'Backup file not found'

    def test_an_archive_is_an_attachment_under_its_name(self, auth_client,
                                                        backup_dir):
        _write(backup_dir, _name('dl'), size=5)

        response = auth_client.get(f"/api/v2/system/backup/{_name('dl')}/download")

        assert response.status_code == 200
        assert response.data == b'xxxxx'
        disposition = response.headers['Content-Disposition']
        assert 'attachment' in disposition and _name('dl') in disposition
        assert response.mimetype == 'application/octet-stream'


class TestSingleDelete:
    def test_deletes_and_records_the_name(self, auth_client, backup_dir,
                                          audit_spy):
        path = _write(backup_dir, _name('del'))

        response = auth_client.delete(f"/api/v2/system/backup/{_name('del')}")

        assert response.status_code == 200, response.data
        assert _message(response) == 'Backup deleted successfully'
        assert not path.exists()
        assert [(c['action'], c['resource_name']) for c in audit_spy] == \
            [('backup_delete', _name('del'))]

    def test_a_symlink_is_refused_and_its_target_kept(self, auth_client,
                                                      backup_dir, tmp_path):
        outside = tmp_path / 'outside.txt'
        outside.write_bytes(b'keep me')
        os.symlink(outside, backup_dir / _name('link'))

        response = auth_client.delete(f"/api/v2/system/backup/{_name('link')}")

        assert response.status_code in (403, 404)
        assert outside.read_bytes() == b'keep me'

    def test_a_busy_lock_is_a_409_and_the_file_stays(
            self, auth_client, backup_dir, lock_held_elsewhere, audit_spy):
        path = _write(backup_dir, _name('busy'))

        response = auth_client.delete(f"/api/v2/system/backup/{_name('busy')}")

        assert response.status_code == 409, response.data
        assert 'backup operation' in _message(response)
        assert path.exists()
        assert audit_spy == []


# ---------------------------------------------------------------------------
# Bulk deletion
# ---------------------------------------------------------------------------

class TestBulkDelete:
    @pytest.mark.parametrize('payload', [
        {}, {'filenames': []}, {'filenames': 'x.ucmbkp'}, ['x.ucmbkp']])
    def test_a_body_without_a_list_is_refused(self, auth_client, backup_dir,
                                              payload):
        assert _bulk(auth_client, payload).status_code == 400

    def test_more_than_1000_names_deletes_nothing(self, auth_client, backup_dir):
        path = _write(backup_dir, _name('kept'))

        response = _bulk(auth_client, {'filenames': [_name('kept')] * 1001})

        assert response.status_code == 400
        assert path.exists()

    def test_1000_names_are_accepted(self, auth_client, backup_dir):
        _write(backup_dir, _name('edge'))
        data = _bulk(auth_client, {'filenames': [_name('edge')] * 1000}).get_json()
        assert data['data']['deleted'] == 1

    def test_a_repeated_name_is_handled_once(self, auth_client, backup_dir):
        _write(backup_dir, _name('twice'))

        response = _bulk(auth_client, {'filenames': [_name('twice')] * 2})

        assert response.status_code == 200, response.data
        assert response.get_json()['data'] == {
            'deleted': 1, 'missing': 0, 'invalid': 0, 'failed': 0}

    def test_mixed_names_are_counted(self, auth_client, backup_dir, audit_spy):
        path = _write(backup_dir, _name('here'))

        response = _bulk(auth_client, {'filenames': [
            _name('here'), '../../etc/passwd', _name('gone')]})

        assert response.status_code == 200, response.data
        assert response.get_json()['data'] == {
            'deleted': 1, 'missing': 1, 'invalid': 1, 'failed': 0}
        assert _message(response) == 'Deleted 1 backup(s)'
        assert not path.exists()
        assert [c['action'] for c in audit_spy] == ['backup_delete']
        assert audit_spy[0]['success'] is True

    def test_a_resolution_error_is_invalid_and_the_rest_goes_on(
            self, auth_client, backup_dir, monkeypatch):
        from services.backup import storage
        real = storage.resolve_archive
        path = _write(backup_dir, _name('after'))

        def flaky(raw, *args, **kwargs):
            if raw == _name('boom'):
                raise RuntimeError('symlink loop')
            return real(raw, *args, **kwargs)
        monkeypatch.setattr(storage, 'resolve_archive', flaky)

        response = _bulk(auth_client, {'filenames': [_name('boom'), _name('after')]})

        assert response.status_code == 200, response.data
        assert response.get_json()['data']['invalid'] == 1
        assert response.get_json()['data']['deleted'] == 1
        assert not path.exists()

    def test_a_symlink_is_not_deleted_through(self, auth_client, backup_dir,
                                              tmp_path):
        outside = tmp_path / 'outside.txt'
        outside.write_bytes(b'keep me')
        os.symlink(outside, backup_dir / _name('link'))

        response = _bulk(auth_client, {'filenames': [_name('link')]})

        assert response.status_code == 200
        assert response.get_json()['data']['deleted'] == 0
        assert outside.read_bytes() == b'keep me'

    def test_a_failed_unlink_is_counted_and_audited_as_a_failure(
            self, auth_client, backup_dir, monkeypatch, audit_spy):
        import pathlib
        _write(backup_dir, _name('stuck'))

        def refuse(self, *args, **kwargs):
            raise PermissionError('read-only')
        monkeypatch.setattr(pathlib.Path, 'unlink', refuse)

        response = _bulk(auth_client, {'filenames': [_name('stuck')]})

        assert response.status_code == 200
        assert response.get_json()['data']['failed'] == 1
        assert [(c['action'], c['success']) for c in audit_spy] == \
            [('backup_delete', False)]

    def test_a_busy_lock_is_a_409_and_nothing_moves(
            self, auth_client, backup_dir, lock_held_elsewhere, audit_spy):
        path = _write(backup_dir, _name('busy'))

        response = _bulk(auth_client, {'filenames': [_name('busy')]})

        assert response.status_code == 409, response.data
        assert 'backup operation' in _message(response)
        assert path.exists()
        assert audit_spy == []


# ---------------------------------------------------------------------------
# Retention on demand
# ---------------------------------------------------------------------------

class TestRetentionNow:
    def test_a_busy_lock_is_a_409(self, auth_client, backup_dir,
                                  lock_held_elsewhere):
        response = auth_client.post('/api/v2/system/backups/run-retention')
        assert response.status_code == 409, response.data

    def test_reports_what_was_removed(self, auth_client, backup_dir,
                                      monkeypatch, audit_spy):
        from services.backup import schedule
        monkeypatch.setattr(schedule, '_apply_retention', lambda days: 3)

        response = auth_client.post('/api/v2/system/backups/run-retention')

        assert response.status_code == 200, response.data
        assert response.get_json()['data'] == {'removed': 3}
        assert _message(response) == 'Retention applied: removed 3 backup(s)'
        assert [c['action'] for c in audit_spy] == ['backup_delete']

    def test_an_internal_failure_is_not_disclosed(self, auth_client, backup_dir,
                                                  monkeypatch):
        from services.backup import schedule

        def broken(days):
            raise RuntimeError('/secret/path exploded')
        monkeypatch.setattr(schedule, '_apply_retention', broken)

        response = auth_client.post('/api/v2/system/backups/run-retention')

        assert response.status_code == 500
        assert _message(response) == 'Failed to apply retention'
        assert b'/secret/path' not in response.data


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def _create(client, payload, url='/api/v2/system/backup'):
    return client.post(url, data=json.dumps(payload),
                       content_type='application/json')


class TestCreate:
    def test_pbkdf2_on_request_writes_a_readable_archive(
            self, app, auth_client, backup_dir, audit_spy):
        from services.backup_service import BackupService

        response = _create(auth_client, {'password': PASSWORD, 'kdf': 'pbkdf2'})

        assert response.status_code == 200, response.data
        body = response.get_json()
        data = body['data']
        assert body['message'] == 'Backup created successfully'
        blob = (backup_dir / data['filename']).read_bytes()
        assert data['size_bytes'] == len(blob)
        assert data['size'].endswith((' B', ' KB', ' MB'))
        assert data['download_url'] == \
            f"/api/v2/system/backup/{data['filename']}/download"
        metadata = json.loads(blob[10:10 + int.from_bytes(blob[8:10], 'big')])
        assert metadata['kdf']['type'].startswith('pbkdf2')
        with app.app_context():
            _key, payload = BackupService()._decrypt_framed(blob, PASSWORD)
        assert 'metadata' in payload
        assert [c['action'] for c in audit_spy] == ['system_backup']

    @pytest.mark.parametrize('kdf', [None, 'argon2id'])
    def test_the_kdf_reaches_the_service(self, auth_client, backup_dir,
                                         monkeypatch, kdf):
        from services.backup_service import BackupService
        seen = []

        def fake(self, password, **kwargs):
            seen.append(kwargs.get('kdf', 'absent'))
            return b'UCMB' + b'\x03' * 60
        monkeypatch.setattr(BackupService, 'create_backup', fake)
        payload = {'password': PASSWORD}
        if kdf:
            payload['kdf'] = kdf

        response = _create(auth_client, payload)

        assert response.status_code == 200, response.data
        assert seen == [kdf]

    def test_missing_password(self, auth_client, backup_dir):
        assert _create(auth_client, {}).status_code == 400

    @pytest.mark.parametrize('error, status, message', [
        ('export', 500, 'Backup aborted: table x unreadable'),
        ('validation', 500, 'Backup could not be validated: short read'),
        ('value', 400, 'Invalid backup parameters'),
        ('other', 500, 'Backup failed'),
    ])
    def test_service_failures_are_mapped(self, auth_client, backup_dir,
                                         monkeypatch, error, status, message):
        from services.backup_service import (
            BackupExportError, BackupService, BackupValidationError)
        raised = {
            'export': BackupExportError('table x unreadable'),
            'validation': BackupValidationError('short read'),
            'value': ValueError('/internal/detail'),
            'other': RuntimeError('/internal/detail'),
        }[error]

        def fail(self, *args, **kwargs):
            raise raised
        monkeypatch.setattr(BackupService, 'create_backup', fail)

        response = _create(auth_client, {'password': PASSWORD})

        assert response.status_code == status
        assert _message(response) == message
        assert b'/internal/detail' not in response.data

    def test_a_fips_refusal_from_the_service_keeps_its_type(
            self, auth_client, backup_dir, monkeypatch):
        from services.backup_service import BackupService

        def fail(self, *args, **kwargs):
            raise fips_mode.FipsRestricted('Argon2id backups not available in FIPS mode')
        monkeypatch.setattr(BackupService, 'create_backup', fail)

        response = _create(auth_client, {'password': PASSWORD})

        assert response.status_code == 400
        body = response.get_json()
        assert body['type'] == fips_mode.PROBLEM_TYPE
        assert body['message'] == 'Argon2id backups not available in FIPS mode'


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def _restore(client, blob=b'x', password=PASSWORD, url='/api/v2/system/restore',
             **fields):
    data = {'file': (io.BytesIO(blob), 'r.ucmbkp'), 'password': password}
    data.update(fields)
    return client.post(url, data=data, content_type='multipart/form-data')


@pytest.fixture
def fake_restore(monkeypatch):
    """Replace the service restore; records the calls."""
    from services.backup_service import BackupService
    calls = []
    outcome = {'value': {'sections_carried': []}}

    def fake(self, blob, password, **kwargs):
        calls.append(kwargs)
        value = outcome['value']
        if isinstance(value, Exception):
            raise value
        return dict(value)
    monkeypatch.setattr(BackupService, 'restore_backup', fake)
    return calls, outcome


@pytest.fixture
def invalidations(monkeypatch):
    import services.backup.restore.invalidate as invalidate
    from utils import service_manager
    done = []
    monkeypatch.setattr(invalidate, 'invalidate_after_restore',
                        lambda *a, **k: done.append(1) or {'sessions_revoked': 4})
    monkeypatch.setattr(service_manager, 'restart_service',
                        lambda: (True, 'restart requested'))
    return done


class TestRestore:
    def test_a_four_character_password_that_decrypts_is_accepted(
            self, app, auth_client, monkeypatch):
        from services.backup_service import BackupService
        with app.app_context(), monkeypatch.context() as patch:
            patch.setattr(BackupService, '_validate_password',
                          lambda self, password: None)
            blob = BackupService().create_backup(
                'abcd', include={name: False for name in manifest.SECTIONS})

        response = _restore(auth_client, blob, password='abcd', mode='merge')

        assert response.status_code == 200, response.data

    @pytest.mark.parametrize('fields, status', [
        ({'mode': 'append'}, 400),
        ({'mode': 'MERGE'}, 200),
        ({}, 200),
    ])
    def test_mode(self, auth_client, fake_restore, fields, status):
        calls, _ = fake_restore
        response = _restore(auth_client, **fields)
        assert response.status_code == status, response.data
        if status == 200:
            assert calls[0]['mode'] == (fields.get('mode') or 'replace').lower()
        else:
            assert calls == []

    def test_missing_file_or_password(self, auth_client, fake_restore):
        assert auth_client.post('/api/v2/system/restore', data={'password': 'x'},
                                content_type='multipart/form-data').status_code == 400
        assert _restore(auth_client, password='').status_code == 400

    def test_an_unknown_extension_is_refused(self, auth_client, fake_restore):
        calls, _ = fake_restore
        response = auth_client.post(
            '/api/v2/system/restore',
            data={'file': (io.BytesIO(b'x'), 'r.exe'), 'password': PASSWORD},
            content_type='multipart/form-data')
        assert response.status_code == 400
        assert _message(response) == 'Invalid backup file'
        assert calls == []

    def test_an_oversized_upload_is_refused(self, auth_client, fake_restore,
                                            monkeypatch):
        from api.v2.system import backup as route
        monkeypatch.setattr(route, 'MAX_RESTORE_UPLOAD_BYTES', 8)
        calls, _ = fake_restore

        response = _restore(auth_client, b'x' * 9)

        assert response.status_code == 400
        assert _message(response) == 'Invalid backup file'
        assert calls == []

    def test_a_pending_switch_refuses_before_restoring(
            self, app, auth_client, fake_restore):
        from services.database_admin.lock import (
            clear_switch_pending, mark_switch_pending)
        calls, _ = fake_restore
        mark_switch_pending('postgresql')
        try:
            response = _restore(auth_client)
        finally:
            clear_switch_pending()

        assert response.status_code == 409, response.data
        assert calls == []

    def test_a_running_migration_refuses(self, app, auth_client, fake_restore):
        from services.database_admin.lock import database_migration_lock
        calls, _ = fake_restore
        taken, release = threading.Event(), threading.Event()

        def hold():
            with database_migration_lock(purpose='a migration'):
                taken.set()
                release.wait(timeout=30)

        holder = threading.Thread(target=hold, daemon=True)
        holder.start()
        try:
            assert taken.wait(timeout=10)
            response = _restore(auth_client)
        finally:
            release.set()
            holder.join(timeout=10)

        assert response.status_code == 409, response.data
        assert calls == []

    def test_an_empty_archive_revokes_nothing(self, auth_client, fake_restore,
                                              invalidations, audit_spy):
        response = _restore(auth_client)

        assert response.status_code == 200, response.data
        body = response.get_json()
        assert 'no data' in body['message']
        assert 'restart_requested' not in body['data']
        assert invalidations == []
        assert [c['action'] for c in audit_spy] == ['system_restore']
        assert 'nothing was restored' in audit_spy[0]['details']

    def test_a_restore_with_data_revokes_and_restarts(
            self, auth_client, fake_restore, invalidations, audit_spy):
        _, outcome = fake_restore
        outcome['value'] = {'sections_carried': ['groups'],
                            'admin_allowlist_cleared': True}

        response = _restore(auth_client, url='/api/v2/system/backup/restore')

        assert response.status_code == 200, response.data
        data = response.get_json()['data']
        assert invalidations == [1]
        assert data['invalidated'] == {'sessions_revoked': 4}
        assert data['restart_requested'] is True
        assert data['restart_detail'] == 'restart requested'
        assert data['admin_allowlist_cleared'] is True
        assert audit_spy[0]['details'] == 'Restored from backup: r.ucmbkp'

    @pytest.mark.parametrize('error, status, needle', [
        ('decrypt', 400, 'password'),
        ('schema', 400, 'schema 99 unknown'),
        ('overflow', 400, 'numeric value'),
        ('other', 500, 'Restore failed'),
    ])
    def test_failures_are_mapped(self, auth_client, fake_restore, error,
                                 status, needle):
        from services.backup.decrypt_mixin import BackupDecryptionError
        from services.backup_service import BackupSchemaError
        _, outcome = fake_restore
        outcome['value'] = {
            'decrypt': BackupDecryptionError('tag mismatch'),
            'schema': BackupSchemaError('schema 99 unknown'),
            'overflow': OverflowError('/internal/int too big'),
            'other': RuntimeError('/internal/detail'),
        }[error]

        response = _restore(auth_client)

        assert response.status_code == status
        assert needle in _message(response)
        assert b'/internal/' not in response.data

    def test_a_fips_refusal_keeps_its_type(self, auth_client, fake_restore):
        _, outcome = fake_restore
        outcome['value'] = fips_mode.FipsRestricted(
            'Argon2id backups not available in FIPS mode')

        response = _restore(auth_client)

        assert response.status_code == 400
        body = response.get_json()
        assert body['type'] == fips_mode.PROBLEM_TYPE
        assert 'password' not in body['message'].lower()


# ---------------------------------------------------------------------------
# An audit failure after a completed operation
# ---------------------------------------------------------------------------

@pytest.fixture
def audit_down(monkeypatch):
    from services.audit_service import AuditService

    def broken(**kwargs):
        raise RuntimeError('the audit store is unreachable')
    monkeypatch.setattr(AuditService, 'log_action', staticmethod(broken))


class TestAnAuditFailureDoesNotUndoTheAnswer:
    def test_create(self, auth_client, backup_dir, audit_down, monkeypatch):
        from services.backup_service import BackupService
        monkeypatch.setattr(BackupService, 'create_backup',
                            lambda self, password, **kw: b'UCMB' + b'\x03' * 60)

        response = _create(auth_client, {'password': PASSWORD})

        assert response.status_code == 200, response.data
        assert (backup_dir / response.get_json()['data']['filename']).is_file()

    def test_delete(self, auth_client, backup_dir, audit_down):
        path = _write(backup_dir, _name('audited'))
        response = auth_client.delete(f"/api/v2/system/backup/{_name('audited')}")
        assert response.status_code == 200, response.data
        assert not path.exists()

    def test_bulk_delete(self, auth_client, backup_dir, audit_down):
        path = _write(backup_dir, _name('audited'))
        response = _bulk(auth_client, {'filenames': [_name('audited')]})
        assert response.status_code == 200, response.data
        assert response.get_json()['data']['deleted'] == 1
        assert not path.exists()

    def test_retention(self, auth_client, backup_dir, audit_down, monkeypatch):
        from services.backup import schedule
        path = _write(backup_dir, _name('expired'))

        def prune(days):
            path.unlink()
            return 1
        monkeypatch.setattr(schedule, '_apply_retention', prune)

        response = auth_client.post('/api/v2/system/backups/run-retention')

        assert response.status_code == 200, response.data
        assert response.get_json()['data'] == {'removed': 1}
        assert not path.exists()
