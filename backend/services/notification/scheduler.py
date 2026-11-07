import json
import logging
from datetime import timedelta
from typing import List, Dict
from models import CA, Certificate
from models.email_notification import NotificationLog
from models.crl import CRLMetadata
from utils.datetime_utils import utc_now
from utils.days_remaining import days_remaining as compute_days_remaining
from .config import NotificationConfigMixin
from .sender import NotificationSenderMixin
from ._constants import CERT_EXPIRING, CRL_EXPIRING

logger = logging.getLogger(__name__)


class NotificationSchedulerMixin:

    @staticmethod
    def check_expiring_certificates():
        """Certificates that crossed an alert threshold not yet notified for
        their current validity period.

        Thresholds come from the cert_expiring row (#323). For each
        certificate the tightest crossed threshold is used and fires once
        (tracked in notification_log.threshold_days since valid_from), so a
        30/14/7/1 selection escalates instead of repeating every day inside
        the largest window (#324).
        """
        config = NotificationConfigMixin.get_config(CERT_EXPIRING)
        if not config or not config.enabled:
            return []
        thresholds = config.get_alert_days()
        if not thresholds:
            return []

        now = utc_now()
        threshold_date = now + timedelta(days=max(thresholds))
        query = Certificate.query.filter(
            Certificate.valid_to <= threshold_date,
            Certificate.valid_to > now,
        )
        if not config.include_revoked:
            query = query.filter(Certificate.revoked.isnot(True))
        if config.exclude_acme:
            query = query.filter(Certificate.source.is_distinct_from('acme'))
        # EST key generators renew by themselves; a replaced one stays archived until it expires
        query = query.filter(Certificate.source.is_distinct_from('est_key_generator'))

        expiring = []
        for cert in query.all():
            days_remaining = compute_days_remaining(cert.valid_to, now)
            due = [t for t in thresholds if days_remaining <= t]
            if not due:
                continue
            threshold = min(due)
            if NotificationLog.was_sent_for_threshold(
                CERT_EXPIRING, 'certificate', cert.refid, threshold,
                since=cert.valid_from,
            ):
                continue
            expiring.append({
                'cert': cert,
                'days_remaining': days_remaining,
                'threshold_days': threshold,
            })

        return expiring

    @staticmethod
    def check_expiring_crls():
        config = NotificationConfigMixin.get_config(CRL_EXPIRING)
        if not config or not config.enabled or not config.days_before:
            return []

        threshold_date = utc_now() + timedelta(days=config.days_before)

        crls = CRLMetadata.query.filter(
            CRLMetadata.next_update <= threshold_date,
            CRLMetadata.next_update > utc_now()
        ).all()

        expiring = []
        for crl in crls:
            if NotificationConfigMixin.should_send(CRL_EXPIRING, 'crl', str(crl.id)):
                days_remaining = compute_days_remaining(crl.next_update)
                expiring.append({
                    'crl': crl,
                    'days_remaining': days_remaining
                })

        return expiring

    @staticmethod
    def run_scheduled_checks():
        logger.info("Running scheduled notification checks...")
        results = {
            'cert_expiring': {'checked': 0, 'notified': 0, 'failed': 0},
            'crl_expiring': {'checked': 0, 'notified': 0, 'failed': 0},
        }

        config = NotificationConfigMixin.get_config(CERT_EXPIRING)
        cert_recipients = json.loads(config.recipients) if config and config.recipients else []
        if config and config.enabled and not cert_recipients:
            logger.warning(
                "Certificate expiry alerts are enabled but have no recipients; "
                "add recipients under Settings > Email > Certificate Expiry Alerts"
            )
        if config and config.enabled and cert_recipients:
            recipients = cert_recipients
            expiring_certs = NotificationSchedulerMixin.check_expiring_certificates()
            results['cert_expiring']['checked'] = len(expiring_certs)

            for item in expiring_certs:
                cert = item['cert']
                days = item['days_remaining']

                success, msg = NotificationSenderMixin.send_cert_expiring_notification(
                    cert, days, recipients, threshold_days=item.get('threshold_days')
                )
                if success:
                    results['cert_expiring']['notified'] += 1
                else:
                    results['cert_expiring']['failed'] += 1
                    logger.error(f"Failed to send cert notification: {msg}")

        config = NotificationConfigMixin.get_config(CRL_EXPIRING)
        if config and config.enabled and config.recipients:
            recipients = json.loads(config.recipients)
            expiring_crls = NotificationSchedulerMixin.check_expiring_crls()
            results['crl_expiring']['checked'] = len(expiring_crls)

            for item in expiring_crls:
                crl = item['crl']
                days = item['days_remaining']

                success, msg = NotificationSenderMixin.send_crl_expiring_notification(
                    crl, days, recipients
                )
                if success:
                    results['crl_expiring']['notified'] += 1
                else:
                    results['crl_expiring']['failed'] += 1
                    logger.error(f"Failed to send CRL notification: {msg}")

        # Fire certificate.expiring / certificate.expired webhooks. Independent
        # of email notification config — webhooks must work even when email
        # alerts are disabled or have no recipients.
        try:
            from services.expiry_alert_service import _emit_expiry_webhooks
            _emit_expiry_webhooks()
        except Exception as e:
            logger.error(f"Expiry webhook pass failed: {e}")

        logger.info(f"Notification check completed: {results}")
        return results
