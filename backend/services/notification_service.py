"""
Enhanced Notification Service for UCM
Handles all types of notifications with deduplication and retry logic
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from models import db, CA, Certificate, User
from models.crl import CRLMetadata
from models.email_notification import NotificationConfig, NotificationLog
from services.email_service import EmailService

logger = logging.getLogger(__name__)


class NotificationService:
    """Enhanced notification service with deduplication and event triggers"""
    
    # Notification types
    CERT_EXPIRING = 'cert_expiring'
    CERT_ISSUED = 'cert_issued'
    CERT_REVOKED = 'cert_revoked'
    CRL_EXPIRING = 'crl_expiring'
    CA_CREATED = 'ca_created'
    SECURITY_ALERT = 'security_alert'
    PASSWORD_CHANGED = 'password_changed'
    DAILY_DIGEST = 'daily_digest'
    
    # ============ Configuration ============
    
    @staticmethod
    def get_config(notification_type: str) -> Optional[NotificationConfig]:
        """Get configuration for a notification type"""
        return NotificationConfig.query.filter_by(type=notification_type).first()
    
    @staticmethod
    def get_all_configs() -> List[NotificationConfig]:
        """Get all notification configurations"""
        return NotificationConfig.query.all()
    
    @staticmethod
    def create_default_configs():
        """Create default notification configurations if they don't exist"""
        defaults = [
            {
                'type': NotificationService.CERT_EXPIRING,
                'description': 'Alert when certificates are about to expire',
                'days_before': 30,
                'cooldown_hours': 24,
                'enabled': True,
            },
            {
                'type': NotificationService.CRL_EXPIRING,
                'description': 'Alert when CRLs need to be regenerated',
                'days_before': 7,
                'cooldown_hours': 24,
                'enabled': True,
            },
            {
                'type': NotificationService.CERT_ISSUED,
                'description': 'Notify when new certificates are issued',
                'cooldown_hours': 0,  # No cooldown - always send
                'enabled': False,
            },
            {
                'type': NotificationService.CERT_REVOKED,
                'description': 'Alert when certificates are revoked',
                'cooldown_hours': 0,
                'enabled': True,
            },
            {
                'type': NotificationService.CA_CREATED,
                'description': 'Notify when new CAs are created',
                'cooldown_hours': 0,
                'enabled': False,
            },
            {
                'type': NotificationService.SECURITY_ALERT,
                'description': 'Security alerts (failed logins, account lockouts)',
                'cooldown_hours': 1,  # Max 1 alert per hour per event
                'enabled': True,
            },
            {
                'type': NotificationService.PASSWORD_CHANGED,
                'description': 'Notify users when their password is changed',
                'cooldown_hours': 0,
                'enabled': True,
            },
        ]
        
        for default in defaults:
            if not NotificationConfig.query.filter_by(type=default['type']).first():
                config = NotificationConfig(
                    type=default['type'],
                    description=default['description'],
                    days_before=default.get('days_before'),
                    cooldown_hours=default.get('cooldown_hours', 24),
                    enabled=default['enabled'],
                    recipients='[]'
                )
                db.session.add(config)
        
        try:
            db.session.commit()
            logger.info("Default notification configurations created")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create default configs: {e}")
    
    # ============ Deduplication ============
    
    @staticmethod
    def should_send(notification_type: str, resource_type: str, resource_id: str) -> bool:
        """Check if notification should be sent (deduplication)"""
        config = NotificationService.get_config(notification_type)
        if not config or not config.enabled:
            return False
        
        cooldown = config.cooldown_hours or 24
        if cooldown == 0:
            return True  # No cooldown, always send
        
        return not NotificationLog.was_recently_sent(
            notification_type, resource_type, resource_id, cooldown
        )
    
    # ============ Event Triggers ============
    
    @staticmethod
    def on_certificate_issued(cert: Certificate, issued_by: str = None) -> Tuple[bool, str]:
        """Trigger notification when certificate is issued"""
        if not NotificationService.should_send(
            NotificationService.CERT_ISSUED, 'certificate', cert.refid
        ):
            return True, "Notification skipped (disabled or cooldown)"
        
        config = NotificationService.get_config(NotificationService.CERT_ISSUED)
        if not config or not config.recipients:
            return True, "No recipients configured"
        
        recipients = json.loads(config.recipients)
        if not recipients:
            return True, "No recipients configured"
        
        subject = f"UCM: New Certificate Issued - {cert.descr or cert.subject}"
        body_html = NotificationService._render_cert_issued_template(cert, issued_by)
        
        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type=NotificationService.CERT_ISSUED,
            resource_type='certificate',
            resource_id=cert.refid
        )
    
    @staticmethod
    def on_certificate_revoked(cert: Certificate, reason: str = None, revoked_by: str = None) -> Tuple[bool, str]:
        """Trigger notification when certificate is revoked"""
        if not NotificationService.should_send(
            NotificationService.CERT_REVOKED, 'certificate', cert.refid
        ):
            return True, "Notification skipped (disabled or cooldown)"
        
        config = NotificationService.get_config(NotificationService.CERT_REVOKED)
        if not config or not config.recipients:
            return True, "No recipients configured"
        
        recipients = json.loads(config.recipients)
        if not recipients:
            return True, "No recipients configured"
        
        subject = f"⚠️ UCM Alert: Certificate Revoked - {cert.descr or cert.subject}"
        body_html = NotificationService._render_cert_revoked_template(cert, reason, revoked_by)
        
        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type=NotificationService.CERT_REVOKED,
            resource_type='certificate',
            resource_id=cert.refid
        )
    
    @staticmethod
    def on_ca_created(ca: CA, created_by: str = None) -> Tuple[bool, str]:
        """Trigger notification when CA is created"""
        if not NotificationService.should_send(
            NotificationService.CA_CREATED, 'ca', ca.refid
        ):
            return True, "Notification skipped (disabled or cooldown)"
        
        config = NotificationService.get_config(NotificationService.CA_CREATED)
        if not config or not config.recipients:
            return True, "No recipients configured"
        
        recipients = json.loads(config.recipients)
        if not recipients:
            return True, "No recipients configured"
        
        subject = f"UCM: New Certificate Authority Created - {ca.descr}"
        body_html = NotificationService._render_ca_created_template(ca, created_by)
        
        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type=NotificationService.CA_CREATED,
            resource_type='ca',
            resource_id=ca.refid
        )
    
    @staticmethod
    def on_security_alert(
        alert_type: str,
        username: str,
        ip_address: str = None,
        details: str = None
    ) -> Tuple[bool, str]:
        """Trigger security alert notification"""
        resource_id = f"{alert_type}:{username}"
        
        if not NotificationService.should_send(
            NotificationService.SECURITY_ALERT, 'security', resource_id
        ):
            return True, "Notification skipped (disabled or cooldown)"
        
        config = NotificationService.get_config(NotificationService.SECURITY_ALERT)
        if not config or not config.recipients:
            return True, "No recipients configured"
        
        recipients = json.loads(config.recipients)
        if not recipients:
            return True, "No recipients configured"
        
        subject = f"🚨 UCM Security Alert: {alert_type}"
        body_html = NotificationService._render_security_alert_template(
            alert_type, username, ip_address, details
        )
        
        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type=NotificationService.SECURITY_ALERT,
            resource_type='security',
            resource_id=resource_id
        )
    
    @staticmethod
    def on_password_changed(user: User, changed_by: str = None) -> Tuple[bool, str]:
        """Notify user when their password is changed"""
        config = NotificationService.get_config(NotificationService.PASSWORD_CHANGED)
        if not config or not config.enabled:
            return True, "Notification disabled"
        
        if not user.email:
            return True, "User has no email address"
        
        subject = "UCM: Your Password Has Been Changed"
        body_html = NotificationService._render_password_changed_template(user, changed_by)
        
        return EmailService.send_email(
            recipients=[user.email],
            subject=subject,
            body_html=body_html,
            notification_type=NotificationService.PASSWORD_CHANGED,
            resource_type='user',
            resource_id=str(user.id)
        )
    
    # ============ Scheduled Checks ============
    
    @staticmethod
    def check_expiring_certificates() -> List[Dict]:
        """Check for certificates expiring soon"""
        config = NotificationService.get_config(NotificationService.CERT_EXPIRING)
        if not config or not config.enabled or not config.days_before:
            return []
        
        threshold_date = datetime.utcnow() + timedelta(days=config.days_before)
        
        certs = Certificate.query.filter(
            Certificate.valid_to <= threshold_date,
            Certificate.valid_to > datetime.utcnow(),
            Certificate.revoked == False
        ).all()
        
        expiring = []
        for cert in certs:
            # Check deduplication
            if NotificationService.should_send(
                NotificationService.CERT_EXPIRING, 'certificate', cert.refid
            ):
                days_remaining = (cert.valid_to - datetime.utcnow()).days
                expiring.append({
                    'cert': cert,
                    'days_remaining': days_remaining
                })
        
        return expiring
    
    @staticmethod
    def check_expiring_crls() -> List[Dict]:
        """Check for CRLs expiring soon"""
        config = NotificationService.get_config(NotificationService.CRL_EXPIRING)
        if not config or not config.enabled or not config.days_before:
            return []
        
        threshold_date = datetime.utcnow() + timedelta(days=config.days_before)
        
        crls = CRLMetadata.query.filter(
            CRLMetadata.next_update <= threshold_date,
            CRLMetadata.next_update > datetime.utcnow()
        ).all()
        
        expiring = []
        for crl in crls:
            if NotificationService.should_send(
                NotificationService.CRL_EXPIRING, 'crl', str(crl.id)
            ):
                days_remaining = (crl.next_update - datetime.utcnow()).days
                expiring.append({
                    'crl': crl,
                    'days_remaining': days_remaining
                })
        
        return expiring
    
    @staticmethod
    def run_scheduled_checks() -> Dict:
        """Run all scheduled notification checks"""
        logger.info("Running scheduled notification checks...")
        results = {
            'cert_expiring': {'checked': 0, 'notified': 0, 'failed': 0},
            'crl_expiring': {'checked': 0, 'notified': 0, 'failed': 0},
        }
        
        # Certificate expiration check
        config = NotificationService.get_config(NotificationService.CERT_EXPIRING)
        if config and config.enabled and config.recipients:
            recipients = json.loads(config.recipients)
            expiring_certs = NotificationService.check_expiring_certificates()
            results['cert_expiring']['checked'] = len(expiring_certs)
            
            for item in expiring_certs:
                cert = item['cert']
                days = item['days_remaining']
                
                success, msg = NotificationService.send_cert_expiring_notification(
                    cert, days, recipients
                )
                if success:
                    results['cert_expiring']['notified'] += 1
                else:
                    results['cert_expiring']['failed'] += 1
                    logger.error(f"Failed to send cert notification: {msg}")
        
        # CRL expiration check
        config = NotificationService.get_config(NotificationService.CRL_EXPIRING)
        if config and config.enabled and config.recipients:
            recipients = json.loads(config.recipients)
            expiring_crls = NotificationService.check_expiring_crls()
            results['crl_expiring']['checked'] = len(expiring_crls)
            
            for item in expiring_crls:
                crl = item['crl']
                days = item['days_remaining']
                
                success, msg = NotificationService.send_crl_expiring_notification(
                    crl, days, recipients
                )
                if success:
                    results['crl_expiring']['notified'] += 1
                else:
                    results['crl_expiring']['failed'] += 1
                    logger.error(f"Failed to send CRL notification: {msg}")
        
        logger.info(f"Notification check completed: {results}")
        return results
    
    # ============ Email Templates ============
    
    @staticmethod
    def _base_template(title: str, title_color: str, content: str) -> str:
        """Base HTML template for all emails"""
        return f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background-color: #f9f9f9; border-radius: 8px; padding: 20px;">
                        <h2 style="color: {title_color}; border-bottom: 2px solid {title_color}; padding-bottom: 10px; margin-top: 0;">
                            {title}
                        </h2>
                        {content}
                        <p style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 0.9em;">
                            Sent at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}<br>
                            From: UCM Notification System
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """
    
    @staticmethod
    def _render_cert_issued_template(cert: Certificate, issued_by: str = None) -> str:
        """Render certificate issued notification template"""
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
        return NotificationService._base_template("✅ New Certificate Issued", "#22c55e", content)
    
    @staticmethod
    def _render_cert_revoked_template(cert: Certificate, reason: str = None, revoked_by: str = None) -> str:
        """Render certificate revoked notification template"""
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
        return NotificationService._base_template("⚠️ Certificate Revoked", "#ef4444", content)
    
    @staticmethod
    def _render_ca_created_template(ca: CA, created_by: str = None) -> str:
        """Render CA created notification template"""
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
        return NotificationService._base_template("🏛️ New Certificate Authority", "#3b82f6", content)
    
    @staticmethod
    def _render_security_alert_template(
        alert_type: str,
        username: str,
        ip_address: str = None,
        details: str = None
    ) -> str:
        """Render security alert notification template"""
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
                    <td style="padding: 8px;">{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
                </tr>
            </table>
        </div>
        
        <div style="background-color: #fee2e2; border-left: 4px solid #ef4444; padding: 12px; margin: 20px 0;">
            <strong>Action Required:</strong> Please investigate this security event.
        </div>
        """
        return NotificationService._base_template("🚨 Security Alert", "#ef4444", content)
    
    @staticmethod
    def _render_password_changed_template(user: User, changed_by: str = None) -> str:
        """Render password changed notification template"""
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
                    <td style="padding: 8px;">{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
                </tr>
                {f'<tr><td style="padding: 8px; font-weight: bold;">Changed By:</td><td style="padding: 8px;">{changed_by}</td></tr>' if changed_by else ''}
            </table>
        </div>
        
        <div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; margin: 20px 0;">
            <strong>Note:</strong> If you did not request this change, please contact your administrator immediately.
        </div>
        """
        return NotificationService._base_template("🔐 Password Changed", "#3b82f6", content)
    
    # Legacy methods for backward compatibility
    @staticmethod
    def send_cert_expiring_notification(cert, days_remaining: int, recipients: List[str]) -> Tuple[bool, str]:
        """Send certificate expiring notification"""
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
        
        body_html = NotificationService._base_template("⚠️ Certificate Expiration Alert", "#ef4444", content)
        
        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type=NotificationService.CERT_EXPIRING,
            resource_type='certificate',
            resource_id=cert.refid
        )
    
    @staticmethod
    def send_crl_expiring_notification(crl, days_remaining: int, recipients: List[str]) -> Tuple[bool, str]:
        """Send CRL expiring notification"""
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
        
        body_html = NotificationService._base_template("⚠️ CRL Expiration Alert", "#f59e0b", content)
        
        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type=NotificationService.CRL_EXPIRING,
            resource_type='crl',
            resource_id=str(crl.id)
        )
    
    @staticmethod
    def send_test_email(recipient: str) -> bool:
        """Send a test email to verify SMTP configuration"""
        success, _ = EmailService.send_test_email(recipient)
        return success

    @staticmethod
    def send_email(to: str, subject: str, template: str, context: dict) -> bool:
        """
        Send templated email
        
        Args:
            to: Recipient email
            subject: Email subject
            template: Template name (password_reset, etc.)
            context: Variables for template
        """
        # Generate HTML based on template
        if template == 'password_reset':
            html_body = NotificationService._render_password_reset_template(context)
        else:
            # Generic template
            html_body = NotificationService._base_template(
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

    @staticmethod
    def _render_password_reset_template(context: dict) -> str:
        """Render password reset email template"""
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
        
        return NotificationService._base_template(
            'Password Reset Request',
            '#f59e0b',  # Warning/amber color
            content
        )
