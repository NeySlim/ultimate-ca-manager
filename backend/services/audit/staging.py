"""Stage an audit entry inside the caller's transaction, sealed.

`AuditService.log_action` commits the session it is given, which is the right
thing for a route that has finished its work and the wrong thing for one in
the middle of a transaction it means to commit itself. Eight places therefore
built an `AuditLog` by hand and added it to the session.

All eight forgot the same thing: the seal. `prev_hash` and `entry_hash` were
left empty, and `verify_integrity` skips an entry carrying no hash and
restarts its chain there, so every one of those rows was a gap the
verification walked across while reporting a valid ledger. Eight copies of an
entry, eight copies of the omission.

This is the one way to put an entry in the session without committing it.
"""
import json
import logging
from types import SimpleNamespace

from flask import has_request_context, request
from sqlalchemy import event
from sqlalchemy.orm import Session

from models import db, AuditLog
from utils.datetime_utils import utc_now
from utils.trusted_proxy import client_ip
from .chain import append_entry

logger = logging.getLogger(__name__)

# Free-text columns are TEXT (migration 133): a guard keeps one header or bulk id list from bloating a row
_TEXT_CAPS = {'username': 255, 'resource_id': 1024, 'resource_name': 1024, 'user_agent': 1024}
_PENDING_SYSLOG = 'ucm_audit_syslog'
_SYSLOG_FIELDS = ('timestamp', 'action', 'username', 'ip_address', 'resource_type',
                  'resource_id', 'resource_name', 'success', 'details')


def fit_to_columns(entry):
    """Cut each bounded field to its column before sealing, so no INSERT is refused for
    its length or a NUL (PostgreSQL TEXT); a cut resource_id list stays whole in details."""
    for name, column in AuditLog.__table__.columns.items():
        value = getattr(entry, name)
        if not isinstance(value, str):
            continue
        if '\x00' in value:
            value = value.replace('\x00', '\\0')
            setattr(entry, name, value)
        cap = getattr(column.type, 'length', None) or _TEXT_CAPS.get(name)
        if cap and len(value) > cap:
            setattr(entry, name, value[:cap])
            if name == 'resource_id':
                entry.details = _with_full_ids(entry.details, value)
    return entry


def _with_full_ids(details, ids):
    try:
        parsed = json.loads(details) if details else None
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        return json.dumps({**parsed, 'resource_id': ids})
    return f'{details}\nresource_id: {ids}' if details else f'resource_id: {ids}'


def syslog_copy(entry):
    """The fields syslog sends, read now: the entry expires at commit."""
    return SimpleNamespace(**{name: getattr(entry, name, None) for name in _SYSLOG_FIELDS})


def forward_to_syslog(entry, reload=True):
    try:
        from services.syslog_service import syslog_forwarder
        if reload:
            syslog_forwarder.reload_if_changed()
        if syslog_forwarder.is_enabled:
            syslog_forwarder.send(entry)
    except Exception as e:
        # Syslog forwarding must never break audit logging itself.
        logger.warning(f"Syslog forward failed for audit action {getattr(entry, 'action', '?')}: {e}",
                       exc_info=True)


@event.listens_for(Session, 'after_commit')
def _syslog_after_commit(session):
    # A staged entry leaves for syslog once the outermost transaction commits, never at a RELEASE SAVEPOINT
    if session.in_nested_transaction():
        return
    for _tx, entry in session.info.pop(_PENDING_SYSLOG, ()):
        forward_to_syslog(entry, reload=False)  # reloaded at staging: no SQL in this hook


def _within(tx, ended):
    while tx is not None:
        if tx is ended:
            return True
        tx = tx.parent
    return False


@event.listens_for(Session, 'after_soft_rollback')
def _syslog_after_rollback(session, previous_transaction):
    # A rolled-back savepoint drops only what was staged inside it
    pending = session.info.get(_PENDING_SYSLOG)
    if not pending:
        return
    if previous_transaction is None or previous_transaction.parent is None:
        session.info.pop(_PENDING_SYSLOG, None)
        return
    pending[:] = [(tx, e) for tx, e in pending if not _within(tx, previous_transaction)]


@event.listens_for(Session, 'after_transaction_end')
def _syslog_after_transaction_end(session, transaction):
    # A root transaction that ends without a commit (close() fires no rollback event) drops the rest
    if transaction.parent is None and not transaction.nested:
        session.info.pop(_PENDING_SYSLOG, None)


def _staged_copy(entry):
    copy = syslog_copy(entry)
    try:
        from services.syslog_service import syslog_forwarder
        syslog_forwarder.reload_if_changed()
        if syslog_forwarder.is_enabled:
            copy.syslog_hostname = syslog_forwarder._resolve_hostname()
    except Exception:
        logger.debug("Syslog HOSTNAME not resolved at staging", exc_info=True)
    return copy


def stage_audit_entry(purge_from=None, **fields):
    """Add a sealed audit entry to the session. The caller commits.

    Returns the entry, or None when it could not be built: an import that
    cannot record itself still has to finish, and a protocol handler that has
    already issued a certificate must not answer an error because of its own
    ledger. `purge_from` marks a purge record (see `append_entry`).
    """
    try:
        fields.setdefault('timestamp', utc_now())
        fields.setdefault('success', True)
        entry = AuditLog(**fields)

        if has_request_context():
            if entry.ip_address is None:
                entry.ip_address = client_ip()
            if entry.user_agent is None:
                entry.user_agent = request.headers.get('User-Agent', '')

        fit_to_columns(entry)
        staged = append_entry(entry, purge_from=purge_from)
        session = db.session()
        tx = session.get_nested_transaction() or session.get_transaction()
        session.info.setdefault(_PENDING_SYSLOG, []).append((tx, _staged_copy(entry)))
        return staged
    except Exception:
        logger.warning("An audit entry could not be staged", exc_info=True)
        return None
