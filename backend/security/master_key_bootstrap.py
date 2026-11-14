"""Master key at first start, so a new installation stores no private key in the clear.

A key is created only where none was ever configured and nothing in the database
is encrypted: a missing key beside encrypted rows is a lost key (safe mode).
"""
import logging
import os
import re
from pathlib import Path

from security import encryption as _encryption

logger = logging.getLogger(__name__)

# Docker and Podman name an anonymous volume after 64 hex digits
_ANONYMOUS_VOLUME = re.compile(r'/volumes/[0-9a-f]{64}/_data/?$')
_MEMORY_FILESYSTEMS = {'tmpfs', 'ramfs'}


def in_container() -> bool:
    return (os.getenv('UCM_DOCKER') == '1' or os.path.exists('/.dockerenv')
            or os.path.exists('/run/.containerenv'))


def _read_mountinfo() -> str:
    return Path('/proc/self/mountinfo').read_text()


def _unescape(field: str) -> str:
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), field)


def container_dir_is_persistent(directory, mountinfo: str = None):
    """(persistent, reason) for `directory` in a container: it must be a volume of
    its own that outlives the container, not an anonymous volume, memory or an emptyDir."""
    target = str(directory).rstrip('/') or '/'
    if mountinfo is None:
        try:
            mountinfo = _read_mountinfo()
        except OSError as e:
            return False, f'the mount table is unreadable ({e})'
    found = None
    for line in mountinfo.splitlines():
        left, sep, right = line.partition(' - ')
        fields = left.split()
        if not sep or len(fields) < 5:
            continue
        root, point = _unescape(fields[3]), _unescape(fields[4])
        if target == point or target.startswith(point.rstrip('/') + '/'):
            # The longest mount point holds the path; the last mounted one wins
            if found is None or len(point) >= len(found[1]):
                found = (root, point, (right.split() or [''])[0])
    if found is None or found[1] != target:
        return False, f'{target} is not a volume of its own'
    root, _, fstype = found
    if fstype in _MEMORY_FILESYSTEMS:
        return False, f'{target} is held in memory ({fstype})'
    if _ANONYMOUS_VOLUME.search(root):
        return False, f'{target} is an anonymous volume'
    if 'kubernetes.io~empty-dir' in root:
        return False, f'{target} is an emptyDir volume'
    return True, ''


def ephemeral_key_dir_refusal():
    """Why a key written now would be lost with the container, or None."""
    if not in_container():
        return None
    directory = _encryption.MASTER_KEY_PATH.parent
    persistent, reason = container_dir_is_persistent(directory)
    if persistent:
        return None
    return (f"{reason}, so a master key there would be lost with the container. Mount "
            f"{directory} on a named volume or a host directory, or set KEY_ENCRYPTION_KEY")


# 'false' once encryption is disabled from the UI, so a later start creates no key
OPT_OUT_KEY = 'security.auto_master_key'


def _disabled_in_audit_log() -> bool:
    from models import AuditLog
    latest = (AuditLog.query
              .filter(AuditLog.action.in_(('encryption_enabled', 'encryption_disabled')))
              .order_by(AuditLog.id.desc()).first())
    return latest is not None and latest.action == 'encryption_disabled'


def auto_master_key_allowed(app) -> bool:
    if not app.config.get('AUTO_MASTER_KEY'):
        return False
    from models import db, SystemConfig
    row = SystemConfig.query.filter_by(key=OPT_OUT_KEY).first()
    if row:
        return row.value != 'false'
    # Versions without the row recorded a disable in the audit log only. Read it once:
    # audit entries a restore appends later come from another installation.
    allowed = not _disabled_in_audit_log()
    record_operator_choice(auto=allowed)
    db.session.commit()
    return allowed


def record_operator_choice(auto: bool) -> None:
    """Stage the operator's choice from enable/disable encryption; the caller commits."""
    from models import db, SystemConfig
    value = 'true' if auto else 'false'
    row = SystemConfig.query.filter_by(key=OPT_OUT_KEY).first()
    if row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=OPT_OUT_KEY, value=value,
                                    description='Master key created automatically when true'))


def _master_key_was_used() -> bool:
    """Something in the database or beside the key was made with a master key now missing."""
    if _encryption.has_encrypted_keys_in_db():
        return True
    from models import AuditLog
    from services.audit.chain import KEYED_CHAIN, keyring_path
    if keyring_path().exists():
        return True
    return AuditLog.query.filter(AuditLog.hash_version == KEYED_CHAIN).first() is not None


class KeyActivationError(RuntimeError):
    """The new key file was written but does not load; it has been removed."""


