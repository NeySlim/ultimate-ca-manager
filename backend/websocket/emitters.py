"""
WebSocket event integration helpers.
Use these functions in services to emit events after actions.
"""

import re
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def _extract_cn(subject: str) -> str:
    """Extract clean CN from a full subject string like 'CN=host.example.com,O=Org,...'."""
    if not subject:
        return 'Unknown'
    m = re.search(r'CN=([^,/]+)', subject)
    return m.group(1).strip() if m else subject.split(',')[0].strip()


def emit_ws_event(event_type, data: Dict[str, Any], room: Optional[str] = None):
    """
    Safely emit a WebSocket event.
    Gracefully handles cases where WebSocket is not initialized.
    """
    try:
        from websocket import emit_event, EventType
        emit_event(event_type, data, room=room)
    except ImportError:
        logger.debug("WebSocket module not available")
    except Exception as e:
        logger.warning(f"Failed to emit WebSocket event: {e}")


# ==================== Certificate Events ====================

def on_certificate_issued(cert_id: int, cn: str, ca_id: int, issuer: str, valid_to: str):
    """Emit event when a certificate is issued."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.CERTIFICATE_ISSUED, {
        'id': cert_id,
        'cn': cn,
        'ca_id': ca_id,
        'issuer': issuer,
        'valid_to': valid_to
    })


def on_certificate_revoked(cert_id: int, cn: str, reason: str, revoked_by: str):
    """Emit event when a certificate is revoked."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.CERTIFICATE_REVOKED, {
        'id': cert_id,
        'cn': cn,
        'reason': reason,
        'revoked_by': revoked_by
    })


def on_certificate_renewed(cert_id: int, old_cert_id: int, cn: str):
    """Emit event when a certificate is renewed."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.CERTIFICATE_RENEWED, {
        'id': cert_id,
        'old_id': old_cert_id,
        'cn': cn
    })


def on_certificate_deleted(cert_id: int, cn: str, deleted_by: str):
    """Emit event when a certificate is deleted."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.CERTIFICATE_DELETED, {
        'id': cert_id,
        'cn': cn,
        'deleted_by': deleted_by
    })


# ==================== CA Events ====================

def on_ca_created(ca_id: int, name: str, common_name: str, created_by: str):
    """Emit event when a CA is created."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.CA_CREATED, {
        'id': ca_id,
        'name': name,
        'common_name': common_name,
        'created_by': created_by
    })


def on_ca_updated(ca_id: int, name: str, changes: Dict[str, Any]):
    """Emit event when a CA is updated."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.CA_UPDATED, {
        'id': ca_id,
        'name': name,
        'changes': changes
    })


def on_ca_deleted(ca_id: int, name: str, deleted_by: str):
    """Emit event when a CA is deleted."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.CA_DELETED, {
        'id': ca_id,
        'name': name,
        'deleted_by': deleted_by
    })


def on_ca_revoked(ca_id: int, name: str, reason: str, revoked_by: str):
    """Emit event when a CA is revoked."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.CA_REVOKED, {
        'id': ca_id,
        'name': name,
        'reason': reason,
        'revoked_by': revoked_by
    })


# ==================== CRL Events ====================

def on_crl_regenerated(ca_id: int, ca_name: str, next_update: str, entries_count: int):
    """Emit event when a CRL is regenerated."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.CRL_REGENERATED, {
        'ca_id': ca_id,
        'ca_name': ca_name,
        'next_update': next_update,
        'entries_count': entries_count
    })


# ==================== User Events ====================

def on_user_login(username: str, ip_address: str, method: str = 'password'):
    """Emit event when a user logs in."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.USER_LOGIN, {
        'username': username,
        'ip': ip_address,
        'method': method
    })


def on_user_logout(username: str):
    """Emit event when a user logs out."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.USER_LOGOUT, {
        'username': username
    })


def on_user_created(user_id: int, username: str, created_by: str):
    """Emit event when a user is created."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.USER_CREATED, {
        'id': user_id,
        'username': username,
        'created_by': created_by
    })


def on_user_deleted(user_id: int, username: str, deleted_by: str):
    """Emit event when a user is deleted."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.USER_DELETED, {
        'id': user_id,
        'username': username,
        'deleted_by': deleted_by
    })


# ==================== Group Events ====================

def on_group_created(group_id: int, name: str, created_by: str):
    """Emit event when a group is created."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.GROUP_CREATED, {
        'id': group_id,
        'name': name,
        'created_by': created_by
    })


