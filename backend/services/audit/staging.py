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
import logging

from flask import has_request_context, request

from models import db, AuditLog
from utils.datetime_utils import utc_now
from utils.trusted_proxy import client_ip
from .chain import append_entry

logger = logging.getLogger(__name__)


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
                entry.user_agent = request.headers.get('User-Agent', '')[:500]

        return append_entry(entry, purge_from=purge_from)
    except Exception:
        logger.warning("An audit entry could not be staged", exc_info=True)
        return None
