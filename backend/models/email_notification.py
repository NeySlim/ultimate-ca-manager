"""
Email Notification Models for UCM
Includes SMTP configuration, notification rules, and logs
"""
import json
from datetime import datetime
from models import db


class SMTPConfig(db.Model):
    """SMTP Configuration for email notifications"""
    __tablename__ = "smtp_config"
    
    id = db.Column(db.Integer, primary_key=True)
    smtp_host = db.Column(db.String(255))
    smtp_port = db.Column(db.Integer, default=587)
    smtp_user = db.Column(db.String(255))
    _smtp_password = db.Column('smtp_password', db.String(512))  # Encrypted
    smtp_from = db.Column(db.String(255))
    smtp_from_name = db.Column(db.String(255), default="UCM Notifications")
    smtp_use_tls = db.Column(db.Boolean, default=True)
    smtp_use_ssl = db.Column(db.Boolean, default=False)
    smtp_auth = db.Column(db.Boolean, default=True)
    smtp_content_type = db.Column(db.String(10), default='html')  # html, text, both
    email_template = db.Column(db.Text)  # Custom HTML template (null = use default)
    email_text_template = db.Column(db.Text)  # Custom plain text template (null = use default)
    enabled = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.String(80))
    
    # SECURITY: Encrypted password property
    @property
    def smtp_password(self):
        """Decrypt SMTP password"""
        if not self._smtp_password:
            return None
        try:
            from utils.encryption import decrypt_if_needed
            return decrypt_if_needed(self._smtp_password)
        except ImportError:
            # Pro module not available, return as-is
            return self._smtp_password
        except Exception:
            return self._smtp_password
    
    @smtp_password.setter
    def smtp_password(self, value):
        """Encrypt SMTP password before storing"""
        if not value:
            self._smtp_password = None
            return
        try:
            from utils.encryption import encrypt_if_needed
            self._smtp_password = encrypt_if_needed(value)
        except ImportError:
            # Pro module not available, store as-is
            self._smtp_password = value
        except Exception:
            self._smtp_password = value
    
    def to_dict(self, include_password=False):
        """Convert to dictionary"""
        data = {
            "id": self.id,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_user": self.smtp_user,
            "smtp_from": self.smtp_from,
            "smtp_from_name": self.smtp_from_name,
            "smtp_use_tls": self.smtp_use_tls,
            "smtp_use_ssl": self.smtp_use_ssl,
            "enabled": self.enabled,
            "has_password": bool(self._smtp_password),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "updated_by": self.updated_by,
        }
        if include_password:
            data["smtp_password"] = self.smtp_password
        return data


class NotificationConfig(db.Model):
    """Notification Configuration (what to send and when)"""
    __tablename__ = "notification_config"
    
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), unique=True, nullable=False, index=True)
    # Types: cert_expiring, crl_expiring, cert_issued, cert_revoked, ca_created, security_alert, password_changed
    enabled = db.Column(db.Boolean, default=True)
    days_before = db.Column(db.Integer)  # For expiring notifications (7, 14, 30, etc.)
    recipients = db.Column(db.Text)  # JSON array of email addresses
    subject_template = db.Column(db.String(255))
    description = db.Column(db.String(512))
    # Deduplication: don't send same notification within this many hours
    cooldown_hours = db.Column(db.Integer, default=24)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "type": self.type,
            "enabled": self.enabled,
            "days_before": self.days_before,
            "recipients": json.loads(self.recipients) if self.recipients else [],
            "subject_template": self.subject_template,
            "description": self.description,
            "cooldown_hours": self.cooldown_hours,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class NotificationLog(db.Model):
    """Log of sent notifications"""
    __tablename__ = "notification_log"
    
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False, index=True)
    recipient = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(255))
    body_preview = db.Column(db.Text)  # First 500 chars
    status = db.Column(db.String(20), nullable=False, index=True)  # sent, failed, pending, retry
    error_message = db.Column(db.Text)
    resource_type = db.Column(db.String(50))  # certificate, ca, crl, user
    resource_id = db.Column(db.String(100))  # refid or ID
    retry_count = db.Column(db.Integer, default=0)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Composite index for deduplication queries
    __table_args__ = (
        db.Index('idx_notification_dedup', 'type', 'resource_type', 'resource_id', 'sent_at'),
    )
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "type": self.type,
            "recipient": self.recipient,
            "subject": self.subject,
            "body_preview": self.body_preview[:200] + "..." if self.body_preview and len(self.body_preview) > 200 else self.body_preview,
            "status": self.status,
            "error_message": self.error_message,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "retry_count": self.retry_count,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
        }
    
    @classmethod
    def was_recently_sent(cls, notification_type: str, resource_type: str, resource_id: str, hours: int = 24) -> bool:
        """Check if this notification was already sent recently (for deduplication)"""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        existing = cls.query.filter(
            cls.type == notification_type,
            cls.resource_type == resource_type,
            cls.resource_id == resource_id,
            cls.status == 'sent',
            cls.sent_at >= cutoff
        ).first()
        return existing is not None
