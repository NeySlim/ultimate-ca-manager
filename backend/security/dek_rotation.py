"""DEK rotation: a new DEK, every stored value rewritten under it in batches, the old one dropped.

Until the end both DEKs stay in encryption_keys (old 'previous', new 'active'), so an
interruption at any point leaves every value readable; running it again resumes.
"""
import importlib
import logging
import time

from sqlalchemy import text

from security import envelope
from security import encryption as _encryption

logger = logging.getLogger(__name__)

BATCH = 200
# HA: how long the rotation waits for the live nodes to load the new DEK before rewriting
ACK_TIMEOUT_SECONDS = 30.0
_LOCK = 0x75636D64656B  # PostgreSQL advisory lock id for DEK state changes
DISABLED_MARKER_VERSION = 0


class RotationError(RuntimeError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def lock_key_state(session=None) -> None:
    """Serialise enable, disable and rotation across nodes (PostgreSQL; SQLite has one writer)."""
    from models import db
    session = session or db.session
    if session.get_bind().dialect.name == 'postgresql':
        session.execute(text('SELECT pg_advisory_xact_lock(:k)'), {'k': _LOCK})


def rotation_in_progress() -> bool:
    from models import EncryptionKey
    return EncryptionKey.query.filter_by(state=envelope.PREVIOUS).first() is not None


def _emit_reload(version):
    from services.cluster_commands import RELOAD_ENCRYPTION, emit
    return emit(RELOAD_ENCRYPTION, {'version': version})


def start():
    """New active DEK, the current one kept as 'previous'; resumes one already started.

    Returns (active version, cluster command or None). Committed.
    """
    from models import db, EncryptionKey
    from utils.datetime_utils import utc_now
    key_encryption = _encryption.key_encryption
    lock_key_state()
    # Checked under the lock: a disable committed meanwhile is never undone here
    key_encryption.refresh()
    if not key_encryption.is_encrypting:
        db.session.rollback()
        raise RotationError('Encryption is not enabled', 400)
    rows = EncryptionKey.query.order_by(EncryptionKey.version).all()
    keys = [r for r in rows if r.state in (envelope.ACTIVE, envelope.PREVIOUS)]
    if any(r.state == envelope.PREVIOUS for r in keys):
        version = max(r.version for r in keys if r.state == envelope.ACTIVE)
        command = _emit_reload(version)
        db.session.commit()
        key_encryption.reload()
        return version, command
    kek = key_encryption.kek_bytes_for_envelope()
    mine = envelope.kek_id(kek)
    for row in rows:
        if row.state == envelope.DISABLED:
            db.session.delete(row)
    now = utc_now()
    if not keys:
        # The KEK material was DEK version 1: recorded so that it stays until the end
        db.session.add(EncryptionKey(version=1, state=envelope.PREVIOUS, kek_id=mine,
                                     wrapped=None, created_at=now))
        version = 2
    else:
        for row in keys:
            row.state = envelope.PREVIOUS
        version = max(r.version for r in keys) + 1
    db.session.add(EncryptionKey(version=version, state=envelope.ACTIVE, kek_id=mine,
                                 wrapped=envelope.wrap(kek, version, envelope.new_dek()),
                                 created_at=now))
    command = _emit_reload(version)
    db.session.commit()
    key_encryption.reload()
    if key_encryption.active_version != version:
        raise RotationError('The new data-encryption key did not load')
    return version, command


def settle() -> None:
    """Return once every process, on any node, re-reads the DEK rows before its next key use.

    A process re-reads them when its last read is REFRESH_SECONDS old: twice that leaves a margin.
    """
    delay = 2 * _encryption.REFRESH_SECONDS
    if delay > 0:
        time.sleep(delay)


def wait_for_nodes(command, timeout=None) -> list:
    """HA: the live nodes that have not applied ``command`` after ``timeout`` (empty: all did)."""
    if command is None or command.id is None:
        return []
    from config.settings import Config
    from models import db
    from services.scheduler_leader import STALE_PASSES, cluster_utc_now
    from services.scheduler_service import WAKE_INTERVAL_SECONDS
    deadline = time.monotonic() + (ACK_TIMEOUT_SECONDS if timeout is None else timeout)
    stale = STALE_PASSES * WAKE_INTERVAL_SECONDS
    while True:
        db.session.commit()  # a fresh snapshot on every poll
        now = cluster_utc_now()
        rows = db.session.execute(text(
            "SELECT node_id, heartbeat_at, command_seen FROM cluster_nodes WHERE node_id <> :me"),
            {'me': Config.NODE_ID}).fetchall()
        pending = sorted(r.node_id for r in rows
                         if (now - r.heartbeat_at).total_seconds() <= stale
                         and (r.command_seen or 0) < command.id)
        if not pending or time.monotonic() >= deadline:
            return pending
        time.sleep(0.5)


def _columns():
    """(model, stored column, format, unwrap, wrap) for every value under the DEK.

    SSOProvider's property hides a database-layer wrapping: its stored column is rewritten
    through that layer so the outer encryption stays as it was.
    """
    from sqlalchemy.orm.attributes import InstrumentedAttribute
    from models import SystemConfig
    from utils.encryption import decrypt_if_needed, encrypt_if_needed
    for module, name, attribute, fmt in _encryption.MASTER_KEY_COLUMNS:
        model = getattr(importlib.import_module(module), name)
        column = getattr(model, attribute)
        if isinstance(column, InstrumentedAttribute):
            yield model, column, fmt, None, None
        else:
            yield model, getattr(model, '_' + attribute), fmt, decrypt_if_needed, encrypt_if_needed
    yield SystemConfig, SystemConfig.value, 'text', None, None


def _under_active(value: str) -> bool:
    import base64
    token = base64.b64decode(value)[len(_encryption.ENCRYPTED_MARKER):]
    try:
        _encryption.key_encryption._fernet.decrypt(token)
        return True
    except Exception:
        return False


def rewrite(batch=None, commit=True) -> dict:
    """Every value not yet under the active DEK, rewritten under it; one commit per batch.

    The UPDATE matches the value read, so a write committed meanwhile is never overwritten
    (made with the active DEK, or taken by the next pass).
    """
    from models import db, SystemConfig
    batch = batch or BATCH
    key_encryption = _encryption.key_encryption
    rewritten = skipped = 0
    unreadable = []
    for model, column, fmt, unwrap, wrap in _columns():
        table = model.__table__
        # SharedFile is keyed by its name: the primary key, not an id column
        pk, stored_column = list(table.primary_key.columns)[0], column.property.columns[0]
        config = model is SystemConfig
        last = None
        while True:
            query = db.session.query(pk, stored_column, table.c.key if config else pk) \
                .filter(stored_column.isnot(None), stored_column != '')
            if config:
                query = query.filter(table.c.key.like('acme.%'))
            if last is not None:
                query = query.filter(pk > last)
            chunk = query.order_by(pk).limit(batch).all()
            if not chunk:
                break
            for row_id, stored, config_key in chunk:
                last = row_id
                if config and not _encryption._is_master_key_config(config_key):
                    continue
                value = unwrap(stored) if unwrap else stored
                if not key_encryption.is_encrypted(value) or _under_active(value):
                    skipped += 1
                    continue
                try:
                    plain = _encryption.decrypt_master_key_value(value, fmt)
                except ValueError:
                    unreadable.append(f"{model.__name__} {row_id}")
                    continue
                new_value = _encryption.encrypt_master_key_value(plain, fmt)
                result = db.session.execute(
                    table.update().where(pk == row_id).where(stored_column == stored)
                    .values({stored_column.name: wrap(new_value) if wrap else new_value}))
                rewritten += result.rowcount
            if commit:
                db.session.commit()
    return {'rewritten': rewritten, 'skipped': skipped, 'unreadable': unreadable}


def finish() -> int:
    """Last pass, then the previous DEKs are dropped; returns how many were."""
    from models import db, EncryptionKey
    rewrite()
    lock_key_state()
    # The final sweep and the drop share one transaction: the window for a late write is its length
    unreadable = rewrite(commit=False)['unreadable']
    if unreadable:
        # Dropping a DEK could lose what only it opens: the rotation stays resumable
        db.session.commit()
        raise RotationError(f"{len(unreadable)} value(s) decrypt with no data-encryption key, "
                            f"the previous key is kept: {', '.join(unreadable[:5])}")
    previous = EncryptionKey.query.filter_by(state=envelope.PREVIOUS).all()
    for row in previous:
        db.session.delete(row)
    _emit_reload(_encryption.key_encryption.active_version)
    db.session.commit()
    _encryption.key_encryption.reload()
    return len(previous)


def rotate(wait_timeout=None) -> dict:
    """Start (or resume) a rotation and carry it to the end; 'in_progress' when nodes lag."""
    version, command = start()
    # No value is rewritten under the new DEK before every process can open it
    settle()
    lagging = wait_for_nodes(command, wait_timeout)
    if lagging:
        logger.warning("DEK rotation to version %s waits for node(s) %s to load it; run it "
                       "again to resume", version, ', '.join(lagging))
        return {'state': 'in_progress', 'version': version, 'waiting_for': lagging}
    stats = rewrite()
    dropped = finish()
    logger.info("🔑 DEK rotated to version %s: %d values rewritten, %d previous key(s) dropped",
                version, stats['rewritten'], dropped)
    return {'state': 'done', 'version': version, 'rewritten': stats['rewritten'],
            'dropped': dropped}


def begin_disable():
    """Phase 1 of a disable: every DEK kept for reading, none encrypts any more. Committed.

    Returns the cluster command. Run again, it resumes a disable left half-way.
    """
    from models import db, EncryptionKey
    from utils.datetime_utils import utc_now
    key_encryption = _encryption.key_encryption
    lock_key_state()
    key_encryption.refresh()
    if not key_encryption.is_enabled:
        db.session.rollback()
        raise RotationError('Encryption is not enabled', 400)
    if rotation_in_progress():
        db.session.rollback()
        raise RotationError('A data-encryption key rotation is in progress: finish it first.')
    mine = envelope.kek_id(key_encryption.kek_bytes_for_envelope())
    rows = EncryptionKey.query.all()
    now = utc_now()
    if not any(r.state in (envelope.ACTIVE, envelope.PREVIOUS) for r in rows):
        # The KEK material is DEK version 1: recorded, or the marker alone would read as off
        db.session.add(EncryptionKey(version=1, state=envelope.ACTIVE, kek_id=mine,
                                     wrapped=None, created_at=now))
    marker = next((r for r in rows if r.state == envelope.DISABLED), None)
    if marker is None:
        db.session.add(EncryptionKey(version=DISABLED_MARKER_VERSION, state=envelope.DISABLED,
                                     kek_id=mine, wrapped=None, created_at=now))
    else:
        marker.kek_id = mine
    command = _emit_reload(None)
    db.session.commit()
    key_encryption.reload()
    return command


def finish_disable(kept_kek) -> None:
    """Phase 2: the DEKs dropped once, under the lock, no stored value is encrypted. Committed.

    ``kept_kek``: fingerprint of the KEK that stays configured, marked unused, or None.
    """
    from models import db, EncryptionKey
    from utils.datetime_utils import utc_now
    lock_key_state()
    if _encryption.has_encrypted_keys_in_db():
        db.session.rollback()
        raise RotationError('A value was encrypted while encryption was being disabled: run '
                            'the disable again, the data-encryption keys are kept.')
    EncryptionKey.query.delete()
    # The KEK being removed is marked too: a process still holding it (no command outside
    # HA) must read "off", not "no row, the KEK is DEK v1"
    marked = [kept_kek, _encryption.key_encryption.kek_fingerprint()]
    for offset, kek in enumerate(dict.fromkeys(k for k in marked if k)):
        db.session.add(EncryptionKey(
            version=DISABLED_MARKER_VERSION - offset, state=envelope.DISABLED,
            kek_id=kek, wrapped=None, created_at=utc_now()))
    # Nothing is encrypted any more: without this the next start would create a key
    from security.master_key_bootstrap import record_operator_choice
    record_operator_choice(auto=False)
    _emit_reload(None)
    db.session.commit()


def resume_at_start() -> None:
    """Outside HA, a rotation an earlier process left unfinished ends at the next start."""
    from utils.ha import ha_enabled
    if ha_enabled() or not _encryption.key_encryption.is_enabled:
        return
    try:
        if not rotation_in_progress():
            return
        result = rotate()
    except Exception as e:
        from models import db
        db.session.rollback()
        logger.error("🔑 Unfinished DEK rotation not resumed: %s: %s", type(e).__name__, e)
        return
    from services.audit_service import AuditService
    AuditService.log_action(
        action='encryption_key_rotated', resource_type='system',
        resource_name='Data Encryption Key',
        details=(f"Interrupted rotation resumed at start: DEK version {result['version']}, "
                 f"{result.get('rewritten', 0)} values rewritten"),
        success=result['state'] == 'done')
