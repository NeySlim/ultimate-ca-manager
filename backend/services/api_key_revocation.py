"""Revoke-then-delete of an API key, shared by its owner and an administrator."""
import logging

from models import db
from services.audit_service import AuditService
from utils.db_transaction import safe_commit

logger = logging.getLogger(__name__)


def revoke_or_delete(api_key, action_prefix, details):
    """Revoke a usable key (kept for audit history), delete a revoked or expired one.

    ``details(verb, name)`` builds the audit text. Returns (verb, error_response):
    verb is 'revoked' or 'deleted', and the error response is None unless the
    commit failed.
    """
    key_id, key_name = api_key.id, api_key.name
    if api_key.is_active and not api_key.is_expired:
        api_key.is_active = False
        verb, suffix = 'revoked', 'revoke'
    else:
        db.session.delete(api_key)
        verb, suffix = 'deleted', 'delete'
    ok, err = safe_commit(logger, f'Failed to {suffix} API key')
    if not ok:
        return None, err

    AuditService.log_action(
        action=f'{action_prefix}_{suffix}',
        resource_type='api_key',
        resource_id=str(key_id),
        resource_name=key_name,
        details=details(verb.capitalize(), key_name),
        success=True,
    )
    return verb, None
