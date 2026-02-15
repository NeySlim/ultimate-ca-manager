"""
Email Service for sending notifications via SMTP
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional, Dict
from datetime import datetime
from models import db
from models.email_notification import SMTPConfig, NotificationLog

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email notifications"""
    
    @staticmethod
    def get_smtp_config() -> Optional[SMTPConfig]:
        """Get SMTP configuration from database"""
        return SMTPConfig.query.first()
    
    @staticmethod
    def test_connection(config: SMTPConfig = None) -> tuple[bool, str]:
        """
        Test SMTP connection
        Returns: (success: bool, message: str)
        """
        if not config:
            config = EmailService.get_smtp_config()
        
        if not config:
            return False, "SMTP configuration not found"
        
        if not config.enabled:
            return False, "SMTP is disabled"
        
        if not all([config.smtp_host, config.smtp_port, config.smtp_from]):
            return False, "SMTP configuration incomplete (host, port, from required)"
        
        try:
            # Try to connect
            if config.smtp_use_ssl:
                server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10)
                if config.smtp_use_tls:
                    server.starttls()
            
            # Login if credentials provided
            if config.smtp_user and config.smtp_password:
                server.login(config.smtp_user, config.smtp_password)
            
            server.quit()
            return True, "SMTP connection successful"
            
        except smtplib.SMTPAuthenticationError as e:
            return False, f"SMTP authentication failed: {str(e)}"
        except smtplib.SMTPConnectError as e:
            return False, f"SMTP connection failed: {str(e)}"
        except Exception as e:
            return False, f"SMTP error: {str(e)}"
    
    @staticmethod
    def send_email(
        recipients: List[str],
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
        notification_type: str = "general",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Send email to recipients
        
        Args:
            recipients: List of email addresses
            subject: Email subject
            body_html: HTML body content
            body_text: Plain text body (optional, will be generated from HTML if not provided)
            notification_type: Type of notification for logging
            resource_type: Type of resource (certificate, ca, crl)
            resource_id: ID of resource
            
        Returns:
            (success: bool, message: str)
        """
        config = EmailService.get_smtp_config()
        
        if not config or not config.enabled:
            return False, "SMTP is not configured or disabled"
        
        if not recipients:
            return False, "No recipients specified"
        
        try:
            # Determine content type from config
            content_type = getattr(config, 'smtp_content_type', 'html') or 'html'
            
            if content_type == 'text':
                # Plain text only
                plain = body_text or body_html.replace('<br>', '\n').replace('</p>', '\n')
                import re
                plain = re.sub(r'<[^>]+>', '', plain)
                msg = MIMEText(plain, 'plain', 'utf-8')
            elif content_type == 'both':
                # Multipart: text + HTML
                msg = MIMEMultipart('alternative')
                if body_text:
                    msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
                msg.attach(MIMEText(body_html, 'html', 'utf-8'))
            else:
                # HTML only (default)
                msg = MIMEMultipart('alternative')
                if body_text:
                    msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
                msg.attach(MIMEText(body_html, 'html', 'utf-8'))
            
            msg['Subject'] = subject
            msg['From'] = f"{config.smtp_from_name} <{config.smtp_from}>" if config.smtp_from_name else config.smtp_from
            msg['To'] = ", ".join(recipients)
            msg['Date'] = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')
            
            # Connect and send
            if config.smtp_use_ssl:
                server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30)
                if config.smtp_use_tls:
                    server.starttls()
            
            # Login if credentials provided
            if config.smtp_user and config.smtp_password:
                server.login(config.smtp_user, config.smtp_password)
            
            # Send to all recipients
            server.sendmail(config.smtp_from, recipients, msg.as_string())
            server.quit()
            
            # Log success for each recipient
            for recipient in recipients:
                log = NotificationLog(
                    type=notification_type,
                    recipient=recipient,
                    subject=subject,
                    body_preview=body_html[:500] if body_html else "",
                    status='sent',
                    resource_type=resource_type,
                    resource_id=resource_id,
                    sent_at=datetime.utcnow()
                )
                db.session.add(log)
            
            db.session.commit()
            
            logger.info(f"Email sent successfully to {len(recipients)} recipient(s): {subject}")
            return True, f"Email sent to {len(recipients)} recipient(s)"
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send email: {error_msg}")
            
            # Log failure for each recipient
            for recipient in recipients:
                log = NotificationLog(
                    type=notification_type,
                    recipient=recipient,
                    subject=subject,
                    body_preview=body_html[:500] if body_html else "",
                    status='failed',
                    error_message=error_msg,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    sent_at=datetime.utcnow()
                )
                db.session.add(log)
            
            try:
                db.session.commit()
            except:
                pass
            
            return False, f"Failed to send email: {error_msg}"
    
    @staticmethod
    def send_test_email(recipient: str) -> tuple[bool, str]:
        """Send a test email"""
        from services.email_templates import render_template, render_text_template
        from models.email_notification import SMTPConfig
        
        smtp = SMTPConfig.query.first()
        custom_template = smtp.email_template if smtp else None
        custom_text_template = smtp.email_text_template if smtp else None
        
        subject = "UCM Test Email"
        content = """
        <p style="font-size:15px;color:#374151;line-height:1.7;margin:0 0 16px;">This is a test email from your UCM instance.</p>
        <p style="font-size:15px;color:#374151;line-height:1.7;margin:0 0 16px;">If you received this email, your SMTP configuration is working correctly! ✅</p>
        <div style="background-color:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin:20px 0;">
            <p style="margin:0;font-size:14px;color:#166534;font-weight:500;">🎉 Your email notifications are ready to use.</p>
        </div>
        """
        
        body_html = render_template(custom_template, "Test Email", "#3b82f6", content)
        body_text = render_text_template(custom_text_template, "Test Email",
            "This is a test email from your UCM instance.\nIf you received this email, your SMTP configuration is working correctly!")
        
        return EmailService.send_email(
            recipients=[recipient],
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            notification_type='test'
        )