def activate_new_master_key(exclusive: bool) -> dict:
    """Write a new master key, load it, encrypt what is stored without it.

    The key file is removed only when it failed to load: once a value is
    encrypted under it, removing it would lose that value.
    """
    from models import db, EncryptionKey
    from security import envelope
    from security.dek_rotation import lock_key_state
    KeyEncryption = _encryption.KeyEncryption
    key_encryption = _encryption.key_encryption
    # A disabled marker keeps any KEK off: enabling is what lifts it, and puts it back on failure
    lock_key_state()
    columns = ('version', 'state', 'kek_id', 'wrapped', 'created_at', 'retire_after')
    markers = [{c: getattr(r, c) for c in columns}
               for r in EncryptionKey.query.filter_by(state=envelope.DISABLED)]
    EncryptionKey.query.filter_by(state=envelope.DISABLED).delete(synchronize_session=False)
    db.session.commit()
    try:
        KeyEncryption.write_key_file(KeyEncryption.generate_key(), exclusive=exclusive)
        key_encryption.reload()
        if not key_encryption.is_enabled:
            KeyEncryption.remove_key_file()
            raise KeyActivationError('Failed to initialize encryption after key generation')
    except BaseException:
        db.session.rollback()
        try:
            lock_key_state()
            for marker in markers:
                if db.session.get(EncryptionKey, marker['version']) is None:
                    db.session.add(EncryptionKey(**marker))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error("🔓 Disabled-encryption markers not put back: %s", e)
        raise

    encrypted, skipped, errors = _encryption.encrypt_all_keys(dry_run=False)
    return {'encrypted': encrypted, 'skipped': skipped, 'errors': errors,
            'purge': purge_plaintext_key_files()}


def purge_plaintext_key_files() -> dict:
    """The plaintext .key mirrors removed once the database is encrypted; never raises."""
    from services.file_regen_service import purge_private_key_files
    try:
        return purge_private_key_files()
    except Exception as e:
        # The key now encrypts the database: a failed cleanup must not hide it
        logger.error("🔓 Could not remove the plaintext key copies: %s", e)
        return {'removed': 0, 'kept_no_db_key': 0, 'errors': 1}


def _log_remaining(errors: list) -> None:
    if errors:
        logger.error("🔓 %d value(s) still stored unencrypted under the master key, retried at "
                     "the next start: %s", len(errors), '; '.join(errors[:5]))


def _loaded_key_reads_the_database() -> bool:
    """False when the first encrypted value does not decrypt: the key is another one."""
    for _, row, attribute, fmt in _encryption.master_key_values():
        value = getattr(row, attribute)
        if _encryption.key_encryption.is_encrypted(value):
            try:
                _encryption.decrypt_master_key_value(value, fmt)
            except ValueError:
                return False
            return True
    return True


def _resume_encryption() -> None:
    """Encrypt what an interrupted first encryption left in the clear."""
    try:
        if not _encryption.has_unencrypted_master_key_values():
            return
        encrypted, _, errors = _encryption.encrypt_all_keys(dry_run=False)
    except Exception as e:
        from models import db
        db.session.rollback()
        logger.error("🔓 Could not encrypt the values still stored unencrypted: %s", e)
        return
    logger.warning("🔑 %d keys and secrets left unencrypted by an earlier start are now encrypted",
                   encrypted)
    _log_remaining(errors)