def on_group_deleted(group_id: int, name: str, deleted_by: str):
    """Emit event when a group is deleted."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.GROUP_DELETED, {
        'id': group_id,
        'name': name,
        'deleted_by': deleted_by
    })


# ==================== System Events ====================

def on_system_alert(alert_type: str, message: str, severity: str = 'info', details: Optional[Dict] = None):
    """Emit a system alert."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.SYSTEM_ALERT, {
        'alert_type': alert_type,
        'message': message,
        'severity': severity,
        'details': details or {}
    })


def on_audit_critical(action: str, user: str, resource: str, details: Optional[Dict] = None):
    """Emit critical audit event."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.AUDIT_CRITICAL, {
        'action': action,
        'user': user,
        'resource': resource,
        'details': details or {}
    })


# ==================== Discovery Events ====================

def on_discovery_scan_started(scan_run_id: int, profile_name: str, total_targets: int):
    """Emit event when a discovery scan starts."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.DISCOVERY_SCAN_STARTED, {
        'scan_run_id': scan_run_id,
        'profile_name': profile_name,
        'total_targets': total_targets,
    })


def on_discovery_scan_progress(scan_run_id: int, scanned: int, total: int, found: int):
    """Emit scan progress update."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.DISCOVERY_SCAN_PROGRESS, {
        'scan_run_id': scan_run_id,
        'scanned': scanned,
        'total': total,
        'found': found,
    })


def on_discovery_scan_complete(scan_run_id: int, summary: Dict):
    """Emit event when a discovery scan completes."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.DISCOVERY_SCAN_COMPLETE, {
        'scan_run_id': scan_run_id,
        'summary': summary,
    })


def on_discovery_new_cert(target: str, port: int, subject: str):
    """Emit event when a new unmanaged certificate is found."""
    from websocket.event_types import EventType
    cn = _extract_cn(subject)
    emit_ws_event(EventType.DISCOVERY_NEW_CERT, {
        'target': target,
        'port': port,
        'cn': cn,
        'subject': subject,
    })


def on_discovery_cert_changed(target: str, port: int, old_subject: str, new_subject: str):
    """Emit event when a certificate on a monitored endpoint has changed."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.DISCOVERY_CERT_CHANGED, {
        'target': target,
        'port': port,
        'old_cn': _extract_cn(old_subject),
        'new_cn': _extract_cn(new_subject),
    })


# ==================== SSH Certificate Events ====================

def on_ssh_ca_created(ca_id: int, name: str, ca_type: str, created_by: str):
    """Emit event when an SSH CA is created."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.SSH_CA_CREATED, {
        'id': ca_id, 'name': name, 'ca_type': ca_type, 'created_by': created_by,
    })


def on_ssh_ca_updated(ca_id: int, name: str, updated_by: str):
    """Emit event when an SSH CA is updated."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.SSH_CA_UPDATED, {
        'id': ca_id, 'name': name, 'updated_by': updated_by,
    })


def on_ssh_ca_deleted(ca_id: int, name: str, deleted_by: str):
    """Emit event when an SSH CA is deleted."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.SSH_CA_DELETED, {
        'id': ca_id, 'name': name, 'deleted_by': deleted_by,
    })


def on_ssh_certificate_issued(cert_id: int, key_id: str, ca_id: int, cert_type: str):
    """Emit event when an SSH certificate is issued."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.SSH_CERTIFICATE_ISSUED, {
        'id': cert_id, 'key_id': key_id, 'ca_id': ca_id, 'cert_type': cert_type,
    })


def on_ssh_certificate_revoked(cert_id: int, key_id: str, reason: str, revoked_by: str):
    """Emit event when an SSH certificate is revoked."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.SSH_CERTIFICATE_REVOKED, {
        'id': cert_id, 'key_id': key_id, 'reason': reason, 'revoked_by': revoked_by,
    })


def on_ssh_certificate_deleted(cert_id: int, key_id: str, deleted_by: str):
    """Emit event when an SSH certificate is deleted."""
    from websocket.event_types import EventType
    emit_ws_event(EventType.SSH_CERTIFICATE_DELETED, {
        'id': cert_id, 'key_id': key_id, 'deleted_by': deleted_by,
    })
