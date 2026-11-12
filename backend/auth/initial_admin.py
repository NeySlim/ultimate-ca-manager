"""The first administrator: its password is provided by the operator or generated once.

Provided (INITIAL_ADMIN_PASSWORD, or INITIAL_ADMIN_PASSWORD_FILE for a secret
mounted as a file): used as is, no forced change. Nothing provided: a random
password is written 0600 into the data directory and never logged; the account
must change it at first login, and the file goes with that change. Every path
that creates the account goes through seed_admin(); nothing here is read once
an account exists.
"""
import json
import logging
import os
import secrets
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

PASSWORD_FILE_NAME = 'initial-admin-password'
# SystemConfig row of a generated password: {"user_id": ..., "node": ...}, deleted at its change
MARKER_KEY = 'initial_admin.generated_password'
# No 0/O/o, 1/l/I: 56 symbols, 24 of them carry 139 bits and copy by hand without doubt
ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
LENGTH = 24
_SWEEP_KEY = 'initial_admin_sweep'


class InitialPasswordError(RuntimeError):
    """The initial password cannot be settled: the administrator is not created."""


@dataclass(frozen=True)
class InitialPassword:
    value: str = field(repr=False)
    generated: bool
    source: str  # 'INITIAL_ADMIN_PASSWORD', 'INITIAL_ADMIN_PASSWORD_FILE' or 'generated'
    # Provided, but drawn by a deployment tool (the Helm chart): nobody chose it
    force_change: bool = False


def password_file(config) -> Path:
    from config.settings import DATA_DIR
    return Path(config.get('DATA_DIR') or DATA_DIR) / PASSWORD_FILE_NAME


def read_command(path) -> str:
    from config.settings import is_docker
    if is_docker():
        return f'docker exec <container> cat {path}'
    return f'sudo cat {path}'


def resolve(config) -> InitialPassword:
    """Both sources set is refused: which one the operator meant cannot be guessed."""
    value = config.get('INITIAL_ADMIN_PASSWORD') or ''
    force = str(config.get('INITIAL_ADMIN_PASSWORD_FORCE_CHANGE') or '').lower() in ('1', 'true', 'yes')
    path = config.get('INITIAL_ADMIN_PASSWORD_FILE') or ''
    if value and path:
        raise InitialPasswordError(
            'INITIAL_ADMIN_PASSWORD and INITIAL_ADMIN_PASSWORD_FILE are both set: keep only one')
    if path:
        try:
            with open(path, encoding='utf-8') as f:
                value = f.read()
        except (OSError, UnicodeDecodeError) as e:
            reason = getattr(e, 'strerror', None) or type(e).__name__
            raise InitialPasswordError(
                f'INITIAL_ADMIN_PASSWORD_FILE {path} cannot be read: {reason}') from None
        value = value.rstrip('\r\n')
        if not value:
            raise InitialPasswordError(f'INITIAL_ADMIN_PASSWORD_FILE {path} is empty')
        return InitialPassword(value, False, 'INITIAL_ADMIN_PASSWORD_FILE', force)
    if value:
        return InitialPassword(value, False, 'INITIAL_ADMIN_PASSWORD', force)
    return InitialPassword(''.join(secrets.choice(ALPHABET) for _ in range(LENGTH)), True, 'generated')


