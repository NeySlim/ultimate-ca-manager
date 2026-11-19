import json
import logging
from typing import Optional
from flask import request, g, has_request_context
from models import db, AuditLog
from utils.datetime_utils import utc_now
from utils.trusted_proxy import client_ip
from .chain import append_entry, verify_chain
from .staging import fit_to_columns, forward_to_syslog, syslog_copy

logger = logging.getLogger(__name__)


class AuditCoreLoggingMixin:

    @staticmethod
    def log_action(
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        details: Optional[str] = None,
        success: bool = True,
        username: Optional[str] = None,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> AuditLog:
        audit_log = None
        try:
            in_request = has_request_context()

            if username is None and in_request and hasattr(g, 'current_user') and g.current_user:
                username = g.current_user.username
            if user_id is None and in_request and hasattr(g, 'user_id'):
                user_id = g.user_id

            # An explicit address (the DNS UPDATE listener has no request
            # context) wins over the one derived from the request.
            explicit_ip = ip_address
            ip_address = None
            user_agent = None
            if in_request:
                # Use trusted-proxy gating: only honor X-Forwarded-For when
                # the immediate peer is in UCM_TRUSTED_PROXIES. Prevents
                # spoofed XFF from arbitrary clients ending up in the audit
                # trail as if it were the real source.
                ip_address = client_ip()
                user_agent = request.headers.get('User-Agent', '')

            if explicit_ip:
                ip_address = str(explicit_ip)[:45]

            if not username:
                username = 'system' if not in_request else 'anonymous'

            if isinstance(resource_name, dict):
                resource_name = json.dumps(resource_name)
            if isinstance(details, dict):
                details = json.dumps(details)

            audit_log = AuditLog(
                timestamp=utc_now(),
                username=username,
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                resource_name=str(resource_name) if resource_name else None,
                details=str(details) if details else None,
                ip_address=ip_address,
                user_agent=user_agent,
                success=success
            )

            fit_to_columns(audit_log)
            append_entry(audit_log)
            db.session.commit()

            log_msg = f"AUDIT: {action} by {username} - {details}"
            if success:
                logger.info(log_msg)
            else:
                logger.warning(log_msg)

            forward_to_syslog(audit_log)
            return audit_log

        except Exception as e:
            # The action is already committed: its trace must still leave somewhere
            unsaved = syslog_copy(audit_log) if audit_log is not None else None
            logger.error(f"Failed to create audit log: {e}; lost entry: action={action} "
                         f"resource={resource_type}:{resource_id} user={username} details={details}")
            db.session.rollback()
            if unsaved is not None:
                forward_to_syslog(unsaved)
            return None

    @staticmethod
    def verify_integrity(start_id: int = None, end_id: int = None) -> dict:
        query = AuditLog.query.order_by(AuditLog.id.asc())
        if start_id:
            query = query.filter(AuditLog.id >= start_id)
        if end_id:
            query = query.filter(AuditLog.id <= end_id)

        # Streamed: memory stays flat on a large ledger. Only a check from the
        # first row can tell a purge from a prefix deleted by hand.
        return verify_chain(query.yield_per(2000),
                            whole_table=start_id is None and end_id is None)
