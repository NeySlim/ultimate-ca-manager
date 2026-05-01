import json
import logging
from typing import Tuple
from models import CA, Certificate, User
from services.email_service import EmailService
from .config import NotificationConfigMixin
from .templates import NotificationTemplatesMixin
from ._constants import (
    CERT_ISSUED, CERT_REVOKED, CA_CREATED, SECURITY_ALERT, PASSWORD_CHANGED,
)

logger = logging.getLogger(__name__)


class NotificationEventsMixin:

    @staticmethod
    def on_certificate_issued(cert, issued_by=None):
        if not NotificationConfigMixin.should_send(CERT_ISSUED, 'certificate', cert.refid):
            return True, "Notification skipped (disabled or cooldown)"

        config = NotificationConfigMixin.get_config(CERT_ISSUED)
        if not config or not config.recipients:
            return True, "No recipients configured"

        recipients = json.loads(config.recipients)
        if not recipients:
            return True, "No recipients configured"

        subject = f"UCM: New Certificate Issued - {cert.descr or cert.subject}"
        body_html = NotificationTemplatesMixin._render_cert_issued_template(cert, issued_by)

        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type=CERT_ISSUED,
            resource_type='certificate',
            resource_id=cert.refid
        )

    @staticmethod
    def on_certificate_revoked(cert, reason=None, revoked_by=None):
        if not NotificationConfigMixin.should_send(CERT_REVOKED, 'certificate', cert.refid):
            return True, "Notification skipped (disabled or cooldown)"

        config = NotificationConfigMixin.get_config(CERT_REVOKED)
        if not config or not config.recipients:
            return True, "No recipients configured"

        recipients = json.loads(config.recipients)
        if not recipients:
            return True, "No recipients configured"

        subject = f"⚠️ UCM Alert: Certificate Revoked - {cert.descr or cert.subject}"
        body_html = NotificationTemplatesMixin._render_cert_revoked_template(cert, reason, revoked_by)

        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type=CERT_REVOKED,
            resource_type='certificate',
            resource_id=cert.refid
        )

    @staticmethod
    def on_ca_created(ca, created_by=None):
        if not NotificationConfigMixin.should_send(CA_CREATED, 'ca', ca.refid):
            return True, "Notification skipped (disabled or cooldown)"

        config = NotificationConfigMixin.get_config(CA_CREATED)
        if not config or not config.recipients:
            return True, "No recipients configured"

        recipients = json.loads(config.recipients)
        if not recipients:
            return True, "No recipients configured"

        subject = f"UCM: New Certificate Authority Created - {ca.descr}"
        body_html = NotificationTemplatesMixin._render_ca_created_template(ca, created_by)

        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type=CA_CREATED,
            resource_type='ca',
            resource_id=ca.refid
        )

    @staticmethod
    def on_security_alert(alert_type, username, ip_address=None, details=None):
        resource_id = f"{alert_type}:{username}"

        if not NotificationConfigMixin.should_send(SECURITY_ALERT, 'security', resource_id):
            return True, "Notification skipped (disabled or cooldown)"

        config = NotificationConfigMixin.get_config(SECURITY_ALERT)
        if not config or not config.recipients:
            return True, "No recipients configured"

        recipients = json.loads(config.recipients)
        if not recipients:
            return True, "No recipients configured"

        subject = f"🚨 UCM Security Alert: {alert_type}"
        body_html = NotificationTemplatesMixin._render_security_alert_template(
            alert_type, username, ip_address, details
        )

        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type=SECURITY_ALERT,
            resource_type='security',
            resource_id=resource_id
        )

    @staticmethod
    def on_password_changed(user, changed_by=None):
        config = NotificationConfigMixin.get_config(PASSWORD_CHANGED)
        if not config or not config.enabled:
            return True, "Notification disabled"

        if not user.email:
            return True, "User has no email address"

        subject = "UCM: Your Password Has Been Changed"
        body_html = NotificationTemplatesMixin._render_password_changed_template(user, changed_by)

        return EmailService.send_email(
            recipients=[user.email],
            subject=subject,
            body_html=body_html,
            notification_type=PASSWORD_CHANGED,
            resource_type='user',
            resource_id=str(user.id)
        )
