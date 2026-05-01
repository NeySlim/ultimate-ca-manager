import logging
from typing import List, Tuple
from models import CA
from services.email_service import EmailService
from .templates import NotificationTemplatesMixin
from ._constants import CERT_EXPIRING, CRL_EXPIRING

logger = logging.getLogger(__name__)


class NotificationSenderMixin:

    @staticmethod
    def send_cert_expiring_notification(cert, days_remaining, recipients):
        subject = f"UCM Alert: Certificate Expiring in {days_remaining} days - {cert.descr}"

        content = f"""
        <p>A certificate in your UCM instance is expiring soon.</p>

        <div style="background-color: white; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #3b82f6;">Certificate Details</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Description:</td>
                    <td style="padding: 8px;">{cert.descr}</td>
                </tr>
                <tr style="background-color: #f9f9f9;">
                    <td style="padding: 8px; font-weight: bold;">Subject:</td>
                    <td style="padding: 8px;">{cert.subject or 'N/A'}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Expires:</td>
                    <td style="padding: 8px; color: #ef4444; font-weight: bold;">
                        {cert.valid_to.strftime('%Y-%m-%d %H:%M:%S UTC') if cert.valid_to else 'N/A'}
                    </td>
                </tr>
                <tr style="background-color: #f9f9f9;">
                    <td style="padding: 8px; font-weight: bold;">Days Remaining:</td>
                    <td style="padding: 8px; color: #ef4444; font-weight: bold; font-size: 1.2em;">
                        {days_remaining} days
                    </td>
                </tr>
            </table>
        </div>

        <div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; margin: 20px 0;">
            <strong>Action Required:</strong> Please renew or replace this certificate before it expires.
        </div>
        """

        body_html = NotificationTemplatesMixin._base_template(
            "⚠️ Certificate Expiration Alert", "#ef4444", content
        )

        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type=CERT_EXPIRING,
            resource_type='certificate',
            resource_id=cert.refid
        )

    @staticmethod
    def send_crl_expiring_notification(crl, days_remaining, recipients):
        ca = CA.query.get(crl.ca_id)
        ca_name = ca.descr if ca else "Unknown CA"

        subject = f"UCM Alert: CRL Expiring in {days_remaining} days - {ca_name}"

        content = f"""
        <p>A Certificate Revocation List (CRL) needs to be regenerated soon.</p>

        <div style="background-color: white; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #3b82f6;">CRL Details</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Certificate Authority:</td>
                    <td style="padding: 8px;">{ca_name}</td>
                </tr>
                <tr style="background-color: #f9f9f9;">
                    <td style="padding: 8px; font-weight: bold;">Next Update:</td>
                    <td style="padding: 8px; color: #f59e0b; font-weight: bold;">
                        {crl.next_update.strftime('%Y-%m-%d %H:%M:%S UTC') if crl.next_update else 'N/A'}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Days Remaining:</td>
                    <td style="padding: 8px; color: #f59e0b; font-weight: bold; font-size: 1.2em;">
                        {days_remaining} days
                    </td>
                </tr>
            </table>
        </div>

        <div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; margin: 20px 0;">
            <strong>Action Required:</strong> Please regenerate the CRL before it expires.
        </div>
        """

        body_html = NotificationTemplatesMixin._base_template(
            "⚠️ CRL Expiration Alert", "#f59e0b", content
        )

        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type=CRL_EXPIRING,
            resource_type='crl',
            resource_id=str(crl.id)
        )

    @staticmethod
    def send_test_email(recipient):
        success, _ = EmailService.send_test_email(recipient)
        return success

    @staticmethod
    def send_test_email_with_detail(recipient):
        return EmailService.send_test_email(recipient)

    @staticmethod
    def send_email(to, subject, template, context):
        if template == 'password_reset':
            html_body = NotificationTemplatesMixin._render_password_reset_template(context)
        else:
            html_body = NotificationTemplatesMixin._base_template(
                subject,
                '#2563eb',
                f"<p>{context.get('message', '')}</p>"
            )

        success, _ = EmailService.send_email(
            recipients=[to],
            subject=subject,
            body_html=html_body
        )
        return success
