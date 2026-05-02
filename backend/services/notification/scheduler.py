import json
import logging
from datetime import timedelta
from typing import List, Dict
from models import CA, Certificate
from models.crl import CRLMetadata
from utils.datetime_utils import utc_now
from .config import NotificationConfigMixin
from .sender import NotificationSenderMixin
from ._constants import CERT_EXPIRING, CRL_EXPIRING

logger = logging.getLogger(__name__)


class NotificationSchedulerMixin:

    @staticmethod
    def check_expiring_certificates():
        config = NotificationConfigMixin.get_config(CERT_EXPIRING)
        if not config or not config.enabled or not config.days_before:
            return []

        threshold_date = utc_now() + timedelta(days=config.days_before)

        certs = Certificate.query.filter(
            Certificate.valid_to <= threshold_date,
            Certificate.valid_to > utc_now(),
            Certificate.revoked == False
        ).all()

        expiring = []
        for cert in certs:
            if NotificationConfigMixin.should_send(CERT_EXPIRING, 'certificate', cert.refid):
                days_remaining = (cert.valid_to - utc_now()).days
                expiring.append({
                    'cert': cert,
                    'days_remaining': days_remaining
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
                days_remaining = (crl.next_update - utc_now()).days
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
        if config and config.enabled and config.recipients:
            recipients = json.loads(config.recipients)
            expiring_certs = NotificationSchedulerMixin.check_expiring_certificates()
            results['cert_expiring']['checked'] = len(expiring_certs)

            for item in expiring_certs:
                cert = item['cert']
                days = item['days_remaining']

                success, msg = NotificationSenderMixin.send_cert_expiring_notification(
                    cert, days, recipients
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

        logger.info(f"Notification check completed: {results}")
        return results
