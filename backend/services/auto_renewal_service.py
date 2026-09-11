"""
Certificate Auto-Renewal Service
Automatically renews certificates before they expire.

Renewal itself is delegated to ``services.cert.renewal.renew_certificate_in_place``
— the exact routine behind ``POST /api/v2/certificates/<id>/renew`` and
``POST /api/v2/certificates/bulk/renew``. Auto-renewed certificates therefore
get the same treatment as manually renewed ones: the superseded serial is
recorded in ``revoked_serials`` (reason ``superseded``) so it stays on the CRL
and answers ``revoked`` over OCSP, the row is updated in place (``id``,
``refid`` and ``created_at`` preserved, ``renewed_at`` / ``renewed_times``
maintained), and the same audit entry and ``cert_renewed`` webhook fire.

Only certificates whose private key the server holds are candidates: a
certificate enrolled through SCEP, EST, WSTEP or ACME keeps its key on the
device, which renews through its protocol, and a certificate re-signed here
could never reach it. Auto-renewal does not re-key: the existing key pair is
re-signed, so exports made from the previous certificate keep working.
"""
import json
from datetime import timedelta
from models import db, Certificate, CA, SystemConfig, AuditLog
from services.cert.renewal import RenewalError, renew_certificate_in_place
import logging
from utils.datetime_utils import to_naive_utc, utc_now

logger = logging.getLogger(__name__)

# Actor recorded in the audit trail / webhooks for unattended renewals.
AUTO_RENEWAL_ACTOR = 'auto-renewal'


def _safe_json_loads(raw, default):
    """Parse a JSON config string, returning *default* on malformed input.

    SystemConfig values are admin-set free-text strings; a stray edit or
    manual DB write can produce invalid JSON that would otherwise kill the
    auto-renewal scheduler with an unhandled ``ValueError``.
    """
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.warning("Malformed JSON config value %r, using default %r", raw, default)
        return default


