import logging
from models import CA, Certificate, User
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class NotificationTemplatesMixin:

    @staticmethod
    def _base_template(title, title_color, content):
        from services.email_templates import render_template
        from models.email_notification import SMTPConfig

        smtp = SMTPConfig.query.first()
        custom_template = smtp.email_template if smtp else None

        return render_template(custom_template, title, title_color, content)

    @staticmethod
    def _render_cert_issued_template(cert, issued_by=None):
        content = f"""
        <p>A new certificate has been issued in your UCM instance.</p>

        <div style="background-color: white; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #3b82f6;">Certificate Details</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Subject:</td>
                    <td style="padding: 8px;">{cert.subject or cert.descr}</td>
                </tr>
                <tr style="background-color: #f9f9f9;">
                    <td style="padding: 8px; font-weight: bold;">Valid From:</td>
                    <td style="padding: 8px;">{cert.valid_from.strftime('%Y-%m-%d') if cert.valid_from else 'N/A'}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Valid Until:</td>
                    <td style="padding: 8px;">{cert.valid_to.strftime('%Y-%m-%d') if cert.valid_to else 'N/A'}</td>
                </tr>
                <tr style="background-color: #f9f9f9;">
                    <td style="padding: 8px; font-weight: bold;">Type:</td>
                    <td style="padding: 8px;">{cert.cert_type or 'N/A'}</td>
                </tr>
                {f'<tr><td style="padding: 8px; font-weight: bold;">Issued By:</td><td style="padding: 8px;">{issued_by}</td></tr>' if issued_by else ''}
            </table>
        </div>
        """
        return NotificationTemplatesMixin._base_template("✅ New Certificate Issued", "#22c55e", content)

    @staticmethod
    def _render_cert_revoked_template(cert, reason=None, revoked_by=None):
        content = f"""
        <p>A certificate has been revoked in your UCM instance.</p>

        <div style="background-color: white; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #ef4444;">Revoked Certificate</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Subject:</td>
                    <td style="padding: 8px;">{cert.subject or cert.descr}</td>
                </tr>
                <tr style="background-color: #f9f9f9;">
                    <td style="padding: 8px; font-weight: bold;">Serial Number:</td>
                    <td style="padding: 8px;">{cert.serial or 'N/A'}</td>
                </tr>
                {f'<tr><td style="padding: 8px; font-weight: bold;">Reason:</td><td style="padding: 8px; color: #ef4444;">{reason}</td></tr>' if reason else ''}
                {f'<tr style="background-color: #f9f9f9;"><td style="padding: 8px; font-weight: bold;">Revoked By:</td><td style="padding: 8px;">{revoked_by}</td></tr>' if revoked_by else ''}
            </table>
        </div>

        <div style="background-color: #fee2e2; border-left: 4px solid #ef4444; padding: 12px; margin: 20px 0;">
            <strong>Important:</strong> This certificate is no longer valid and should not be trusted.
        </div>
        """
        return NotificationTemplatesMixin._base_template("⚠️ Certificate Revoked", "#ef4444", content)

    @staticmethod
    def _render_ca_created_template(ca, created_by=None):
        content = f"""
        <p>A new Certificate Authority has been created in your UCM instance.</p>

        <div style="background-color: white; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #3b82f6;">CA Details</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Name:</td>
                    <td style="padding: 8px;">{ca.descr}</td>
                </tr>
                <tr style="background-color: #f9f9f9;">
                    <td style="padding: 8px; font-weight: bold;">Type:</td>
                    <td style="padding: 8px;">{'Root CA' if not ca.caref else 'Intermediate CA'}</td>
                </tr>
                {f'<tr><td style="padding: 8px; font-weight: bold;">Created By:</td><td style="padding: 8px;">{created_by}</td></tr>' if created_by else ''}
            </table>
        </div>
        """
        return NotificationTemplatesMixin._base_template("🏛️ New Certificate Authority", "#3b82f6", content)

    @staticmethod
    def _render_security_alert_template(alert_type, username, ip_address=None, details=None):
        content = f"""
        <p>A security event has been detected in your UCM instance.</p>

        <div style="background-color: white; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #ef4444;">Security Event</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Event Type:</td>
                    <td style="padding: 8px; color: #ef4444; font-weight: bold;">{alert_type}</td>
                </tr>
                <tr style="background-color: #f9f9f9;">
                    <td style="padding: 8px; font-weight: bold;">Username:</td>
                    <td style="padding: 8px;">{username}</td>
                </tr>
                {f'<tr><td style="padding: 8px; font-weight: bold;">IP Address:</td><td style="padding: 8px;">{ip_address}</td></tr>' if ip_address else ''}
                {f'<tr style="background-color: #f9f9f9;"><td style="padding: 8px; font-weight: bold;">Details:</td><td style="padding: 8px;">{details}</td></tr>' if details else ''}
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Time:</td>
                    <td style="padding: 8px;">{utc_now().strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
                </tr>
            </table>
        </div>

        <div style="background-color: #fee2e2; border-left: 4px solid #ef4444; padding: 12px; margin: 20px 0;">
            <strong>Action Required:</strong> Please investigate this security event.
        </div>
        """
        return NotificationTemplatesMixin._base_template("🚨 Security Alert", "#ef4444", content)

    @staticmethod
    def _render_password_changed_template(user, changed_by=None):
        content = f"""
        <p>Your password has been changed.</p>

        <div style="background-color: white; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Account:</td>
                    <td style="padding: 8px;">{user.username}</td>
                </tr>
                <tr style="background-color: #f9f9f9;">
                    <td style="padding: 8px; font-weight: bold;">Changed At:</td>
                    <td style="padding: 8px;">{utc_now().strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
                </tr>
                {f'<tr><td style="padding: 8px; font-weight: bold;">Changed By:</td><td style="padding: 8px;">{changed_by}</td></tr>' if changed_by else ''}
            </table>
        </div>

        <div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; margin: 20px 0;">
            <strong>Note:</strong> If you did not request this change, please contact your administrator immediately.
        </div>
        """
        return NotificationTemplatesMixin._base_template("🔐 Password Changed", "#3b82f6", content)

    @staticmethod
    def _render_password_reset_template(context):
        username = context.get('username', 'User')
        reset_url = context.get('reset_url', '#')
        expires_in = context.get('expires_in', '1 hour')
        ip_address = context.get('ip_address', 'Unknown')

        content = f"""
        <p>Hello <strong>{username}</strong>,</p>

        <p>We received a request to reset your password. Click the button below to create a new password:</p>

        <p style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}"
               style="background: #2563eb; color: white; padding: 12px 32px;
                      text-decoration: none; border-radius: 6px; font-weight: 500;">
                Reset Password
            </a>
        </p>

        <p style="color: #666; font-size: 13px;">
            Or copy and paste this link into your browser:<br>
            <a href="{reset_url}" style="color: #2563eb; word-break: break-all;">{reset_url}</a>
        </p>

        <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">

        <p style="color: #666; font-size: 13px;">
            <strong>Security Details:</strong><br>
            • This link expires in <strong>{expires_in}</strong><br>
            • Request originated from IP: {ip_address}<br>
            • If you didn't request this, you can safely ignore this email
        </p>
        """
        return NotificationTemplatesMixin._base_template(
            'Password Reset Request',
            '#f59e0b',
            content
        )
