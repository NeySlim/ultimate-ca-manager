import json
import logging
from datetime import datetime, timedelta
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

# HA: one node at a time runs the expiry pass. The webhook mark (kept on every install) is the
# cluster instant of the last emission: the next pass announces what expired since, on any node.
EXPIRY_LEASE_KEY = 'expiry_alerts.lease'
EXPIRY_WEBHOOKS_MARK_KEY = 'expiry_alerts.webhooks_mark'
EXPIRY_LEASE = timedelta(minutes=10)
# Oldest expiry announced after an outage: past a month the news is stale and a flood of it buries the rest
EXPIRY_CATCH_UP = timedelta(days=30)


class _NoLease:
    """Outside HA one scheduler runs the pass: nothing to reserve."""
    def renew(self):
        return True

    def end(self):
        pass


def _cluster_now():
    from services.scheduler_leader import cluster_utc_now
    return cluster_utc_now()


def _parse_mark(value):
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _later(last, now):
    """The mark never moves back: a cluster clock stepping back would announce expiries again."""
    return last if last is not None and last > now else now


def _expired_after(last, now):
    """Lower bound of the 'expired' window: the mark, at most EXPIRY_CATCH_UP back, and the
    last day on a first pass (no mark), which announces no backlog. Logs what is left aside."""
    if last is None:
        return now - timedelta(days=1)
    floor = now - EXPIRY_CATCH_UP
    if last >= floor:
        return last
    from services import expiry_alert_service
    left = expiry_alert_service.count_expired_between(last, floor)
    if left:
        logger.warning(f"Expiry webhooks: {left} certificate(s) expired more than "
                       f"{EXPIRY_CATCH_UP.days} days ago are not announced")
    return floor


def _emit_webhooks_in_ha():
    """HA: 'expired' covers (last mark, now], 'expiring' reminders go out once per cluster
    day; a pass cut short before the mark is emitted again once the lease is over."""
    from models import SystemConfig, db
    from utils.config_cas import config_compare_and_set
    from services import expiry_alert_service
    now = _cluster_now()
    previous = db.session.query(SystemConfig.value).filter_by(key=EXPIRY_WEBHOOKS_MARK_KEY).scalar()
    last = _parse_mark(previous)
    if not expiry_alert_service._emit_expiry_webhooks(
            expiring=last is None or last.date() != now.date(),
            expired_after=_expired_after(last, now),
            now=now):
        return
    try:
        config_compare_and_set(EXPIRY_WEBHOOKS_MARK_KEY, previous, _later(last, now).isoformat())
    except Exception as e:
        db.session.rollback()
        logger.error(f"Expiry webhooks sent, their mark not stored: {e}")


def _emit_webhooks_single_node():
    """Same window as in HA, from the mark; reminders go out at every pass."""
    from models import SystemConfig, db
    from services import expiry_alert_service
    now = _cluster_now()
    row = SystemConfig.query.filter_by(key=EXPIRY_WEBHOOKS_MARK_KEY).first()
    last = _parse_mark(row.value if row is not None else None)
    if not expiry_alert_service._emit_expiry_webhooks(expired_after=_expired_after(last, now), now=now):
        return
    try:
        row = SystemConfig.query.filter_by(key=EXPIRY_WEBHOOKS_MARK_KEY).first()
        if row is None:
            db.session.add(SystemConfig(key=EXPIRY_WEBHOOKS_MARK_KEY, value=now.isoformat()))
        else:
            row.value = _later(_parse_mark(row.value), now).isoformat()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Expiry webhooks sent, their mark not stored: {e}")


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
        from utils.ha import ha_enabled
        if not ha_enabled():
            return NotificationSchedulerMixin._run_checks(_NoLease())
        from utils.config_cas import ConfigLease
        lease = ConfigLease(EXPIRY_LEASE_KEY, EXPIRY_LEASE)
        if not lease.take():
            logger.info("Expiry checks skipped: another node is running them")
            return {'status': 'skipped', 'reason': 'another node is running the expiry checks',
                    'retry_in': lease.retry_in()}
        try:
            return NotificationSchedulerMixin._run_checks(lease)
        finally:
            lease.end()

    @staticmethod
    def _run_checks(lease):
        """Every send is preceded by a renewal: a node whose lease was taken over stops."""
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
                if not lease.renew():
                    return NotificationSchedulerMixin._taken_over(results)
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
                if not lease.renew():
                    return NotificationSchedulerMixin._taken_over(results)
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
            if isinstance(lease, _NoLease):
                _emit_webhooks_single_node()
            elif lease.renew():
                _emit_webhooks_in_ha()
            else:
                return NotificationSchedulerMixin._taken_over(results)
        except Exception as e:
            logger.error(f"Expiry webhook pass failed: {e}")

        logger.info(f"Notification check completed: {results}")
        return results

    @staticmethod
    def _taken_over(results):
        logger.warning(f"Expiry checks stopped: another node took the run over ({results})")
        return {**results, 'status': 'warning', 'reason': 'another node took the run over'}
