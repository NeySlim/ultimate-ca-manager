"""
Notification service package.
"""
from ._constants import (
    CERT_EXPIRING, CERT_ISSUED, CERT_REVOKED, CRL_EXPIRING,
    CA_CREATED, SECURITY_ALERT, PASSWORD_CHANGED, DAILY_DIGEST,
)
from .config import NotificationConfigMixin
from .templates import NotificationTemplatesMixin
from .events import NotificationEventsMixin
from .sender import NotificationSenderMixin
from .scheduler import NotificationSchedulerMixin


class NotificationService(
    NotificationConfigMixin,
    NotificationEventsMixin,
    NotificationSchedulerMixin,
    NotificationTemplatesMixin,
    NotificationSenderMixin,
):
    """Enhanced notification service with deduplication and event triggers"""

    CERT_EXPIRING = CERT_EXPIRING
    CERT_ISSUED = CERT_ISSUED
    CERT_REVOKED = CERT_REVOKED
    CRL_EXPIRING = CRL_EXPIRING
    CA_CREATED = CA_CREATED
    SECURITY_ALERT = SECURITY_ALERT
    PASSWORD_CHANGED = PASSWORD_CHANGED
    DAILY_DIGEST = DAILY_DIGEST
