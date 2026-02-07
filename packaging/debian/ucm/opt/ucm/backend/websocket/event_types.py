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
}
