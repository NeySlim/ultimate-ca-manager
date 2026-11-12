"""The session secret (SECRET_KEY) stored in the database under the DEK, shared by every node.

Three system_config rows: the active key and the previous one, each encrypted as a whole
like the other master-key values (a DEK rotation rewrites them), and the instant until
which the previous one is still accepted. No row, or at start one that does not open: the
environment's SECRET_KEY signs, as before. A key is never stored in the clear.
"""
import logging
import secrets as py_secrets
import time
from datetime import datetime

from security.csrf import CSRF_TOKEN_LIFETIME

logger = logging.getLogger(__name__)

ACTIVE_KEY = 'session.secret_key'
PREVIOUS_KEY = 'session.secret_key.previous'
RETIRE_KEY = 'session.secret_key.retire_after'
# Encrypted under the DEK, rewritten by a DEK rotation
STORED_KEYS = (ACTIVE_KEY, PREVIOUS_KEY)
ALL_KEYS = STORED_KEYS + (RETIRE_KEY,)
# A CSRF token is the longest-lived value signed with the key (the session id is not
# signed): none signed before a rotation is still valid after this
GRACE_SECONDS = CSRF_TOKEN_LIFETIME
MIN_LENGTH = 32
# A load that failed is tried again on a request, after this delay doubled up to the cap
RETRY_SECONDS = 5
RETRY_MAX_SECONDS = 300
_STATE = 'ucm_session_key'
_DESCRIPTIONS = {
    ACTIVE_KEY: 'Session secret key (encrypted)',
    PREVIOUS_KEY: 'Previous session secret key, accepted until its retirement (encrypted)',
    RETIRE_KEY: 'Previous session secret key accepted until',
}


class SessionKeyError(RuntimeError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def _now():
    from services.scheduler_leader import cluster_utc_now
    return cluster_utc_now()


def _local_now():
    # Checked on every signed request: this host's clock, no query
    from utils.datetime_utils import utc_now
    return utc_now()


def _state(app):
    # The environment's key as create_app set it, captured before any row replaces it
    return app.extensions.setdefault(_STATE, {'env': app.config.get('SECRET_KEY')})


def environment_key(app):
    return _state(app)['env']


def stored_mode() -> bool:
    """True when a rotation stores the key: encryption on and new values encrypted."""
    from security.encryption import key_encryption
    return key_encryption.is_encrypting


def _read_rows():
    from models import SystemConfig
    return {r.key: r.value for r in
            SystemConfig.query.filter(SystemConfig.key.in_(ALL_KEYS)).all()}


def _open(value, what):
    """The key ``value`` holds, or None with a warning: never one stored in the clear."""
    from security import encryption as _encryption
    if not _encryption.key_encryption.is_encrypted(value):
        logger.warning("The stored %s is not encrypted: ignored", what)
        return None
    try:
        key = _encryption.decrypt_master_key_value(value, 'text')
    except Exception:
        logger.warning("The stored %s does not decrypt with this node's encryption key "
                       "(restored from another installation, or another key-encryption key)",
                       what)
        return None
    return key or None


def _until(rows):
    raw = rows.get(RETIRE_KEY)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def load(app, at_start=False) -> str:
    """Sets this process's signing key and the previous key it still accepts, from the
    database; the environment's key when nothing is stored. A row that cannot be read or
    opened falls back to the environment at start only, a reload keeps the keys in memory;
    either way reload_if_pending() tries again until it succeeds. Returns the source."""
    from models import db
    state = _state(app)
    active, previous, until, source = state['env'], None, None, 'environment'
    failed = None
    try:
        rows = _read_rows()
    except Exception as e:
        db.session.rollback()
        logger.warning("Session key not read from the database (%s)", type(e).__name__)
        rows, failed = {}, 'read'
    if rows.get(ACTIVE_KEY):
        stored = _open(rows[ACTIVE_KEY], 'session key')
        if stored is None:
            failed = 'open'
        else:
            active, source = stored, 'database'
            until = _until(rows)
            try:
                in_grace = until is not None and _now() < until
            except Exception as e:
                db.session.rollback()
                logger.warning("Session key grace not checked, the clock was not read (%s)",
                               type(e).__name__)
                in_grace, failed = False, 'clock'
            if rows.get(PREVIOUS_KEY) and in_grace:
                previous = _open(rows[PREVIOUS_KEY], 'previous session key')
                if previous is None:
                    failed = 'open'
    if failed:
        delay = RETRY_SECONDS if 'retry' not in state else \
            min(state['retry'][1] * 2, RETRY_MAX_SECONDS)
        state['retry'] = (time.monotonic() + delay, delay)
    else:
        state.pop('retry', None)
    if failed and not at_start:
        logger.warning("Session key reload incomplete: this node keeps the keys it had "
                       "and tries again")
        return state.get('source', 'environment')
    if failed and source == 'environment':
        logger.warning("The environment's SECRET_KEY signs on this node; rotate the session "
                       "key to store a new one")
    app.config['SECRET_KEY'] = active
    app.config['SECRET_KEY_FALLBACKS'] = [previous] if previous else []
    state.update(source=source, previous_until=until if previous else None)
    return source


def reload_pending(app) -> bool:
    return 'retry' in (app.extensions.get(_STATE) or {})


def reload_if_pending() -> None:
    """Before a request: the last load failed and its delay is over, load again. Without
    this a node would refuse the new key's tokens until the next command or a restart."""
    from flask import current_app
    app = current_app._get_current_object()
    retry = (app.extensions.get(_STATE) or {}).get('retry')
    if retry is None or time.monotonic() < retry[0]:
        return
    load(app)


def verification_keys(app) -> list:
    """The keys a signed value may be checked against: the active one, then the previous one
    while its grace runs (dropped from memory once it is over)."""
    keys = [app.config.get('SECRET_KEY') or '']
    fallbacks = app.config.get('SECRET_KEY_FALLBACKS') or []
    if fallbacks:
        until = (app.extensions.get(_STATE) or {}).get('previous_until')
        if until is not None and _local_now() < until:
            keys.extend(k for k in fallbacks if k)
        else:
            app.config['SECRET_KEY_FALLBACKS'] = []
    return keys


def status(app) -> dict:
    state = _state(app)
    until = state.get('previous_until') if app.config.get('SECRET_KEY_FALLBACKS') else None
    return {
        'source': state.get('source', 'environment'),
        'previous_accepted_until': until.isoformat(timespec='seconds') if until else None,
    }


def _put(key, value):
    from models import db, SystemConfig
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value, description=_DESCRIPTIONS[key]))
    else:
        row.value = value


