"""
Notification Service for certificate and CRL expiration alerts
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from models import db, CA, Certificate
from models.crl import CRLMetadata
from models.email_notification import NotificationConfig
from services.email_service import EmailService

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing and sending notifications"""
    
    @staticmethod
    def get_notification_config(notification_type: str) -> Optional[NotificationConfig]:
        """Get configuration for a specific notification type"""
        return NotificationConfig.query.filter_by(type=notification_type).first()
    
    @staticmethod
    def check_expiring_certificates() -> List[Dict]:
        """
        Check for certificates expiring soon
        Returns list of certificates that need notification
        """
        # Get enabled notification configs for cert expiring
        configs = NotificationConfig.query.filter_by(type='cert_expiring', enabled=True).all()
        
        if not configs:
            return []
        
        expiring_certs = []
        
        for config in configs:
            if not config.days_before:
                continue
            
            # Calculate threshold date
            threshold_date = datetime.utcnow() + timedelta(days=config.days_before)
            
            # Find certificates expiring before threshold
            certs = Certificate.query.filter(
                Certificate.valid_to <= threshold_date,
                Certificate.valid_to > datetime.utcnow()
            ).all()
            
            for cert in certs:
                days_remaining = (cert.valid_to - datetime.utcnow()).days
                expiring_certs.append({
                    'cert': cert,
                    'days_remaining': days_remaining,
                    'config': config
                })
        
        return expiring_certs
    
    @staticmethod
    def check_expiring_crls() -> List[Dict]:
        """
        Check for CRLs expiring soon
        Returns list of CRLs that need notification
        """
        configs = NotificationConfig.query.filter_by(type='crl_expiring', enabled=True).all()
        
        if not configs:
            return []
        
        expiring_crls = []
        
        for config in configs:
            if not config.days_before:
                continue
            
            threshold_date = datetime.utcnow() + timedelta(days=config.days_before)
            
            crls = CRLMetadata.query.filter(
                CRLMetadata.next_update <= threshold_date,
                CRLMetadata.next_update > datetime.utcnow()
            ).all()
            
            for crl in crls:
                days_remaining = (crl.next_update - datetime.utcnow()).days
                expiring_crls.append({
                    'crl': crl,
                    'days_remaining': days_remaining,
                    'config': config
                })
        
        return expiring_crls
    
    @staticmethod
    def send_cert_expiring_notification(cert, days_remaining: int, recipients: List[str]) -> tuple[bool, str]:
        """Send certificate expiring notification"""
        subject = f"UCM Alert: Certificate Expiring in {days_remaining} days - {cert.descr}"
        
        body_html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 8px;">
                    <h2 style="color: #ef4444; border-bottom: 2px solid #ef4444; padding-bottom: 10px;">
                        ⚠️ Certificate Expiration Alert
                    </h2>
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
                            <tr>
                                <td style="padding: 8px; font-weight: bold;">Certificate Type:</td>
                                <td style="padding: 8px;">{cert.cert_type or 'N/A'}</td>
                            </tr>
                        </table>
                    </div>
                    
                    <div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; margin: 20px 0;">
                        <strong>Action Required:</strong> Please renew or replace this certificate before it expires.
                    </div>
                    
                    <p style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 0.9em;">
                        Sent at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}<br>
                        From: UCM Notification System
                    </p>
                </div>
            </body>
        </html>
        """
        
        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type='cert_expiring',
            resource_type='certificate',
            resource_id=cert.refid
        )
    
    @staticmethod
    def send_crl_expiring_notification(crl, days_remaining: int, recipients: List[str]) -> tuple[bool, str]:
        """Send CRL expiring notification"""
        ca = CA.query.get(crl.ca_id)
        ca_name = ca.descr if ca else "Unknown CA"
        
        subject = f"UCM Alert: CRL Expiring in {days_remaining} days - {ca_name}"
        
        body_html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 8px;">
                    <h2 style="color: #f59e0b; border-bottom: 2px solid #f59e0b; padding-bottom: 10px;">
                        ⚠️ CRL Expiration Alert
                    </h2>
                    <p>A Certificate Revocation List (CRL) in your UCM instance needs to be regenerated soon.</p>
                    
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
                            <tr style="background-color: #f9f9f9;">
                                <td style="padding: 8px; font-weight: bold;">Revoked Certificates:</td>
                                <td style="padding: 8px;">{crl.revoked_count or 0}</td>
                            </tr>
                        </table>
                    </div>
                    
                    <div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; margin: 20px 0;">
                        <strong>Action Required:</strong> Please regenerate the CRL before it expires to maintain certificate validation.
                    </div>
                    
                    <p style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 0.9em;">
                        Sent at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}<br>
                        From: UCM Notification System
                    </p>
                </div>
            </body>
        </html>
        """
        
        return EmailService.send_email(
            recipients=recipients,
            subject=subject,
            body_html=body_html,
            notification_type='crl_expiring',
            resource_type='crl',
            resource_id=str(crl.id)
        )
    
    @staticmethod
    def run_notification_check():
        """
        Run notification check for all configured alerts
        This should be called by a cron job or scheduler
        """
        logger.info("Running notification check...")
        
        # Check expiring certificates
        expiring_certs = NotificationService.check_expiring_certificates()
        logger.info(f"Found {len(expiring_certs)} expiring certificates")
        
        for item in expiring_certs:
            cert = item['cert']
            days = item['days_remaining']
            config = item['config']
            
            if config.recipients:
                import json
                recipients = json.loads(config.recipients)
                if recipients:
                    success, msg = NotificationService.send_cert_expiring_notification(cert, days, recipients)
                    if success:
                        logger.info(f"Sent expiring cert notification for {cert.descr}")
                    else:
                        logger.error(f"Failed to send cert notification: {msg}")
        
        # Check expiring CRLs
        expiring_crls = NotificationService.check_expiring_crls()
        logger.info(f"Found {len(expiring_crls)} expiring CRLs")
        
        for item in expiring_crls:
            crl = item['crl']
            days = item['days_remaining']
            config = item['config']
            
            if config.recipients:
                import json
                recipients = json.loads(config.recipients)
                if recipients:
                    success, msg = NotificationService.send_crl_expiring_notification(crl, days, recipients)
                    if success:
                        logger.info(f"Sent expiring CRL notification for CA ID {crl.ca_id}")
                    else:
                        logger.error(f"Failed to send CRL notification: {msg}")
        
        logger.info("Notification check completed")