def bootstrap_master_key(app) -> str:
    """Create the master key when the installation never had one; returns what was done."""
    key_encryption = _encryption.key_encryption
    path = _encryption.MASTER_KEY_PATH
    if key_encryption.dek_error:
        # The stored DEKs are wrapped by another KEK: nothing is written under this one
        key_encryption.refuse_kek('wrong_key')
        return 'wrong_key'
    if _marker_is_foreign_in_ha(key_encryption):
        # Disabled under another KEK: an enable from here, or a peer's (no marker left, the KEK
        # read as DEK version 1), would encrypt under a KEK the other nodes do not hold, so this
        # process writes nothing until it restarts with the cluster's KEK
        key_encryption.refuse_kek('foreign_disable')
        return 'foreign_disable'
    if key_encryption.is_enabled:
        if not _loaded_key_reads_the_database():
            # Running on would write new values under the wrong key: keep them as without one
            key_encryption.refuse_kek('wrong_key')
            return 'wrong_key'
        # A disable in progress encrypts nothing: there is nothing to resume
        if key_encryption.is_encrypting and auto_master_key_allowed(app):
            _resume_encryption()
        return 'present'
    if not auto_master_key_allowed(app):
        return 'disabled'
    # A key that exists but does not load is reported, never replaced
    if path.exists() or os.getenv('KEY_ENCRYPTION_KEY'):
        # It may have been written by another process since the start reload
        key_encryption.reload()
        return 'present' if key_encryption.is_enabled else 'configured'
    if _master_key_was_used():
        logger.error(
            "🔓 No master key created: encrypted values or a keyed audit chain need the "
            "previous one. Restore %s and restart UCM.", path)
        return 'lost'
    refusal = ephemeral_key_dir_refusal()
    if refusal:
        logger.error("🔓 No master key created: %s; private keys stay unencrypted until then.",
                     refusal)
        return 'ephemeral'
    try:
        stats = activate_new_master_key(exclusive=True)
    except FileExistsError:
        # Another process of this start created it first
        key_encryption.reload()
        return 'present' if key_encryption.is_enabled else 'configured'
    except (OSError, KeyActivationError) as e:
        logger.error("🔓 Could not create the master key %s: %s; private keys stay unencrypted",
                     path, e)
        return 'unwritable'

    logger.warning(
        "🔑 Master key created at %s; %d keys and secrets encrypted, %d errors. Back this file "
        "up: without it a copy of the database cannot be decrypted.",
        path, stats['encrypted'], len(stats['errors']))
    _log_remaining(stats['errors'])
    from services.audit_service import AuditService
    AuditService.log_action(
        action='encryption_enabled',
        resource_type='system',
        resource_name='Private Key Encryption',
        details=(f"Master key created at first start. Encrypted {stats['encrypted']} keys, "
                 f"{len(stats['errors'])} errors. Removed {stats['purge']['removed']} key files."),
        success=not stats['errors'],
    )
    return 'generated'


PREVIOUS_KEK_ENV = 'KEY_ENCRYPTION_KEY_PREVIOUS'


def previous_kek_path():
    return _encryption.MASTER_KEY_PATH.with_name('master.key.previous')


def _previous_kek():
    """The KEK being replaced by hand (file beside master.key, or variable), as raw bytes."""
    import base64
    from cryptography.fernet import Fernet
    path = previous_kek_path()
    value = path.read_text().strip() if path.exists() else os.getenv(PREVIOUS_KEK_ENV, '').strip()
    if not value:
        return None
    Fernet(value.encode())  # same format as the KEK; raises when it is not one
    return base64.urlsafe_b64decode(value.encode())


def _reads_with(kek: bytes) -> bool:
    """Whether the first encrypted value decrypts with ``kek`` taken as DEK version 1."""
    import base64
    from cryptography.fernet import Fernet, InvalidToken
    fernet = Fernet(base64.urlsafe_b64encode(kek))
    for _, row, attribute, _ in _encryption.master_key_values():
        value = getattr(row, attribute)
        if _encryption.key_encryption.is_encrypted(value):
            try:
                fernet.decrypt(base64.b64decode(value)[len(_encryption.ENCRYPTED_MARKER):])
            except InvalidToken:
                return False
            return True
    return False


def rewrap_under_new_kek() -> str:
    """Manual KEK change: the DEKs the previous KEK wrapped are wrapped by the configured one,
    and its disabled markers name the configured one.

    Writes encryption_keys and the audit entry encryption_kek_changed, never a stored value;
    returns what was done.
    """
    from models import db, EncryptionKey
    from security import envelope
    from security.dek_rotation import lock_key_state
    from utils.datetime_utils import utc_now
    try:
        previous = _previous_kek()
    except Exception as e:
        logger.error("🔑 The previous key-encryption key is unreadable, nothing rewrapped: %s",
                     type(e).__name__)
        return 'unreadable'
    current = _encryption.key_encryption.kek_bytes_for_envelope()
    if previous is None:
        return 'none'
    if current is None or previous == current:
        logger.warning("🔑 A previous key-encryption key is configured but no new one: nothing "
                       "rewrapped")
        return 'same'
    lock_key_state()
    old_id, new_id = envelope.kek_id(previous), envelope.kek_id(current)
    rows = EncryptionKey.query.order_by(EncryptionKey.version).all()
    changed = 0
    # Disabled markers move too, even with no DEK row: left under the old KEK, a disabled
    # cluster would read as disabled under another one (safe mode in HA)
    for row in rows:
        if row.kek_id != old_id:
            continue
        if row.state != envelope.DISABLED:
            dek = envelope.material(previous, row.version, row.wrapped)
            row.wrapped = envelope.wrap(current, row.version, dek)
        row.kek_id = new_id
        changed += 1
    if not any(r.state in (envelope.ACTIVE, envelope.PREVIOUS) for r in rows) \
            and _reads_with(previous):
        # DEK version 1 was the previous KEK's material: from now on it is stored, wrapped
        db.session.add(EncryptionKey(version=1, state=envelope.ACTIVE, kek_id=new_id,
                                     wrapped=envelope.wrap(current, 1, previous),
                                     created_at=utc_now()))
        changed += 1
    if not changed:
        db.session.rollback()
        return 'nothing'
    db.session.commit()
    from services.audit_service import AuditService
    AuditService.log_action(
        action='encryption_kek_changed', resource_type='system',
        resource_name='Key Encryption Key',
        details=(f"{changed} encryption key row(s) (data-encryption keys, disabled markers) "
                 f"moved from KEK {old_id} to KEK {new_id}"),
        success=True)
    logger.warning("🔑 %d encryption key row(s) moved under the new key-encryption key "
                   "(%s). Remove %s (or %s) once every node runs with the new key.",
                   changed, new_id, previous_kek_path(), PREVIOUS_KEK_ENV)
    return 'rewrapped'