def _write_atomically(path: Path, value: str):
    fd, tmp = tempfile.mkstemp(prefix=f'.{PASSWORD_FILE_NAME}.', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(value + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


def _probe(path: Path):
    """Raises OSError unless a file could be put at path now; writes nothing there."""
    if path.is_dir():
        raise IsADirectoryError(21, 'Is a directory')
    fd, tmp = tempfile.mkstemp(prefix=f'.{PASSWORD_FILE_NAME}.', dir=path.parent)
    os.close(fd)
    os.unlink(tmp)


def prepare(config, defer_write=False) -> InitialPassword:
    """resolve(), and a generated password on disk before any account holds it.

    defer_write: only check the file can be written, write_generated() puts it
    there later (a reset must not replace a live file before its drop succeeds)."""
    prepared = resolve(config)
    if prepared.generated:
        _put(password_file(config), prepared.value, probe_only=defer_write)
    else:
        _warn_if_weak(prepared)
    return prepared


def write_generated(config, prepared):
    """The file of a prepare(defer_write=True); nothing for a provided password."""
    if prepared.generated:
        _put(password_file(config), prepared.value)


def _put(path, value, probe_only=False):
    try:
        _probe(path) if probe_only else _write_atomically(path, value)
    except OSError as e:
        raise InitialPasswordError(
            f'the generated initial password cannot be written to {path}: '
            f'{e.strerror or type(e).__name__}; the administrator is not created') from None


def _warn_if_weak(prepared):
    """The policy never gated this account; it is evaluated and said, the value is kept."""
    from security.password_policy import validate_password
    try:
        ok, errors = validate_password(prepared.value)
    except Exception:
        return
    if not ok:
        logger.warning(f'The password from {prepared.source} does not meet the password policy '
                       f'({errors[0]["message"]}); it is used as provided, change it after login')


def seed_admin(config, prepared=None):
    """The configured administrator, added to the session; the caller commits."""
    from config.settings import Config
    from models import SystemConfig, User, db
    prepared = prepared or prepare(config)
    admin = User(
        username=config.get('INITIAL_ADMIN_USERNAME') or 'admin',
        email=config.get('INITIAL_ADMIN_EMAIL') or 'admin@localhost',
        role='admin',
        active=True,
        force_password_change=prepared.generated or prepared.force_change,
        # Forced 2FA enrolment (#141) never locks this account out
        totp_exempt=True,
    )
    admin.set_password(prepared.value)
    db.session.add(admin)
    if prepared.generated:
        db.session.flush()
        marker = json.dumps({'user_id': admin.id, 'node': Config.NODE_ID})
        row = SystemConfig.query.filter_by(key=MARKER_KEY).first()
        if row is None:
            db.session.add(SystemConfig(key=MARKER_KEY, value=marker,
                                        description='Where the generated initial password is'))
        else:
            row.value = marker
    return admin


def _marker():
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=MARKER_KEY).first()
    if row is None:
        return None, None
    try:
        return row, json.loads(row.value or '{}')
    except ValueError:
        return row, {}


def forget_generated(user):
    """User.set_password on a saved account: its generated password, if any, is gone.

    The marker goes in the caller's transaction; the local file once it commits,
    the other nodes' through a cluster command."""
    from models import db
    row, marker = _marker()
    if row is None or marker.get('user_id') != user.id:
        return
    db.session.delete(row)
    from services import cluster_commands
    cluster_commands.emit(cluster_commands.DROP_INITIAL_PASSWORD)
    from flask import current_app
    db.session.info[_SWEEP_KEY] = (row, password_file(current_app.config))


@event.listens_for(Session, 'after_commit')
def _remove_after_commit(session):
    pending = session.info.pop(_SWEEP_KEY, None)
    if pending is None:
        return
    row, path = pending
    if sa_inspect(row).was_deleted:
        _remove(path)


@event.listens_for(Session, 'after_rollback')
def _keep_after_rollback(session):
    session.info.pop(_SWEEP_KEY, None)


def _remove(path):
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as e:
        logger.error(f'The initial password file {path} could not be removed: {e.strerror}')
        return
    logger.info(f'Initial password file {path} removed: the password it held was changed')


def sweep(config):
    """Remove this node's file unless it still opens the account the marker names.

    Startup and the cluster command run it: a change made on another node, or a
    database reset, leaves no stale password behind. Never raises."""
    path = password_file(config)
    try:
        if not path.exists():
            return
        from models import User, db
        _, marker = _marker()
        user = db.session.get(User, marker.get('user_id')) if marker else None
        try:
            current = path.read_text(encoding='utf-8').rstrip('\r\n')
        except (OSError, UnicodeDecodeError):
            current = ''
        if user is None or not current or not user.check_password(current):
            _remove(path)
    except Exception as e:
        logger.error(f'Initial password file {path} not checked: {type(e).__name__}: {e}')


def announce(config):
    """Each start: where the generated password is while it has not been changed."""
    from config.settings import Config
    from models import User, db
    from utils.ha import ha_enabled
    _, marker = _marker()
    if not marker:
        return
    user = db.session.get(User, marker.get('user_id'))
    if user is None:
        return
    path = password_file(config)
    node = marker.get('node')
    if path.exists():
        logger.warning(f"Initial administrator '{user.username}': generated password in {path} "
                       f'(read it with: {read_command(path)}); it must be changed at first '
                       f'login, which removes the file')
    elif ha_enabled() and node and node != Config.NODE_ID:
        logger.warning(f"Initial administrator '{user.username}': its generated password file "
                       f'is on node {node}, in its data directory ({path.name})')
    else:
        logger.error(f"Initial administrator '{user.username}': the generated password file "
                     f'{path} is missing and the password was never changed; see "Lost '
                     f'initial password" in the administration guide')
