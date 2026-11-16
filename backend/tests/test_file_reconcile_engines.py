"""What a restore's transaction writes for the files, and the reconciliation's lock, on both engines."""
import uuid
from pathlib import Path

import pytest

from models import FileRemoval, db
from services.backup.errors import BackupSchemaError
from tests.test_backup_restore_failfast import SSH_PUBLIC_KEY, UNREADABLE_KEY, _reseal
from tests.test_restore_replace_dependents import (
    ENGINES, PASSWORD, _authority_row, _only, _service, _target,
)
from utils.file_naming import ca_cert_path


@pytest.fixture(params=ENGINES)
def target(request, app, tmp_path):
    with _target(app, request.param, tmp_path, f'files_{uuid.uuid4().hex[:8]}'):
        yield request.param


def _generation():
    from services.file_regen_service import current_generation
    db.session.rollback()
    return current_generation()


def test_a_replacement_commits_its_generation_and_the_paths_it_removed(target):
    kept = _authority_row(f'kept-{uuid.uuid4().hex[:8]}')[0]
    db.session.commit()
    blob = _service().create_backup(PASSWORD, include=_only('certificate_authorities'))
    removed = _authority_row(f'gone-{uuid.uuid4().hex[:8]}')[0]
    db.session.commit()
    gone = str(ca_cert_path(removed))
    before = _generation()

    results = _service().restore_backup(blob, PASSWORD, mode='replace')

    after = _generation()
    from services.file_regen_service import generation_number
    assert generation_number(after) == generation_number(before) + 1
    listed = {row.path for row in FileRemoval.query.filter_by(
        generation=generation_number(after))}
    assert gone in listed and str(ca_cert_path(kept)) not in listed
    assert results['files']['removals'] == len(listed)


def test_a_restore_that_fails_commits_neither(target):
    _authority_row(f'kept-{uuid.uuid4().hex[:8]}')
    db.session.commit()
    blob = _service().create_backup(PASSWORD, include=_only('certificate_authorities'))
    _key, data = _service()._decrypt_framed(blob, PASSWORD)
    data.setdefault('ssh_cas', []).append({
        'refid': f'files-ssh-{uuid.uuid4().hex[:6]}', 'descr': 'unreadable', 'ca_type': 'user',
        'key_type': 'ed25519', 'public_key': SSH_PUBLIC_KEY, 'fingerprint': 'SHA256:files',
        'serial_counter': 0, 'private_key_pem_encrypted': UNREADABLE_KEY})
    _authority_row(f'stays-{uuid.uuid4().hex[:8]}')
    db.session.commit()
    before, listed = _generation(), FileRemoval.query.count()

    with pytest.raises(BackupSchemaError):
        _service().restore_backup(_reseal(blob, data), PASSWORD, mode='replace')

    assert _generation() == before and FileRemoval.query.count() == listed


def test_in_ha_nodes_sharing_a_directory_take_turns(target, monkeypatch, tmp_path):
    """A shared directory carries one id, so one advisory lock; directories of a node's own
    carry their own ids and reconcile at once."""
    if target != 'postgresql':
        pytest.skip('the advisory lock is PostgreSQL\'s')
    from sqlalchemy import text
    from config.settings import Config
    from services import file_regen_service as regen
    from utils import ha
    monkeypatch.setattr(ha, 'ha_enabled', lambda: True)
    dirs = [regen._Dir(path) for path in regen.managed_dirs()]
    for directory in dirs:
        directory.open()
    keys = regen.advisory_keys(dirs)
    for directory in dirs:
        directory.close()
    other_node = db.engine.connect().execution_options(isolation_level='AUTOCOMMIT')
    try:
        for key in keys:
            other_node.execute(text('SELECT pg_advisory_lock(:k)'), {'k': key})
        assert regen.reconcile_files(full=True) == {'status': 'busy'}
        for name in ('CA_DIR', 'CERT_DIR', 'PRIVATE_DIR'):
            monkeypatch.setattr(Config, name, Path(tmp_path / 'own' / name.lower()))
        assert regen.reconcile_files(full=True)['status'] == 'done'
    finally:
        other_node.close()
    assert regen.reconcile_files(full=True)['status'] == 'done'


def test_in_ha_a_pass_asked_to_wait_takes_the_lock_once_released(target, monkeypatch):
    if target != 'postgresql':
        pytest.skip('the advisory lock is PostgreSQL\'s')
    import threading
    from sqlalchemy import text
    from services import file_regen_service as regen
    from utils import ha
    monkeypatch.setattr(ha, 'ha_enabled', lambda: True)
    dirs = [regen._Dir(path) for path in regen.managed_dirs()]
    for directory in dirs:
        directory.open()
    keys = regen.advisory_keys(dirs)
    for directory in dirs:
        directory.close()
    other_node = db.engine.connect().execution_options(isolation_level='AUTOCOMMIT')
    try:
        # One key only: the pass holds the others while it waits for this one
        other_node.execute(text('SELECT pg_advisory_lock(:k)'), {'k': keys[-1]})
        assert regen.reconcile_files(full=True, wait=0.2) == {'status': 'busy'}
        threading.Timer(0.3, other_node.close).start()
        assert regen.reconcile_files(full=True, wait=5)['status'] == 'done'
    finally:
        other_node.close()