def live_peers_with_another_kek() -> list:
    """HA: (node_id, fingerprint) of each live peer that publishes another KEK than this node's,
    a process holding this node's identifier under another token included."""
    from utils.ha import ha_enabled
    if not ha_enabled():
        return []
    from sqlalchemy import and_, or_
    from config.settings import Config
    from models import ClusterNode
    from services.scheduler_leader import STALE_PASSES, cluster_utc_now, instance_token
    from services.scheduler_service import WAKE_INTERVAL_SECONDS
    mine = _encryption.key_encryption.configured_kek_fingerprint()
    now = cluster_utc_now()
    # Another process under this node's identifier is a peer too
    others = or_(ClusterNode.node_id != Config.NODE_ID,
                 and_(ClusterNode.instance_token.isnot(None), ClusterNode.instance_token != instance_token()))
    return [(peer.node_id, peer.kek_fingerprint)
            for peer in ClusterNode.query.filter(others).order_by(ClusterNode.node_id).all()
            if (now - peer.heartbeat_at).total_seconds() <= STALE_PASSES * WAKE_INTERVAL_SECONDS
            and peer.kek_fingerprint and peer.kek_fingerprint != mine]


def _database_names_kek(fingerprint) -> bool:
    """An encryption_keys row (DEK or disabled marker) was made under this KEK."""
    from models import EncryptionKey
    return bool(fingerprint) and EncryptionKey.query.filter_by(kek_id=fingerprint).first() is not None


def refuse_kek_mismatch_with_peers() -> None:
    """HA: a node whose KEK fingerprint differs from a live peer's does not start, unless the
    database names this node's KEK and not the peer's (that peer is the stranger)."""
    from config.settings import Config
    mine = _encryption.key_encryption.configured_kek_fingerprint()
    for node_id, theirs in live_peers_with_another_kek():
        if _database_names_kek(mine) and not _database_names_kek(theirs):
            logger.error("🔒 HA: live peer %s holds another key-encryption key (fingerprint %s) "
                         "than the cluster's; it writes nothing until it has the cluster's",
                         node_id, theirs)
            continue
        raise SystemExit(
            f"HA: the key-encryption key of node {Config.NODE_ID} (fingerprint {mine or 'none'}) "
            f"differs from that of live peer {node_id} (fingerprint "
            f"{theirs}). Configure the same KEY_ENCRYPTION_KEY or master.key "
            "on every node.")


def _apply_safe_mode(app, outcome=None) -> bool:
    key_encryption = _encryption.key_encryption
    has_enc = _encryption.has_encrypted_keys_in_db()
    mismatch = outcome in ('wrong_key', 'foreign_disable', 'foreign_kek')
    app.config['SAFE_MODE'] = not key_encryption.is_enabled and (has_enc or mismatch)
    if outcome in ('foreign_disable', 'foreign_kek') and not has_enc:
        # Nothing is encrypted: the KEK is not the cluster's, no key is undecryptable
        reason = 'encryption_kek_not_the_clusters'
    else:
        reason = 'encryption_key_mismatch' if mismatch else 'encryption_key_missing'
    app.config['SAFE_MODE_REASON'] = reason
    return has_enc


def _marker_is_foreign(key_encryption) -> bool:
    """No DEK row, and a disable marker that is not this KEK's."""
    from security import envelope
    rows = key_encryption.dek_rows
    if not key_encryption.kek_loaded or any(
            r[1] in (envelope.ACTIVE, envelope.PREVIOUS) for r in rows):
        return False
    markers = {r[2] for r in rows if r[1] == envelope.DISABLED}
    return bool(markers) and key_encryption.kek_fingerprint() not in markers


