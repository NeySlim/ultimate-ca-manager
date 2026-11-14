"""check_archive_opens: what an HA restore runs before setting the cluster maintenance.
It refuses as the restore would (password, framing, KDF, FIPS) and reads the stream back
to its start, so the restore that follows sees the archive whole."""
import io

import pytest

import fips_mode
from fips_mode import FipsRestricted
from services.backup import manifest
from services.backup.container import ContainerError
from services.backup.decrypt_mixin import BackupDecryptionError
from tests.backup_v3 import as_v3
from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Preflight-Password-2026'


def _service():
    from services.backup_service import BackupService
    return BackupService()


@pytest.fixture(scope='module')
def archive(app):
    with app.app_context():
        return _service().create_backup(
            PASSWORD, include={n: n == 'groups' for n in manifest.SECTIONS})


def _at_offset(blob):
    """A stream whose archive starts past some bytes already consumed."""
    stream = io.BytesIO(b'spooled-' + blob)
    stream.seek(len(b'spooled-'))
    return stream


@pytest.mark.parametrize('version', ['v4', 'v3'])
def test_a_good_archive_opens_and_the_stream_is_back_at_its_start(app, archive, version):
    blob = archive if version == 'v4' else as_v3(archive, PASSWORD)
    stream = _at_offset(blob)
    _service().check_archive_opens(stream, PASSWORD)
    assert stream.tell() == len(b'spooled-')
    assert stream.read() == blob


@pytest.mark.parametrize('version', ['v4', 'v3'])
def test_a_wrong_password_is_refused_and_the_stream_rewound(app, archive, version):
    blob = archive if version == 'v4' else as_v3(archive, PASSWORD)
    stream = _at_offset(blob)
    with pytest.raises(BackupDecryptionError):
        _service().check_archive_opens(stream, 'not-the-password')
    assert stream.tell() == len(b'spooled-')


def test_a_file_that_is_not_a_backup_is_refused(app):
    with pytest.raises(ValueError):
        _service().check_archive_opens(io.BytesIO(b'UCMB' + b'\x04' * 64), PASSWORD)
    with pytest.raises(ContainerError):
        _service().check_archive_opens(io.BytesIO(b'UCMB\x04\x00\x02\x00\xff\xff'), PASSWORD)


def test_an_argon2id_archive_is_refused_in_fips_mode(app, archive, monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    with pytest.raises(FipsRestricted):
        _service().check_archive_opens(io.BytesIO(archive), PASSWORD)


def test_an_archive_of_a_later_schema_is_refused_on_its_first_chunk(app, monkeypatch):
    from services.backup.restore_core import BackupSchemaError
    from services.backup_service import BackupService
    with app.app_context():
        with monkeypatch.context() as later:
            later.setattr(BackupService, 'SCHEMA_VERSION', BackupService.SCHEMA_VERSION + 1)
            blob = _service().create_backup(
                PASSWORD, include={n: n == 'groups' for n in manifest.SECTIONS})
        stream = _at_offset(blob)
        with pytest.raises(BackupSchemaError, match='newer than'):
            _service().check_archive_opens(stream, PASSWORD)
        assert stream.tell() == len(b'spooled-')


def test_outside_ha_the_restore_window_runs_no_check(app):
    """One node has no group to spare: the restore itself refuses, the key is derived once."""
    from services import cluster_maintenance
    ran = []
    with app.app_context():
        with cluster_maintenance.restore_window('admin', preflight=lambda: ran.append(1)) as hold:
            assert hold is None
    assert ran == []
