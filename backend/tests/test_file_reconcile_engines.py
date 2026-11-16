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
    from services.file_regen_service import listed_path
    gone = listed_path(ca_cert_path(removed))
    before = _generation()

    results = _service().restore_backup(blob, PASSWORD, mode='replace')

    after = _generation()
    from services.file_regen_service import generation_number
    assert generation_number(after) == generation_number(before) + 1
    listed = {row.path for row in FileRemoval.query.filter_by(
        generation=generation_number(after))}
    assert gone in listed and listed_path(ca_cert_path(kept)) not in listed
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
        # Released by the other node 0.3 s into a pass that waits for it
        threading.Timer(0.3, lambda: other_node.execute(
            text('SELECT pg_advisory_unlock(:k)'), {'k': keys[-1]})).start()
        assert regen.reconcile_files(full=True, wait=5)['status'] == 'done'
    finally:
        other_node.close()


def test_a_pass_striking_with_a_restore_never_deadlocks_the_restore(target, app, monkeypatch):
    """A restore strikes listed rows and holds them to its commit; a pass striking the same
    rows takes each without waiting, in id order, and commits each batch: no lock cycle."""
    if target != 'postgresql':
        pytest.skip('row locks and their deadlocks are PostgreSQL\'s')
    import threading
    from sqlalchemy import event, text
    from services import file_regen_service as regen
    first = _authority_row(f'strike-a-{uuid.uuid4().hex[:8]}')[0]
    second = _authority_row(f'strike-b-{uuid.uuid4().hex[:8]}')[0]
    paths = [regen.listed_path(ca_cert_path(first)), regen.listed_path(ca_cert_path(second))]
    db.session.add_all([FileRemoval(generation=1, path=p) for p in paths])
    db.session.commit()
    monkeypatch.setattr(regen, 'PAGE_SIZE', 1)   # one path per batch

    restore = db.engine.connect()
    restore_txn = restore.begin()
    restore.execute(text('DELETE FROM file_removals WHERE path = :p'), {'p': paths[1]})

    first_batch, go_on, outcome = threading.Event(), threading.Event(), {}

    def after(conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith('DELETE FROM FILE_REMOVALS') \
                and not first_batch.is_set():
            first_batch.set()
            go_on.wait(10)

    def node_pass():
        with app.app_context():
            event.listen(db.engine, 'after_cursor_execute', after)
            try:
                outcome['pass'] = regen.reconcile_files(full=True)['status']
            except Exception as exc:  # noqa: BLE001 (the outcome is asserted below)
                outcome['pass'] = exc
            finally:
                event.remove(db.engine, 'after_cursor_execute', after)
                db.session.remove()

    def restore_strikes_the_first():
        try:
            restore.execute(text('DELETE FROM file_removals WHERE path = :p'), {'p': paths[0]})
            restore_txn.commit()
            outcome['restore'] = 'committed'
        except Exception as exc:  # noqa: BLE001
            restore_txn.rollback()
            outcome['restore'] = exc

    passing = threading.Thread(target=node_pass)
    passing.start()
    try:
        assert first_batch.wait(10)
        # The restore now waits on the pass's first batch, as a restore's strike would
        striking = threading.Thread(target=restore_strikes_the_first)
        striking.start()
        import time
        time.sleep(0.5)
        go_on.set()
        striking.join(30)
        passing.join(30)
    finally:
        go_on.set()
        restore.close()
    assert outcome['restore'] == 'committed', outcome
    assert outcome['pass'] in ('busy', 'done'), outcome
