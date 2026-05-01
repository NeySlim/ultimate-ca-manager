"""
Notification-related restore methods mixin for BackupService
"""
import logging
from typing import Dict, Any

from models import db

logger = logging.getLogger(__name__)


class RestoreNotificationsMixin:
    def _restore_smtp_config(self, backup_data: Dict, results: Dict) -> None:
        """Restore SMTP configuration from backup data"""
        from models.email_notification import SMTPConfig
        for smtp_data in backup_data.get('smtp_config', []):
            existing = SMTPConfig.query.first()
            if existing:
                smtp = existing
            else:
                smtp = SMTPConfig()
                db.session.add(smtp)
            smtp.smtp_host = smtp_data.get('smtp_host')
            smtp.smtp_port = smtp_data.get('smtp_port', 587)
            smtp.smtp_user = smtp_data.get('smtp_user')
            smtp._smtp_password = smtp_data.get('smtp_password')
            smtp.smtp_from = smtp_data.get('smtp_from')
            smtp.smtp_from_name = smtp_data.get('smtp_from_name')
            smtp.smtp_use_tls = smtp_data.get('smtp_use_tls', True)
            smtp.smtp_use_ssl = smtp_data.get('smtp_use_ssl', False)
            smtp.enabled = smtp_data.get('enabled', False)
            results['smtp_config'] += 1

    def _restore_notification_config(self, backup_data: Dict, results: Dict) -> None:
        """Restore notification configuration from backup data"""
        from models.email_notification import NotificationConfig
        for nc_data in backup_data.get('notification_config', []):
            existing = NotificationConfig.query.filter_by(type=nc_data['type']).first()
            if existing:
                existing.enabled = nc_data.get('enabled', True)
                existing.days_before = nc_data.get('days_before')
                existing.recipients = nc_data.get('recipients')
                existing.subject_template = nc_data.get('subject_template')
                existing.description = nc_data.get('description')
                existing.cooldown_hours = nc_data.get('cooldown_hours', 24)
            else:
                new_nc = NotificationConfig(
                    type=nc_data['type'],
                    enabled=nc_data.get('enabled', True),
                    days_before=nc_data.get('days_before'),
                    recipients=nc_data.get('recipients'),
                    subject_template=nc_data.get('subject_template'),
                    description=nc_data.get('description'),
                    cooldown_hours=nc_data.get('cooldown_hours', 24),
                )
                db.session.add(new_nc)
            results['notification_config'] += 1
