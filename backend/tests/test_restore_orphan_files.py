"""The files of a restore follow its rows: never written by the restore, reconciled after.

A failed restore left the certificate and key files of authorities that were
never committed, written at insert time; a replacement left the files of the
rows it removed. A restore now writes no file and lists what it removed; the
reconciliation then follows the committed rows, on SQLite and on PostgreSQL.
"""
import base64
import uuid

import pytest

from models import CA, db
from services.backup.errors import BackupSchemaError
from tests.test_backup_restore_failfast import UNREADABLE_KEY, SSH_PUBLIC_KEY, _reseal
from tests.test_restore_replace_dependents import (
    ENGINES, PASSWORD, _authority_row, _only, _service, _target,
)
from utils.file_naming import ca_cert_path, ca_key_path


@pytest.fixture(params=ENGINES)
def target(request, app, tmp_path):
    with _target(app, request.param, tmp_path, f'orphans_{uuid.uuid4().hex[:8]}'):
        yield request.param


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
    assert cert.exists() and key.exists(), 'the restore itself wrote to the disk'

    from services.file_regen_service import reconcile_files
    assert reconcile_files()['status'] == 'done'
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


# (DEKs loaded, new values encrypted): (False, False) off, (True, False) a disable's grace
@pytest.mark.parametrize('enabled,encrypted', [(False, False), (True, False), (True, True)])
def test_a_key_mirror_follows_the_values(target, monkeypatch, enabled, encrypted):
    """Mirrored while values are stored in the clear, removed while they are encrypted."""
    from security.encryption import key_encryption
    from services import file_regen_service as regen
    from utils.key_codec import load_pem_bytes

    row = _authority_row(f'mirror-{uuid.uuid4().hex[:8]}')[0]
    db.session.commit()
    key_pem = load_pem_bytes(row.prv)
    if not encrypted:    # values stored in the clear, as a disable leaves them
        row.prv = base64.b64encode(key_pem).decode('ascii')
    mirror = ca_key_path(row)
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_bytes(b'before')
    regen.advance_generation()
    db.session.commit()
    monkeypatch.setattr(type(key_encryption), 'is_enabled', property(lambda self: enabled))
    monkeypatch.setattr(type(key_encryption), 'is_encrypting', property(lambda self: encrypted))
    regen.reconcile_files()
    assert (not mirror.exists()) if encrypted else mirror.read_bytes() == key_pem