def _marker_is_foreign_in_ha(key_encryption) -> bool:
    """HA: the cluster was disabled under another KEK. Outside HA a file disable followed by
    a new master.key leaves that marker legitimately."""
    from utils.ha import ha_enabled
    return ha_enabled() and _marker_is_foreign(key_encryption)


def _kek_is_foreign(key_encryption) -> bool:
    """No DEK row: the database was written under another KEK when a peer's disable marker
    is not this KEK's, or when a value does not open with this KEK (the start path's check)."""
    from security import envelope
    if any(r[1] in (envelope.ACTIVE, envelope.PREVIOUS) for r in key_encryption.dek_rows):
        return False
    if _marker_is_foreign(key_encryption):
        return True
    return key_encryption.is_enabled and not _loaded_key_reads_the_database()


def reload_encryption_state(app) -> None:
    """Cluster command reload_encryption: the DEKs from the database, safe mode re-evaluated."""
    key_encryption = _encryption.key_encryption
    # A KEK this process refused stays refused, whatever the database now holds
    outcome = key_encryption.kek_refused
    key_encryption.reload()
    if outcome:
        pass
    elif not key_encryption.dek_error and _marker_is_foreign(key_encryption):
        outcome = 'foreign_disable'
    elif key_encryption.dek_error or (key_encryption.kek_loaded
                                      and _kek_is_foreign(key_encryption)):
        outcome = 'wrong_key'
    elif key_encryption.kek_loaded and live_peers_with_another_kek() and not _database_names_kek(
            key_encryption.kek_fingerprint()):
        # No row names this KEK and a live peer holds another one: it is not the cluster's
        outcome = 'foreign_kek'
    if outcome:
        key_encryption.refuse_kek(outcome)
    if outcome is None and key_encryption.is_enabled:
        # Enabled with the database's KEK: no safe mode, and no scan of every stored value
        app.config['SAFE_MODE'] = False
    else:
        _apply_safe_mode(app, outcome)
    logger.info("🔐 Encryption reloaded: enabled=%s, DEK version=%s, safe mode=%s",
                key_encryption.is_enabled, key_encryption.active_version,
                app.config['SAFE_MODE'])


def check_master_key_at_start(app) -> None:
    """Load the master key, create it on a new installation, and enter safe mode
    when encrypted keys are found without it. Runs inside an app context."""
    key_encryption = _encryption.key_encryption
    key_encryption.start_over()
    refuse_kek_mismatch_with_peers()
    # Before anything reads the DEKs: a KEK changed by hand leaves them wrapped by the previous one
    if rewrap_under_new_kek() == 'rewrapped':
        key_encryption.reload()
    outcome = bootstrap_master_key(app)
    if outcome == 'present':
        from security.dek_rotation import resume_at_start
        resume_at_start()
    has_enc = _apply_safe_mode(app, outcome)
    app.logger.info(
        f"🔐 Encryption check: enabled={key_encryption.is_enabled}, has_encrypted_keys={has_enc}, "
        f"key_source={key_encryption.key_source}, DEK version={key_encryption.active_version}, "
        f"first_start={outcome}")
    if not key_encryption.is_enabled and not has_enc and outcome in ('disabled', 'configured'):
        if key_encryption.kek_loaded:
            app.logger.warning("🔓 Private-key encryption is turned off; a key-encryption key "
                               "is configured but holds no data-encryption key")
        else:
            _encryption.log_encryption_disabled()
    reason = app.config['SAFE_MODE_REASON']
    if app.config['SAFE_MODE'] and reason == 'encryption_kek_not_the_clusters':
        app.logger.error(
            "🔒 SAFE MODE: this node's key-encryption key is not the cluster's (the cluster was "
            "disabled under another key, or a live node holds another one); nothing is written. "
            "Configure the cluster's KEY_ENCRYPTION_KEY (or master.key) on this node, or, after "
            f"a key change by hand, the cluster's previous key in {PREVIOUS_KEK_ENV}, and "
            "restart UCM.")
    elif app.config['SAFE_MODE'] and reason == 'encryption_key_mismatch':
        app.logger.error(
            "🔒 SAFE MODE: the configured master key does not decrypt the stored private keys. "
            f"Restore the previous {_encryption.MASTER_KEY_PATH} (or KEY_ENCRYPTION_KEY) "
            "and restart UCM.")
    elif app.config['SAFE_MODE']:
        app.logger.error(
            "🔒 SAFE MODE: Encrypted private keys found but no encryption key available. "
            f"Place your master.key file at {_encryption.MASTER_KEY_PATH} and restart UCM.")
