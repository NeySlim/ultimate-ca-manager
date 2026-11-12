"""DEK rotation: a new DEK, every stored value rewritten under it in batches, the old one dropped.

Until the end both DEKs stay in encryption_keys (old 'previous', new 'active'), so an
interruption at any point leaves every value readable; running it again resumes.
"""
import importlib
import json
import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import text

from security import envelope
from security import encryption as _encryption

logger = logging.getLogger(__name__)

BATCH = 200
# HA: how long the rotation waits for the live nodes to load the new DEK before rewriting
ACK_TIMEOUT_SECONDS = 30.0
_LOCK = 0x75636D64656B  # PostgreSQL advisory lock id for DEK state changes
DISABLED_MARKER_VERSION = 0
# The previous DEK opens values for this long after the last sweep: a write encrypted under
# it before its process re-read the rows (REFRESH_SECONDS) commits within it and stays readable
GRACE_SECONDS = 600.0
# system_config: {"version", "until", "command"}, plus {"disable": true, "remove_file"} after
# a disable, whose DEKs are kept for reading the same way
GRACE_KEY = 'encryption.dek_retire_after'


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
    """A previous DEK is still in the database: being rewritten, or in its grace period."""
    from models import EncryptionKey
    return EncryptionKey.query.filter_by(state=envelope.PREVIOUS).first() is not None


def retiring():
    """The grace period of the previous DEK (or of a disable's DEKs), as stored, or None."""
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=GRACE_KEY).first()
    if row is None or not row.value:
        return None
    grace = json.loads(row.value)
    grace['until'] = datetime.fromisoformat(grace['until'])
    return grace


def disable_grace():
    """The grace period of a disable done (its DEKs kept for reading only), or None."""
    grace = retiring()
    return grace if grace and grace.get('disable') else None


def shown_as_enabled() -> bool:
    """Encryption as the status, the dashboard and the preflight report it: on while new values
    are encrypted or a disable is left half-way, off once a disable is done (grace included)."""
    key_encryption = _encryption.key_encryption
    return key_encryption.is_encrypting or (key_encryption.is_enabled and disable_grace() is None)


def _set_grace(version, command_id, **extra) -> datetime:
    from models import db, SystemConfig
    from services.scheduler_leader import cluster_utc_now
    until = cluster_utc_now() + timedelta(seconds=GRACE_SECONDS)
    value = json.dumps({'version': version, 'until': until.isoformat(), 'command': command_id,
                        **extra})
    row = SystemConfig.query.filter_by(key=GRACE_KEY).first()
    if row is None:
        db.session.add(SystemConfig(key=GRACE_KEY, value=value,
                                    description='Previous data-encryption key kept until'))
    else:
        row.value = value
    return until


def _clear_grace() -> None:
    from models import SystemConfig
    SystemConfig.query.filter_by(key=GRACE_KEY).delete(synchronize_session=False)


def grace_refusal(grace) -> str:
    """Why an enable, rotation or disable waits for the end of ``grace``."""
    until = grace['until'].isoformat(timespec='seconds')
    if grace.get('disable'):
        # A rotation is refused afterwards as well (nothing to rotate): only enabling goes on
        return (f"Encryption was disabled: its data-encryption keys are kept until {until} UTC "
                f"for values written during the disable; enable it again after that.")
    return f"The previous data-encryption key is kept until {until} UTC: rotate again after that"


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
        if key_encryption.is_enabled:
            raise RotationError('A disable of encryption was left half-way: run Disable '
                                'Encryption again to finish it.')
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
    from models import db, ClusterNode
    from services.scheduler_leader import STALE_PASSES, cluster_utc_now
    from services.scheduler_service import WAKE_INTERVAL_SECONDS
    deadline = time.monotonic() + (ACK_TIMEOUT_SECONDS if timeout is None else timeout)
    stale = STALE_PASSES * WAKE_INTERVAL_SECONDS
    while True:
        db.session.commit()  # a fresh snapshot on every poll
        now = cluster_utc_now()
        rows = db.session.query(ClusterNode.node_id, ClusterNode.heartbeat_at,
                                ClusterNode.command_seen).filter(
            ClusterNode.node_id != Config.NODE_ID).all()
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


