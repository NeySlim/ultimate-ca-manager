"""The files of a restore follow its rows: published with the commit, never before.

A failed restore left the certificate and key files of authorities that were
never committed, written at insert time; a replacement left the files of the
rows it removed. Both now go through the staged publication.
"""
import uuid

import pytest

from models import CA, db
from services.backup.errors import BackupSchemaError
from tests.test_backup_restore_failfast import UNREADABLE_KEY, SSH_PUBLIC_KEY, _reseal
from tests.test_restore_replace_dependents import (
    PASSWORD, _authority_row, _only, _service, _target,
)
from utils.file_naming import ca_cert_path, ca_key_path


@pytest.fixture
def target(app, tmp_path):
    with _target(app, 'sqlite', tmp_path, f'orphans_{uuid.uuid4().hex[:8]}'):
        yield


def _files(row):
    return ca_cert_path(row), ca_key_path(row)


def _with_a_mirror(row):
    """The certificate written at insert, and a key mirror as an older install left it."""
    cert, key = _files(row)
    assert cert.exists()
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_bytes(b'-----BEGIN PRIVATE KEY-----\nmirror\n')
    return cert, key


def _failing(blob):
    """The archive, plus an SSH authority whose key nothing can read: the restore fails late."""
    svc = _service()
    _key, data = svc._decrypt_framed(blob, PASSWORD)
    data.setdefault('ssh_cas', []).append({
        'refid': f'orphans-ssh-{uuid.uuid4().hex[:6]}', 'descr': 'unreadable', 'ca_type': 'user',
        'key_type': 'ed25519', 'public_key': SSH_PUBLIC_KEY, 'fingerprint': 'SHA256:orphans',
        'serial_counter': 0, 'private_key_pem_encrypted': UNREADABLE_KEY})
    return _reseal(blob, data)


def test_a_replacement_removes_the_files_of_the_rows_it_removes(target):
    kept = _authority_row(f'kept-{uuid.uuid4().hex[:8]}')[0]
    db.session.commit()
    blob = _service().create_backup(PASSWORD, include=_only('certificate_authorities'))
    removed = _authority_row(f'gone-{uuid.uuid4().hex[:8]}')[0]
    db.session.commit()
    cert, key = _with_a_mirror(removed)

    _service().restore_backup(blob, PASSWORD, mode='replace')

    assert not cert.exists() and not key.exists()
    assert ca_cert_path(kept).exists()


def test_a_failed_replacement_keeps_them(target):
    _authority_row(f'kept-{uuid.uuid4().hex[:8]}')
    db.session.commit()
    blob = _failing(_service().create_backup(PASSWORD, include=_only('certificate_authorities')))
    survivor = _authority_row(f'stays-{uuid.uuid4().hex[:8]}')[0]
    db.session.commit()
    refid = survivor.refid
    cert, key = _with_a_mirror(survivor)

    with pytest.raises(BackupSchemaError):
        _service().restore_backup(blob, PASSWORD, mode='replace')

    db.session.rollback()
    assert CA.query.filter_by(refid=refid).one()
    assert cert.exists() and key.exists()


def test_a_failed_restore_writes_no_file_for_the_rows_it_did_not_keep(target):
    archived = _authority_row(f'never-{uuid.uuid4().hex[:8]}')[0]
    db.session.commit()
    blob = _failing(_service().create_backup(PASSWORD, include=_only('certificate_authorities')))
    refid = archived.refid
    cert, key = _files(archived)
    db.session.delete(archived)
    db.session.commit()
    cert.unlink(missing_ok=True)
    key.unlink(missing_ok=True)

    with pytest.raises(BackupSchemaError):
        _service().restore_backup(blob, PASSWORD, mode='merge')

    db.session.rollback()
    assert CA.query.filter_by(refid=refid).first() is None
    assert not cert.exists() and not key.exists()


@pytest.mark.parametrize('encrypted', [False, True])
def test_a_key_mirror_waits_for_the_publication(tmp_path, monkeypatch, encrypted):
    """Written at once, a mirror outlived the rollback; removed at once, it was lost by one."""
    from security.encryption import key_encryption
    from services.backup.restore.files import StagedFiles
    from services.backup.restore_core import _stage_key_mirror

    monkeypatch.setattr(type(key_encryption), 'is_enabled', property(lambda self: encrypted))
    mirror = tmp_path / 'private' / 'ca_x.key'
    mirror.parent.mkdir()
    mirror.write_bytes(b'before')
    staged = StagedFiles(base_dir=tmp_path / 'staging')
    try:
        _stage_key_mirror(staged, mirror, b'restored')
        assert mirror.read_bytes() == b'before'
        staged.publish()
        assert (not mirror.exists()) if encrypted else mirror.read_bytes() == b'restored'
        staged.unpublish()
        assert mirror.read_bytes() == b'before'
    finally:
        staged.discard()
