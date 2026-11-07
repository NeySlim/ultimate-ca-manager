"""Uploads spool under DATA_DIR/tmp, not the system temp dir (a small tmpfs in some deployments)."""
import io
import logging
import os
from pathlib import Path

import pytest

PASSWORD = 'Correct-Horse-Battery-9'
TWO_MIB = 2 * 1024 * 1024


def _spool_dir():
    # The DATA_DIR the app booted with (tests later sandbox Config.DATA_DIR itself)
    return os.path.realpath(Path(os.environ['DATA_DIR']) / 'tmp')


@pytest.fixture
def seen(monkeypatch):
    """Record where the restore route's upload is spooled, then let the route go on."""
    import api.v2.system.backup as route
    original = route.validate_upload
    records = []

    def spy(file, *args, **kwargs):
        stream = file.stream
        assert getattr(stream, '_rolled', True), 'a 2 MiB upload must be on disk'
        fd = stream.fileno()
        target = os.readlink(f'/proc/self/fd/{fd}').removesuffix(' (deleted)')
        records.append({'stream': stream, 'dir': os.path.dirname(target),
                        'links': os.fstat(fd).st_nlink})
        return original(file, *args, **kwargs)

    monkeypatch.setattr(route, 'validate_upload', spy)
    return records


def _restore(client, name='r.ucmbkp'):
    data = {'file': (io.BytesIO(b'\0' * TWO_MIB), name), 'password': PASSWORD}
    return client.post('/api/v2/system/restore', data=data,
                       content_type='multipart/form-data')


def test_the_spool_dir_is_private(app):
    assert app.config['UPLOAD_SPOOL_DIR'] == _spool_dir()
    assert os.stat(_spool_dir()).st_mode & 0o777 == 0o700


def test_an_upload_spools_under_data_dir_and_is_released_on_success(
        auth_client, seen, monkeypatch):
    from services.backup_service import BackupService
    monkeypatch.setattr(BackupService, 'restore_backup',
                        lambda self, blob, password, **kw: {'sections_carried': []})
    before = set(os.listdir(_spool_dir()))

    response = _restore(auth_client)

    assert response.status_code == 200, response.get_json()
    assert seen and seen[0]['dir'] == _spool_dir()
    assert seen[0]['links'] == 0          # never has a name a crash could leave behind
    assert seen[0]['stream'].closed
    assert set(os.listdir(_spool_dir())) == before


def test_an_upload_is_released_when_the_request_fails(auth_client, seen):
    before = set(os.listdir(_spool_dir()))

    response = _restore(auth_client, name='r.exe')   # refused by validate_upload

    assert response.status_code == 400
    assert seen and seen[0]['dir'] == _spool_dir()
    assert seen[0]['stream'].closed
    assert set(os.listdir(_spool_dir())) == before


def test_an_unwritable_data_dir_falls_back_to_the_system_temp_dir(tmp_path, caplog):
    from utils.upload_spool import prepare_spool_dir
    not_a_dir = tmp_path / 'data'
    not_a_dir.write_text('a file where DATA_DIR should be')

    with caplog.at_level(logging.WARNING, logger='utils.upload_spool'):
        assert prepare_spool_dir(not_a_dir) is None

    warnings = [r for r in caplog.records if r.name == 'utils.upload_spool']
    assert len(warnings) == 1 and 'system temp' in warnings[0].getMessage()


def test_without_a_spool_dir_uploads_use_the_system_temp_dir(app, monkeypatch):
    import tempfile
    from flask import request
    monkeypatch.setitem(app.config, 'UPLOAD_SPOOL_DIR', None)
    data = {'file': (io.BytesIO(b'\0' * TWO_MIB), 'r.bin')}

    with app.test_request_context('/', method='POST', data=data,
                                  content_type='multipart/form-data'):
        fd = request.files['file'].stream.fileno()
        target = os.readlink(f'/proc/self/fd/{fd}').removesuffix(' (deleted)')

    assert os.path.dirname(target) == os.path.realpath(tempfile.gettempdir())