def rewrite(batch=None, commit=True, decrypt=False) -> dict:
    """Every value not yet under the active DEK, rewritten under it; one commit per batch.
    ``decrypt``: every encrypted value stored in the clear instead (a disable's last sweep).

    The UPDATE matches the value read, so a write committed meanwhile is never overwritten
    (made with the active DEK, or taken by the next pass).
    """
    from models import db, SystemConfig
    batch = batch or BATCH
    key_encryption = _encryption.key_encryption
    rewritten = skipped = 0
    unreadable, changed = [], []
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
                if not key_encryption.is_encrypted(value) or (not decrypt and _under_active(value)):
                    skipped += 1
                    continue
                try:
                    plain = _encryption.decrypt_master_key_value(value, fmt)
                except ValueError:
                    unreadable.append(f"{model.__name__} {row_id}")
                    continue
                new_value = plain if decrypt else _encryption.encrypt_master_key_value(plain, fmt)
                result = db.session.execute(
                    table.update().where(pk == row_id).where(stored_column == stored)
                    .values({stored_column.name: wrap(new_value) if wrap else new_value}))
                rewritten += result.rowcount
                if result.rowcount:
                    changed.append((model, row_id))
            if commit:
                db.session.commit()
    return {'rewritten': rewritten, 'skipped': skipped, 'unreadable': unreadable,
            'changed': changed}


def _mirror_keys(changed) -> None:
    """The plaintext .key mirrors of the CA and certificate keys a disable's sweep decrypted."""
    from models import db, CA, Certificate
    from services.file_regen_service import write_ca_files, write_cert_files
    for model, row_id in changed:
        write = {CA: write_ca_files, Certificate: write_cert_files}.get(model)
        row = db.session.get(model, row_id) if write else None
        if row is not None:
            write(row)


def _final_sweep() -> None:
    """Under the lock, in the caller's transaction; raises while a value opens with no DEK."""
    from models import db
    unreadable = rewrite(commit=False)['unreadable']
    if unreadable:
        # Dropping a DEK could lose what only it opens: the rotation stays resumable
        db.session.commit()
        raise RotationError(f"{len(unreadable)} value(s) decrypt with no data-encryption key, "
                            f"the previous key is kept: {', '.join(unreadable[:5])}")


def finish(command=None):
    """Last pass, then the previous DEKs enter their grace period; returns its end."""
    from models import db
    rewrite()
    lock_key_state()
    _final_sweep()
    until = _set_grace(_encryption.key_encryption.active_version,
                       getattr(command, 'id', None))
    db.session.commit()
    return until


def retire_if_due() -> int:
    """Drop the previous DEKs (after a disable, every DEK) once their grace is over, every live
    node has applied the change and a sweep finds no value left under them; returns how many
    were dropped."""
    from types import SimpleNamespace
    from models import db, EncryptionKey
    from services.scheduler_leader import cluster_utc_now
    grace = retiring()
    if grace is None or cluster_utc_now() < grace['until']:
        return 0
    lagging = wait_for_nodes(SimpleNamespace(id=grace['command']), timeout=0)
    if lagging:
        logger.warning("Previous DEK kept: node(s) %s have not loaded DEK version %s",
                       ', '.join(lagging), grace['version'])
        return 0
    lock_key_state()
    _encryption.key_encryption.refresh()
    # Read again under the lock: another node may have ended it and started a new rotation
    if retiring() != grace:
        db.session.commit()
        return 0
    disable = bool(grace.get('disable'))
    # A disable's DEKs are the only ones: values found under them go back in the clear
    late = rewrite(commit=False, decrypt=disable)
    if late['unreadable']:
        db.session.commit()
        kept = 'the keys of the disable are kept' if disable else 'the previous key is kept'
        raise RotationError(f"{len(late['unreadable'])} value(s) decrypt with no data-encryption "
                            f"key, {kept}: {', '.join(late['unreadable'][:5])}")
    extra = {k: grace[k] for k in ('disable', 'remove_file') if k in grace}
    if late['rewritten']:
        # Something still wrote under the DEK: it stays for another grace period
        _set_grace(grace['version'], grace['command'], **extra)
        db.session.commit()
        if disable:
            _mirror_keys(late['changed'])
        logger.warning("Previous DEK kept: %d value(s) were written under it since the "
                       "%s", late['rewritten'], 'disable' if disable else 'rotation')
        return 0
    states = (envelope.ACTIVE, envelope.PREVIOUS) if disable else (envelope.PREVIOUS,)
    dropped = EncryptionKey.query.filter(EncryptionKey.state.in_(states)).all()
    for row in dropped:
        db.session.delete(row)
    _clear_grace()
    _emit_reload(None if disable else _encryption.key_encryption.active_version)
    db.session.commit()
    if disable and grace.get('remove_file'):
        # Outside HA the file's KEK wrapped the DEKs just dropped: nothing needs it any more
        _encryption.KeyEncryption.remove_key_file()
    _encryption.key_encryption.reload()
    return len(dropped)


