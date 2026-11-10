"""Creating an archive streams it: no step serialises or holds the whole payload."""
import json

import pytest

from config.settings import Config
from services.backup import container, storage

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'
CHUNK_MAX = container.CHUNK_MAX_RANGE[0]


@pytest.fixture
def small_chunks(app, tmp_path, monkeypatch):
    """Chunks at their floor, and a section well past it, rows that are not in the database."""
    from services.backup import backup_service
    from services.backup_service import BackupService

    monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
    monkeypatch.setattr(BackupService, 'CHUNK_MAX', CHUNK_MAX)
    real = backup_service.export_section

    def with_synthetic_rows(name, index, warnings=None):
        rows = real(name, index, warnings)
        if name == 'deploy_targets':
            rows += [{'name': f'synthetic-{n}', 'note': 'x' * 1000} for n in range(400)]
        return rows

    monkeypatch.setattr(backup_service, 'export_section', with_synthetic_rows)
    return tmp_path


def test_export_never_serialises_more_than_a_chunk(app, small_chunks, monkeypatch):
    produced = []
    real_dumps = json.dumps

    def measured(*args, **kwargs):
        text = real_dumps(*args, **kwargs)
        produced.append(len(text))
        return text

    monkeypatch.setattr(json, 'dumps', measured)
    with app.app_context():
        from services.backup_service import BackupService
        service = BackupService()
        size, path, filename = storage.export_archive(service, PASSWORD)

    assert service.last_payload_size > 5 * CHUNK_MAX
    assert max(produced) <= CHUNK_MAX
    assert path.name == filename and path.stat().st_size == size
    assert not list(small_chunks.glob('.ucm_backup_*.tmp'))


def test_the_streamed_archive_restores_what_was_exported(app, small_chunks):
    with app.app_context():
        from services.backup_service import BackupService
        service = BackupService()
        _size, path, _filename = storage.export_archive(service, PASSWORD)
        _key, payload = service._decrypt_framed(path.read_bytes(), PASSWORD)
    synthetic = [row for row in payload['deploy_targets']
                 if row['name'].startswith('synthetic-')]
    assert len(synthetic) == 400
    assert payload['metadata']['sections']['deploy_targets'] == len(payload['deploy_targets'])


def test_the_scheduled_backup_streams_too(app, small_chunks, monkeypatch):
    from services.backup import schedule
    calls = []
    monkeypatch.setattr(storage, 'export_archive',
                        lambda service, password, **kwargs: calls.append(kwargs)
                        or (7, small_chunks / 'x.ucmbkp', 'x.ucmbkp'))
    # The run marks itself attempted: put the mark back for the files after this one
    monkeypatch.setitem(schedule._LAST_ATTEMPT, 'at', schedule._LAST_ATTEMPT.get('at'))
    monkeypatch.setattr(schedule, '_apply_retention', lambda days: 0)
    monkeypatch.setattr(schedule, '_record_last_run', lambda now: None)
    monkeypatch.setattr(schedule, '_record_outcome', lambda *args: None)
    monkeypatch.setattr(schedule, '_audit_scheduled_backup', lambda *args, **kwargs: None)
    with app.app_context():
        from utils.datetime_utils import utc_now
        result = schedule._create_scheduled_backup({}, utc_now(), PASSWORD)
    assert calls and result['size'] == 7


def test_a_failed_export_leaves_no_temporary_file(app, small_chunks, monkeypatch):
    from services.backup import backup_service
    from services.backup.errors import BackupExportError

    def broken(name, index, warnings=None):
        if name == 'deploy_targets':
            raise RuntimeError('database gone')
        return []

    monkeypatch.setattr(backup_service, 'export_section', broken)
    with app.app_context():
        from services.backup_service import BackupService
        with pytest.raises(BackupExportError):
            storage.export_archive(BackupService(), PASSWORD)
    assert [p.name for p in small_chunks.iterdir() if not p.name.endswith('.lock')] == []