def _emit_reload():
    from services.cluster_commands import RELOAD_SECRET_KEY, emit
    return emit(RELOAD_SECRET_KEY)


def rotate(app, new_secret=None):
    """New active key in the database, the current one kept as previous for GRACE_SECONDS;
    every node reloads through the cluster command. Returns the grace's end. Committed."""
    from datetime import timedelta
    from models import db
    from security import encryption as _encryption
    from security.dek_rotation import lock_key_state
    lock_key_state()
    _encryption.key_encryption.refresh()
    if not stored_mode():
        db.session.rollback()
        raise SessionKeyError('Encryption is not enabled: the session key cannot be stored')
    rows = _read_rows()
    now = _now()
    until = _until(rows)
    # One previous key at a time: a second rotation would cut the tokens of the first short
    if rows.get(PREVIOUS_KEY) and until is not None and now < until:
        db.session.rollback()
        raise SessionKeyError(f"The previous session key is accepted until "
                              f"{until.isoformat(timespec='seconds')} UTC: rotate again after that.")
    current = (_open(rows[ACTIVE_KEY], 'session key') if rows.get(ACTIVE_KEY) else None) \
        or environment_key(app)
    new_secret = new_secret or py_secrets.token_urlsafe(48)
    until = now + timedelta(seconds=GRACE_SECONDS)
    _put(ACTIVE_KEY, _encryption.encrypt_master_key_value(new_secret, 'text'))
    _put(PREVIOUS_KEY, _encryption.encrypt_master_key_value(current, 'text'))
    _put(RETIRE_KEY, until.isoformat())
    command = _emit_reload()
    db.session.commit()
    load(app)
    return until, command


def retire_if_due(app=None) -> bool:
    """Drops the previous key once its grace is over; True when it did. Committed."""
    from flask import current_app
    from models import db, SystemConfig
    from security.dek_rotation import lock_key_state
    app = app or current_app._get_current_object()
    until = _until(_read_rows())
    if until is None or _now() < until:
        db.session.rollback()
        return False
    lock_key_state()
    until = _until(_read_rows())
    if until is None or _now() < until:
        db.session.rollback()
        return False
    SystemConfig.query.filter(SystemConfig.key.in_((PREVIOUS_KEY, RETIRE_KEY))).delete(
        synchronize_session=False)
    _emit_reload()
    db.session.commit()
    load(app)
    logger.info("Previous session key dropped after its grace period")
    return True


def scheduled_retire() -> None:
    """Scheduler task (the leader in HA)."""
    from models import db
    try:
        retire_if_due()
    except Exception:
        db.session.rollback()
        raise


def drop_stored() -> bool:
    """In the caller's transaction (a disable of encryption): the stored keys go, so none is
    ever kept in the clear; the environment's key signs again. True when there were some."""
    from models import SystemConfig
    removed = SystemConfig.query.filter(SystemConfig.key.in_(ALL_KEYS)).delete(
        synchronize_session=False)
    if removed:
        _emit_reload()
    return bool(removed)
