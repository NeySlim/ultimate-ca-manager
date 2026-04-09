"""
WebSocket event type definitions.
"""

from enum import Enum


class EventType(str, Enum):
    """All WebSocket event types."""
    
    # Certificate events
    CERTIFICATE_ISSUED = 'certificate.issued'
    CERTIFICATE_REVOKED = 'certificate.revoked'
    CERTIFICATE_EXPIRING = 'certificate.expiring'
    CERTIFICATE_RENEWED = 'certificate.renewed'
    CERTIFICATE_DELETED = 'certificate.deleted'
    
    # CA events
    CA_CREATED = 'ca.created'
    CA_UPDATED = 'ca.updated'
    CA_DELETED = 'ca.deleted'
    CA_REVOKED = 'ca.revoked'
    
    # CRL events
    CRL_REGENERATED = 'crl.regenerated'
    CRL_PUBLISHED = 'crl.published'
    
    # User events
    USER_LOGIN = 'user.login'
    USER_LOGOUT = 'user.logout'
    USER_CREATED = 'user.created'
    USER_UPDATED = 'user.updated'
    USER_DELETED = 'user.deleted'
    
    # Group events
    GROUP_CREATED = 'group.created'
    GROUP_UPDATED = 'group.updated'
    GROUP_DELETED = 'group.deleted'
    
    # System events
    SYSTEM_ALERT = 'system.alert'
    SYSTEM_BACKUP = 'system.backup'
    SYSTEM_RESTORE = 'system.restore'
    
    # Audit events
    AUDIT_CRITICAL = 'audit.critical'
    
    # Protocol events
    ACME_ORDER_COMPLETED = 'acme.order.completed'
    SCEP_ENROLLMENT = 'scep.enrollment'
    OCSP_REQUEST = 'ocsp.request'

    # Discovery events
    DISCOVERY_SCAN_STARTED = 'discovery.scan_started'
    DISCOVERY_SCAN_PROGRESS = 'discovery.scan_progress'
    DISCOVERY_SCAN_COMPLETE = 'discovery.scan_complete'
    DISCOVERY_NEW_CERT = 'discovery.new_certificate'
    DISCOVERY_CERT_CHANGED = 'discovery.cert_changed'

    # SSH Certificate events
    SSH_CA_CREATED = 'ssh_ca.created'
    SSH_CA_UPDATED = 'ssh_ca.updated'
    SSH_CA_DELETED = 'ssh_ca.deleted'
    SSH_CERTIFICATE_ISSUED = 'ssh_certificate.issued'
    SSH_CERTIFICATE_REVOKED = 'ssh_certificate.revoked'
    SSH_CERTIFICATE_DELETED = 'ssh_certificate.deleted'


# Event metadata for documentation
EVENT_DESCRIPTIONS = {
    EventType.CERTIFICATE_ISSUED: "A new certificate has been issued",
    EventType.CERTIFICATE_REVOKED: "A certificate has been revoked",
    EventType.CERTIFICATE_EXPIRING: "A certificate is about to expire",
    EventType.CA_CREATED: "A new Certificate Authority has been created",
    EventType.CA_UPDATED: "A Certificate Authority has been updated",
    EventType.CRL_REGENERATED: "A CRL has been regenerated",
    EventType.USER_LOGIN: "A user has logged in",
    EventType.USER_LOGOUT: "A user has logged out",
    EventType.SYSTEM_ALERT: "A system alert has been triggered",
    EventType.AUDIT_CRITICAL: "A critical action has been logged",
    EventType.DISCOVERY_SCAN_STARTED: "A network discovery scan has started",
    EventType.DISCOVERY_SCAN_COMPLETE: "A network discovery scan has completed",
    EventType.DISCOVERY_NEW_CERT: "A new unmanaged certificate was discovered",
    EventType.DISCOVERY_CERT_CHANGED: "A certificate on a monitored endpoint has changed",
}
