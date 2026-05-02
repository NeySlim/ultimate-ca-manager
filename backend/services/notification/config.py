import logging
from models import db
from models.email_notification import NotificationConfig, NotificationLog
from ._constants import (
    CERT_EXPIRING, CRL_EXPIRING, CERT_ISSUED, CERT_REVOKED,
    CA_CREATED, SECURITY_ALERT, PASSWORD_CHANGED,
)

logger = logging.getLogger(__name__)


class NotificationConfigMixin:

    @staticmethod
    def get_config(notification_type):
        return NotificationConfig.query.filter_by(type=notification_type).first()

    @staticmethod
    def get_all_configs():
        return NotificationConfig.query.all()

    @staticmethod
    def create_default_configs():
        defaults = [
            {
                'type': CERT_EXPIRING,
                'description': 'Alert when certificates are about to expire',
                'days_before': 30,
                'cooldown_hours': 24,
                'enabled': True,
            },
            {
                'type': CRL_EXPIRING,
                'description': 'Alert when CRLs need to be regenerated',
                'days_before': 7,
                'cooldown_hours': 24,
                'enabled': True,
            },
            {
                'type': CERT_ISSUED,
                'description': 'Notify when new certificates are issued',
                'cooldown_hours': 0,
                'enabled': False,
            },
            {
                'type': CERT_REVOKED,
                'description': 'Alert when certificates are revoked',
                'cooldown_hours': 0,
                'enabled': True,
            },
            {
                'type': CA_CREATED,
                'description': 'Notify when new CAs are created',
                'cooldown_hours': 0,
                'enabled': False,
            },
            {
                'type': SECURITY_ALERT,
                'description': 'Security alerts (failed logins, account lockouts)',
                'cooldown_hours': 1,
                'enabled': True,
            },
            {
                'type': PASSWORD_CHANGED,
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

    @staticmethod
    def should_send(notification_type, resource_type, resource_id):
        config = NotificationConfigMixin.get_config(notification_type)
        if not config or not config.enabled:
            return False

        cooldown = config.cooldown_hours or 24
        if cooldown == 0:
            return True

        return not NotificationLog.was_recently_sent(
            notification_type, resource_type, resource_id, cooldown
        )
