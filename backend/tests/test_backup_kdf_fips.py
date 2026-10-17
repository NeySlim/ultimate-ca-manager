"""Backup KDF in FIPS mode (#399): archives are written with PBKDF2, an
Argon2id archive is refused before any derivation, and nothing changes
outside FIPS mode."""
import io
import json

import pytest

import fips_mode
from fips_mode import FipsRestricted
from services.backup import container, manifest

PASSWORD = 'Correct-Horse-Battery-9'
ARGON2_REFUSAL = ('Backups protected with Argon2id cannot be restored in FIPS mode: '
                  'convert the archive to PBKDF2 on a standard (non-FIPS) instance first')


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _groups_only():
    return {name: name == 'groups' for name in manifest.SECTIONS}


def _kdf_of(blob):
    metadata, _header, _ciphertext = container.parse_header(blob)
    return metadata['kdf_id'], metadata['kdf']['type']


@pytest.fixture
def fips(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)


@pytest.fixture
def no_argon2_derivation(monkeypatch):
    from services.backup_service import BackupService

    def forbidden(self, *a, **k):
        raise AssertionError('Argon2id derivation attempted')

    monkeypatch.setattr(BackupService, '_derive_argon2id', forbidden)


@pytest.fixture(scope='module')
def argon2_archive(app):
    with app.app_context():
        return _service().create_backup(PASSWORD, include=_groups_only())


class TestCreation:
    def test_fips_mode_writes_pbkdf2(self, app, fips, no_argon2_derivation):
        with app.app_context():
            blob = _service().create_backup(PASSWORD, include=_groups_only())
        assert _kdf_of(blob) == (container.KDF_PBKDF2, 'pbkdf2-sha256')

    def test_standard_mode_still_writes_argon2id(self, argon2_archive):
        assert _kdf_of(argon2_archive) == (container.KDF_ARGON2ID, 'argon2id')


class TestRestore:
    def test_argon2id_is_refused_in_fips_mode_before_deriving(
            self, fips, no_argon2_derivation, argon2_archive):
        with pytest.raises(FipsRestricted) as exc:
            _service()._decrypt_framed(argon2_archive, PASSWORD)
        assert str(exc.value) == ARGON2_REFUSAL

    def test_argon2id_still_opens_outside_fips_mode(self, argon2_archive):
        _key, payload = _service()._decrypt_framed(argon2_archive, PASSWORD)
        assert 'groups' in payload

    def test_pbkdf2_from_standard_mode_opens_in_fips_mode(self, app, monkeypatch):
        import services.backup.backup_service as writer
        monkeypatch.setattr(writer, '_ARGON2_AVAILABLE', False)
        with app.app_context():
            blob = _service().create_backup(PASSWORD, include=_groups_only())
        assert _kdf_of(blob)[0] == container.KDF_PBKDF2
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        _key, payload = _service()._decrypt_framed(blob, PASSWORD)
        assert 'groups' in payload

    def test_pbkdf2_from_fips_mode_restores_outside_fips_mode(self, app, monkeypatch):
        from models import db
        from models.group import Group
        name = 'fips-kdf-roundtrip'
        with app.app_context():
            db.session.add(Group(name=name))
            db.session.commit()
            monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
            blob = _service().create_backup(PASSWORD, include=_groups_only())
            monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
            Group.query.filter_by(name=name).delete()
            db.session.commit()
            try:
                _service().restore_backup(blob, PASSWORD, mode='merge')
                assert Group.query.filter_by(name=name).count() == 1
            finally:
                Group.query.filter_by(name=name).delete()
                db.session.commit()
        assert _kdf_of(blob)[0] == container.KDF_PBKDF2


@pytest.mark.parametrize('route', ['/api/v2/system/restore', '/api/v2/settings/backup/restore'])
def test_the_refusal_reaches_the_restore_api_unchanged(
        auth_client, fips, no_argon2_derivation, argon2_archive, route):
    r = auth_client.post(route, data={'password': PASSWORD,
                                      'file': (io.BytesIO(argon2_archive), 'b.ucmbkp')},
                         content_type='multipart/form-data')
    body = json.loads(r.data)
    assert r.status_code == 400, r.data
    assert body['type'] == fips_mode.PROBLEM_TYPE
    assert body['message'] == ARGON2_REFUSAL
