import json
import logging
from typing import Optional
from flask import request, g, has_request_context
from models import db, AuditLog
from utils.datetime_utils import utc_now

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
        user_id: Optional[int] = None
    ) -> AuditLog:
        try:
            in_request = has_request_context()

            if username is None and in_request and hasattr(g, 'current_user') and g.current_user:
                username = g.current_user.username
            if user_id is None and in_request and hasattr(g, 'user_id'):
                user_id = g.user_id

            ip_address = None
            user_agent = None
            if in_request:
                ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
                if ip_address and ',' in ip_address:
                    ip_address = ip_address.split(',')[0].strip()
                user_agent = request.headers.get('User-Agent', '')[:500]

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

            db.session.add(audit_log)
            db.session.flush()

            prev_log = AuditLog.query.filter(AuditLog.id < audit_log.id).order_by(AuditLog.id.desc()).first()
            prev_hash = prev_log.entry_hash if prev_log and prev_log.entry_hash else '0' * 64
            audit_log.prev_hash = prev_hash
            audit_log.entry_hash = audit_log.compute_hash(prev_hash)

            db.session.commit()

            log_msg = f"AUDIT: {action} by {username} - {details}"
            if success:
                logger.info(log_msg)
            else:
                logger.warning(log_msg)

            try:
                from services.syslog_service import syslog_forwarder
                if syslog_forwarder.is_enabled:
                    syslog_forwarder.send(audit_log)
            except Exception:
                pass

            return audit_log

        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
            db.session.rollback()
            return None

    @staticmethod
    def verify_integrity(start_id: int = None, end_id: int = None) -> dict:
        query = AuditLog.query.order_by(AuditLog.id.asc())
        if start_id:
            query = query.filter(AuditLog.id >= start_id)
        if end_id:
            query = query.filter(AuditLog.id <= end_id)

        logs = query.all()
        if not logs:
            return {'valid': True, 'checked': 0, 'errors': []}

        errors = []
        prev_hash = '0' * 64

        for log in logs:
            if not log.entry_hash:
                prev_hash = '0' * 64
                continue

            if log.prev_hash and log.prev_hash != prev_hash:
                errors.append({
                    'id': log.id,
                    'error': 'prev_hash mismatch',
                    'expected': prev_hash,
                    'actual': log.prev_hash
                })

            computed = log.compute_hash(log.prev_hash)
            if computed != log.entry_hash:
                errors.append({
                    'id': log.id,
                    'error': 'entry_hash mismatch (tampered)',
                    'expected': computed,
                    'actual': log.entry_hash
                })

            prev_hash = log.entry_hash

        return {
            'valid': len(errors) == 0,
            'checked': len(logs),
            'errors': errors
        }