def scheduled_retire() -> None:
    """Scheduler task (the leader in HA): ends a grace period that is over."""
    from models import db
    if retiring() is None:
        return
    try:
        dropped = retire_if_due()
    except RotationError as e:
        logger.error("🔑 %s", e)  # the message already says the key is kept
        return
    except Exception:
        db.session.rollback()
        raise
    if dropped:
        logger.info("🔑 Previous data-encryption key dropped after its grace period")


def rotate(wait_timeout=None) -> dict:
    """Start (or resume) a rotation and carry it to the end; 'in_progress' when nodes lag.

    A rotation still in its grace period is retired first when it is due, else refused.
    """
    if retiring() is not None:
        retire_if_due()
        grace = retiring()
        if grace is not None:
            raise RotationError(grace_refusal(grace))
    version, command = start()
    # No value is rewritten under the new DEK before every process can open it
    settle()
    lagging = wait_for_nodes(command, wait_timeout)
    if lagging:
        logger.warning("DEK rotation to version %s waits for node(s) %s to load it; run it "
                       "again to resume", version, ', '.join(lagging))
        return {'state': 'in_progress', 'version': version, 'waiting_for': lagging}
    stats = rewrite()
    until = finish(command)
    dropped = retire_if_due()
    logger.info("🔑 DEK rotated to version %s: %d values rewritten, %d previous key(s) dropped",
                version, stats['rewritten'], dropped)
    return {'state': 'done', 'version': version, 'rewritten': stats['rewritten'],
            'dropped': dropped,
            'retire_after': None if dropped else until.isoformat(timespec='seconds')}


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
        grace = retiring()
        db.session.rollback()
        if grace is not None:
            raise RotationError(f"The previous data-encryption key of the last rotation is kept "
                                f"until {grace['until'].isoformat(timespec='seconds')} UTC: "
                                f"disable after that.")
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


def finish_disable(kept_kek, remove_file=False):
    """Phase 2, under the lock once no stored value is encrypted: the disabled markers, and the
    DEKs kept for reading through a grace period (a value encrypted before its process saw
    phase 1 may commit after this). Committed; returns the end of the grace.

    ``kept_kek``: fingerprint of the KEK that stays configured, marked unused, or None.
    ``remove_file``: master.key is removed with the DEKs at the end of the grace.
    """
    from models import db, EncryptionKey
    from utils.datetime_utils import utc_now
    lock_key_state()
    if _encryption.has_encrypted_keys_in_db():
        db.session.rollback()
        raise RotationError('A value was encrypted while encryption was being disabled: run '
                            'the disable again, the data-encryption keys are kept.')
    rows = EncryptionKey.query.all()
    for row in rows:
        if row.state == envelope.DISABLED:
            db.session.delete(row)
    db.session.flush()
    kept = [r.version for r in rows if r.state in (envelope.ACTIVE, envelope.PREVIOUS)]
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
    command = _emit_reload(None)
    db.session.flush()  # the command's id, which every live node acknowledges
    until = _set_grace(max(kept, default=None), getattr(command, 'id', None), disable=True,
                       remove_file=bool(remove_file))
    db.session.commit()
    return until


def resume_at_start() -> None:
    """Outside HA, a rotation an earlier process left unfinished ends at the next start."""
    from utils.ha import ha_enabled
    if ha_enabled() or not _encryption.key_encryption.is_enabled:
        return
    try:
        if retiring() is not None:
            retire_if_due()  # restarted during the grace period: the scheduler ends it otherwise
            return
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
