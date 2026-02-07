"""
Certificate Expiry Alert Service
Monitors certificates and sends email alerts before expiration
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from models import db, Certificate
from services.email_service import EmailService

logger = logging.getLogger(__name__)


class ExpiryAlertSettings:
    """Configuration for certificate expiry alerts"""
    
    # Singleton settings
    _settings: Dict[str, Any] = {
        'enabled': True,
        'alert_days': [30, 14, 7, 1],  # Days before expiry to alert
        'include_revoked': False,
        'recipients': [],  # Additional recipients (besides cert contacts)
        'last_run': None,
        'total_alerts_sent': 0
    }
    
    @classmethod
    def get_settings(cls) -> Dict[str, Any]:
        return cls._settings.copy()
    
    @classmethod
    def update_settings(cls, **kwargs) -> Dict[str, Any]:
        if 'enabled' in kwargs:
            cls._settings['enabled'] = bool(kwargs['enabled'])
        if 'alert_days' in kwargs:
            days = kwargs['alert_days']
            if isinstance(days, list):
                cls._settings['alert_days'] = sorted([int(d) for d in days if d > 0], reverse=True)
        if 'include_revoked' in kwargs:
            cls._settings['include_revoked'] = bool(kwargs['include_revoked'])
        if 'recipients' in kwargs:
            cls._settings['recipients'] = list(kwargs['recipients'])
        
        logger.info(f"Expiry alert settings updated: {cls._settings}")
        return cls._settings.copy()


def get_expiring_certificates(days: int = 30, include_revoked: bool = False) -> List[Dict[str, Any]]:
    """
    Get certificates expiring within specified days
    
    Args:
        days: Number of days to look ahead
        include_revoked: Include revoked certificates
        
    Returns:
        List of certificate info dicts
    """
    now = datetime.utcnow()
    cutoff = now + timedelta(days=days)
    
    query = Certificate.query.filter(
        Certificate.valid_to <= cutoff,
        Certificate.valid_to > now
    )
    
    if not include_revoked:
        query = query.filter(
            db.or_(Certificate.revoked == False, Certificate.revoked == None)
        )
    
    certs = query.order_by(Certificate.valid_to.asc()).all()
    
    result = []
    for cert in certs:
        days_until = (cert.valid_to - now).days if cert.valid_to else 0
        result.append({
            'id': cert.id,
            'serial_number': cert.serial_number,
            'common_name': cert.descr,  # descr is used as common name
            'subject': cert.subject,
            'valid_to': cert.valid_to.isoformat() if cert.valid_to else None,
            'days_until_expiry': days_until,
            'issuer_ca_id': cert.caref,
            'revoked': cert.revoked or False
        })
    
    return result


def check_and_send_alerts() -> Dict[str, Any]:
    """
    Check for expiring certificates and send alerts
    
    Returns:
        Dict with alert results
    """
    settings = ExpiryAlertSettings._settings
    
    if not settings['enabled']:
        return {'status': 'disabled', 'alerts_sent': 0}
    
    # Get SMTP config
    smtp_config = EmailService.get_smtp_config()
    if not smtp_config or not smtp_config.enabled:
        logger.warning("SMTP not configured, cannot send expiry alerts")
        return {'status': 'smtp_disabled', 'alerts_sent': 0}
    
    alerts_sent = 0
    errors = []
    certificates_alerted = []
    
    for alert_days in settings['alert_days']:
        # Get certs expiring in exactly alert_days (±1 day to avoid duplicates)
        certs = get_expiring_certificates(
            days=alert_days + 1,
            include_revoked=settings['include_revoked']
        )
        
        # Filter to certs expiring in alert_days range
        for cert in certs:
            days_left = cert['days_until_expiry']
            
            # Only alert if days_left matches this alert threshold
            # Allow ±1 day tolerance for daily checks
            if days_left <= alert_days and days_left > (alert_days - 7 if alert_days > 7 else 0):
                # Skip if already alerted at a later threshold
                if cert['id'] in certificates_alerted:
                    continue
                
                # Determine recipients
                recipients = list(settings['recipients']) if settings['recipients'] else []
                
                # Add admin email from SMTP config if set
                if smtp_config.smtp_from:
                    admin_email = smtp_config.admin_email or smtp_config.smtp_from
                    if admin_email not in recipients:
                        recipients.append(admin_email)
                
                if not recipients:
                    logger.warning(f"No recipients for expiry alert cert={cert['id']}")
                    continue
                
                # Send alert
                success, msg = send_expiry_alert(cert, days_left, recipients)
                
                if success:
                    alerts_sent += 1
                    certificates_alerted.append(cert['id'])
                else:
                    errors.append(f"Cert {cert['id']}: {msg}")
    
    # Update stats
    ExpiryAlertSettings._settings['last_run'] = datetime.utcnow().isoformat()
    ExpiryAlertSettings._settings['total_alerts_sent'] += alerts_sent
    
    result = {
        'status': 'completed',
        'alerts_sent': alerts_sent,
        'certificates_checked': len(certificates_alerted),
        'errors': errors if errors else None
    }
    
    logger.info(f"Expiry alert check complete: {alerts_sent} alerts sent")
    return result


def send_expiry_alert(cert: Dict[str, Any], days_left: int, recipients: List[str]) -> tuple[bool, str]:
    """
    Send expiry alert email for a certificate
    
    Args:
        cert: Certificate info dict
        days_left: Days until expiration
        recipients: Email recipients
        
    Returns:
        (success, message)
    """
    urgency = "URGENT" if days_left <= 7 else "WARNING"
    urgency_color = "#dc2626" if days_left <= 7 else "#f59e0b"
    
    subject = f"[UCM] {urgency}: Certificate expires in {days_left} days - {cert['common_name']}"
    
    body_html = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; padding: 20px; border-radius: 8px 8px 0 0;">
                <h2 style="margin: 0;">🔐 Certificate Expiry Alert</h2>
            </div>
            
            <div style="padding: 20px; background: #f9fafb; border: 1px solid #e5e7eb; border-top: none;">
                <div style="background: {urgency_color}; color: white; padding: 12px 16px; border-radius: 6px; margin-bottom: 20px;">
                    <strong>{urgency}:</strong> This certificate expires in <strong>{days_left} day(s)</strong>
                </div>
                
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;"><strong>Common Name:</strong></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;">{cert['common_name']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;"><strong>Subject:</strong></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;">{cert['subject']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;"><strong>Serial Number:</strong></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;"><code>{cert['serial_number']}</code></td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;"><strong>Expires On:</strong></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #e5e7eb;">{cert['valid_to']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0;"><strong>Certificate ID:</strong></td>
                        <td style="padding: 8px 0;">#{cert['id']}</td>
                    </tr>
                </table>
                
                <div style="margin-top: 20px; padding: 16px; background: #dbeafe; border-radius: 6px; border-left: 4px solid #3b82f6;">
                    <strong>Action Required:</strong><br>
                    Please renew or replace this certificate before it expires to avoid service disruption.
                </div>
            </div>
            
            <div style="padding: 16px; background: #f3f4f6; border-radius: 0 0 8px 8px; text-align: center; font-size: 0.85em; color: #6b7280;">
                Sent by Ultimate CA Manager<br>
                <em>Automated certificate expiry monitoring</em>
            </div>
        </body>
    </html>
    """
    
    body_text = f"""
Certificate Expiry Alert - {urgency}

This certificate expires in {days_left} day(s)!

Common Name: {cert['common_name']}
Subject: {cert['subject']}
Serial Number: {cert['serial_number']}
Expires On: {cert['valid_to']}
Certificate ID: #{cert['id']}

Action Required:
Please renew or replace this certificate before it expires to avoid service disruption.

---
Sent by Ultimate CA Manager
    """
    
    return EmailService.send_email(
        recipients=recipients,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        notification_type='cert_expiry',
        resource_type='certificate',
        resource_id=str(cert['id'])
    )


def scheduled_expiry_check():
    """Scheduled task for automatic expiry checking"""
    result = check_and_send_alerts()
    logger.info(f"Scheduled expiry check: {result}")