class AutoRenewalService:
    """Service for automatic certificate renewal"""

    @staticmethod
    def get_renewal_config():
        """Get auto-renewal configuration"""
        config = {
            'enabled': False,
            'days_before_expiry': 30,
            # Sources to auto-renew: manual covers the issue form and signed
            # requests; the protocol sources only match certificates whose
            # key the server holds (EST server-side key generation)
            'renewal_sources': ['manual', 'scep', 'acme', 'est'],
            'notify_on_renewal': True,
            'notify_on_failure': True,
        }

        enabled = SystemConfig.query.filter_by(key='auto_renewal_enabled').first()
        if enabled:
            config['enabled'] = enabled.value == 'true'

        days = SystemConfig.query.filter_by(key='auto_renewal_days').first()
        if days:
            config['days_before_expiry'] = int(days.value)

        sources = SystemConfig.query.filter_by(key='auto_renewal_sources').first()
        if sources:
            parsed = _safe_json_loads(sources.value, config['renewal_sources'])
            if not isinstance(parsed, list):
                logger.warning(
                    "auto_renewal_sources is not a JSON list (%r), using default",
                    sources.value,
                )
            else:
                config['renewal_sources'] = parsed

        notify_renewal = SystemConfig.query.filter_by(key='auto_renewal_notify_on_renewal').first()
        if notify_renewal:
            config['notify_on_renewal'] = notify_renewal.value == 'true'

        notify_failure = SystemConfig.query.filter_by(key='auto_renewal_notify_on_failure').first()
        if notify_failure:
            config['notify_on_failure'] = notify_failure.value == 'true'

        return config

    @staticmethod
    def set_renewal_config(config: dict):
        """Update auto-renewal configuration"""
        # The stored keys get_renewal_config reads back
        db_keys = {'renewal_sources': 'auto_renewal_sources',
                   'days_before_expiry': 'auto_renewal_days'}
        for key, value in config.items():
            db_key = db_keys.get(key, f'auto_renewal_{key}')
            if key in ('enabled', 'notify_on_renewal', 'notify_on_failure'):
                db_value = 'true' if value else 'false'
            elif key == 'renewal_sources':
                db_value = json.dumps(value)
            else:
                db_value = str(value)

            existing = SystemConfig.query.filter_by(key=db_key).first()
            if existing:
                existing.value = db_value
            else:
                db.session.add(SystemConfig(key=db_key, value=db_value))

        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/auto_renewal_service.py:109: {_commit_err}", exc_info=True)
            raise

    @staticmethod
    def get_certificates_for_renewal():
        """Get certificates eligible for auto-renewal"""
        config = AutoRenewalService.get_renewal_config()
        if not config['enabled']:
            return []

        threshold = utc_now() + timedelta(days=config['days_before_expiry'])

        # NOTE: Certificate has no `status` column — `revoked` boolean + `archived` instead.
        # Expiry uses `valid_to`, not `not_after`.
        certs = Certificate.query.filter(
            Certificate.revoked.is_(False),
            (Certificate.archived.is_(False)) | (Certificate.archived.is_(None)),
            Certificate.valid_to.isnot(None),
            Certificate.valid_to <= threshold,
            Certificate.valid_to >= utc_now(),  # don't try to renew already-expired
            Certificate.crt.isnot(None),  # only issued certs, not CSRs
            # A certificate whose key the device holds cannot be delivered by
            # the scheduler; the device renews through its protocol
            Certificate.prv.isnot(None),
            Certificate.prv != '',
            Certificate.source.in_(config['renewal_sources'])
        ).all()

        return certs

    @staticmethod
    def renew_certificate(cert: Certificate, regenerate_crl: bool = True, known_serial=None) -> tuple:
        """
        Renew a single certificate in place.

        Uses the same routine as manual and bulk renewal, so the superseded
        serial lands in `revoked_serials` and the certificate keeps its id,
        refid and created_at.

        Args:
            cert: the certificate to renew.
            regenerate_crl: publish a fresh CRL immediately. `run_auto_renewal`
                passes False and regenerates once per CA after the batch.
            known_serial: the serial the batch listed the certificate with;
                a certificate renewed by someone else meanwhile is refused.

        Returns:
            (success: bool, cert_id or error_message: int|str)
        """
        try:
            renew_certificate_in_place(
                cert,
                username=AUTO_RENEWAL_ACTOR,
                # The held key pair is re-signed, not replaced (module docstring)
                rekey=False,
                regenerate_crl=regenerate_crl,
                trigger='auto',
                known_serial=known_serial,
            )
            return True, cert.id

        except RenewalError as e:
            db.session.rollback()
            logger.warning(f"Auto-renewal refused for cert {cert.id}: {e.message}")
            AutoRenewalService._log_failure(cert, e.message)
            return False, e.message

        except Exception as e:
            db.session.rollback()
            logger.error(f"Auto-renewal failed for cert {cert.id}: {e}", exc_info=True)
            AutoRenewalService._log_failure(cert, str(e))
            return False, "Renewal failed"

    @staticmethod
    def _log_failure(cert: Certificate, reason: str):
        """Surface a renewal failure in the audit trail.

        A silently-swallowed failure means the certificate expires without
        warning, so this is best-effort but never allowed to raise.
        """
        try:
            db.session.add(AuditLog(
                action='certificate.auto_renewal_failed',
                resource_type='certificate',
                resource_id=cert.id,
                resource_name=cert.common_name,
                details=f'Auto-renewal failed: {reason}',
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()

    @staticmethod
    def run_auto_renewal():
        """
        Run auto-renewal for all eligible certificates.
        This is called by the scheduler service.
        """
        config = AutoRenewalService.get_renewal_config()
        if not config['enabled']:
            logger.debug("Auto-renewal is disabled")
            return {'renewed': 0, 'failed': 0, 'skipped': 0}

        certs = AutoRenewalService.get_certificates_for_renewal()
        # The serials as listed: a certificate an operator renews during
        # the batch (and deploys) is not renewed a second time
        listed_serials = {c.id: c.serial_number for c in certs}

        stats = {'renewed': 0, 'failed': 0, 'skipped': 0, 'errors': []}
        # CRLs are published once per CA after the batch — every renewal adds a
        # superseded serial that only reaches relying parties through a CRL.
        renewed_carefs = set()

        # A renewal an operator queued for approval is a human decision the
        # scheduler does not pre-empt, as long as that decision (or the
        # request's expiry) comes before the certificate expires; the
        # certificate is picked up again once the request is resolved
        from services.approval_gate import expire_stale_requests, pending_target_ids
        expire_stale_requests()
        awaiting_approval = pending_target_ids('renewal', 'certificate_id')

        for cert in certs:
            # Skip already-archived (superseded by a pre-in-place-renewal run)
            if cert.archived:
                stats['skipped'] += 1
                continue
            deadline = awaiting_approval.get(str(cert.id))
            valid_to = to_naive_utc(cert.valid_to)
            if deadline is not None and valid_to is not None and deadline < valid_to:
                logger.info(f"Auto-renewal skipped cert {cert.id}: renewal awaiting approval")
                stats['skipped'] += 1
                continue

            success, result = AutoRenewalService.renew_certificate(
                cert, regenerate_crl=False, known_serial=listed_serials.get(cert.id)
            )

            if success:
                stats['renewed'] += 1
                # The renewal links the row to the CA that really signed it
                # (resolved by signature when the row named none): that CA's
                # CRL is the one carrying the superseded serial
                if cert.caref:
                    renewed_carefs.add(cert.caref)
            else:
                stats['failed'] += 1
                stats['errors'].append({
                    'cert_id': cert.id,
                    'common_name': cert.common_name,
                    'error': result
                })

        AutoRenewalService._publish_crls(renewed_carefs)

        logger.info(f"Auto-renewal complete: {stats['renewed']} renewed, {stats['failed']} failed")

        # Send notifications if configured
        if config.get('notify_on_renewal') and stats['renewed'] > 0:
            AutoRenewalService._send_renewal_notification(stats)

        if config.get('notify_on_failure') and stats['failed'] > 0:
            AutoRenewalService._send_failure_notification(stats)

        return stats

    @staticmethod
    def _publish_crls(carefs):
        """Regenerate the CRL once per CDP-enabled CA touched by the batch."""
        if not carefs:
            return
        from services.crl_service import CRLService
        for caref in carefs:
            ca = CA.query.filter_by(refid=caref).first()
            if not ca or not ca.cdp_enabled:
                continue
            try:
                CRLService.generate_crl(ca.id, username=AUTO_RENEWAL_ACTOR)
            except Exception as e:
                logger.warning(
                    f"Failed to auto-generate CRL for CA {ca.id} after auto-renewal: {e}"
                )

    @staticmethod
    def _send_renewal_notification(stats: dict):
        """Send notification about successful renewals"""
        from services.email_service import EmailService

        recipients = SystemConfig.query.filter_by(key='auto_renewal_notify_emails').first()
        if not recipients:
            return

        emails = _safe_json_loads(recipients.value, [])
        if not isinstance(emails, list):
            logger.warning(
                "auto_renewal_notify_emails is not a JSON list (%r), skipping notifications",
                recipients.value,
            )
            return

        for email in emails:
            try:
                EmailService.send_email(
                    to=email,
                    subject=f'UCM: {stats["renewed"]} certificates auto-renewed',
                    body=f'The following {stats["renewed"]} certificates were automatically renewed.',
                    html=f'<p>The following {stats["renewed"]} certificates were automatically renewed.</p>'
                )
            except Exception as e:
                logger.error(f"Failed to send renewal notification: {e}")

    @staticmethod
    def _send_failure_notification(stats: dict):
        """Send notification about failed renewals"""
        from services.email_service import EmailService

        recipients = SystemConfig.query.filter_by(key='auto_renewal_notify_emails').first()
        if not recipients:
            return

        emails = _safe_json_loads(recipients.value, [])
        if not isinstance(emails, list):
            logger.warning(
                "auto_renewal_notify_emails is not a JSON list (%r), skipping failure notifications",
                recipients.value,
            )
            return

        error_list = '\n'.join([
            f"- {e['common_name']} (ID: {e['cert_id']}): {e['error']}"
            for e in stats.get('errors', [])
        ])

        for email in emails:
            try:
                EmailService.send_email(
                    to=email,
                    subject=f'UCM: {stats["failed"]} certificate renewals FAILED',
                    body=f'The following certificate renewals failed:\n\n{error_list}',
                    html=f'<p>The following certificate renewals failed:</p><pre>{error_list}</pre>'
                )
            except Exception as e:
                logger.error(f"Failed to send failure notification: {e}")


# Scheduler task function
def run_auto_renewal_task():
    """Scheduled task for auto-renewal"""
    return AutoRenewalService.run_auto_renewal()
