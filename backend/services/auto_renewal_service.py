"""
Certificate Auto-Renewal Service
Automatically renews certificates before they expire.
Only certificates whose private key the server holds are candidates: a
certificate enrolled through SCEP, EST, WSTEP or ACME keeps its key on the
device, which renews through its protocol, and a certificate re-signed here
could never reach it. Auto-renewal does not re-key: the existing key pair is
re-signed, so exports made from the previous certificate keep working.
"""
import datetime
import json
import logging

from sqlalchemy.orm.exc import ObjectDeletedError

from models import db, Certificate, CA, SystemConfig
from services.cert.renewal import RenewalError, SERIAL_UNSET, renew_certificate_in_place
from utils.datetime_utils import to_naive_utc, utc_now

logger = logging.getLogger(__name__)

# Actor of scheduled renewals: audit entries, approval requests, CRLs
AUTO_RENEWAL_ACTOR = 'auto-renewal'

# Settings stored as 'true' / 'false'
_FLAG_KEYS = ('enabled', 'notify_on_renewal', 'notify_on_failure')


def _json_list(key: str, raw):
    """The JSON list stored under ``key``, or None (with a warning) when
    the value is not valid JSON or not a list."""
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning(f"Setting {key} is not valid JSON; ignored")
        return None
    if not isinstance(value, list):
        logger.warning(f"Setting {key} is not a JSON list; ignored")
        return None
    return value


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
            try:
                config['days_before_expiry'] = int(days.value)
            except (TypeError, ValueError):
                logger.warning("Setting auto_renewal_days is not an integer; ignored")

        sources = SystemConfig.query.filter_by(key='auto_renewal_sources').first()
        if sources:
            parsed = _json_list('auto_renewal_sources', sources.value)
            if parsed is not None and all(isinstance(v, str) for v in parsed):
                config['renewal_sources'] = parsed
            elif parsed is not None:
                logger.warning("Setting auto_renewal_sources holds non-string values; ignored")

        for flag in ('notify_on_renewal', 'notify_on_failure'):
            row = SystemConfig.query.filter_by(key=f'auto_renewal_{flag}').first()
            if row:
                config[flag] = row.value == 'true'
        return config

    @staticmethod
    def set_renewal_config(config: dict):
        """Update auto-renewal configuration"""
        # The stored keys get_renewal_config reads back
        db_keys = {'renewal_sources': 'auto_renewal_sources',
                   'days_before_expiry': 'auto_renewal_days'}
        for key, value in config.items():
            db_key = db_keys.get(key, f'auto_renewal_{key}')
            if key in _FLAG_KEYS:
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
            logger.error(f"Auto-renewal settings not saved: {_commit_err}", exc_info=True)
            raise

    @staticmethod
    def get_certificates_for_renewal():
        """Get certificates eligible for auto-renewal"""
        config = AutoRenewalService.get_renewal_config()
        if not config['enabled']:
            return []

        threshold = utc_now() + datetime.timedelta(days=config['days_before_expiry'])

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

        return [c for c in certs if AutoRenewalService._in_renewal_window(c, config['days_before_expiry'])]

    @staticmethod
    def waiting_certificates(config) -> dict:
        """Count the certificates expiring within the window that this pass
        leaves alone, by reason, so a run that renews nothing says why."""
        now = utc_now()
        rows = db.session.query(
            Certificate.prv, Certificate.source, Certificate.valid_from, Certificate.valid_to,
        ).filter(
            Certificate.revoked.is_(False),
            (Certificate.archived.is_(False)) | (Certificate.archived.is_(None)),
            Certificate.crt.isnot(None),
            Certificate.valid_to.isnot(None),
            Certificate.valid_to <= now + datetime.timedelta(days=config['days_before_expiry']),
            Certificate.valid_to >= now,
        ).all()
        waiting = {'not_yet_due': 0, 'no_private_key': 0, 'source_excluded': 0}
        for cert in rows:
            if not cert.prv:
                waiting['no_private_key'] += 1
            elif cert.source not in config['renewal_sources']:
                waiting['source_excluded'] += 1
            elif not AutoRenewalService._in_renewal_window(cert, config['days_before_expiry']):
                waiting['not_yet_due'] += 1
        return waiting

    @staticmethod
    def _in_renewal_window(cert: Certificate, days_before_expiry: int) -> bool:
        """Never before the last third of the lifetime, as ARI and the OCSP
        responder do: otherwise a certificate about as long as the window is
        re-signed on every pass from the day it is issued."""
        window = datetime.timedelta(days=days_before_expiry)
        if cert.valid_from is not None:
            lifetime = to_naive_utc(cert.valid_to) - to_naive_utc(cert.valid_from)
            if lifetime > datetime.timedelta(0):
                window = min(window, lifetime / 3)
        return to_naive_utc(cert.valid_to) <= to_naive_utc(utc_now()) + window

    @staticmethod
    def renew_certificate(cert: Certificate, regenerate_crl: bool = True, known_serial=SERIAL_UNSET) -> tuple:
        """Renew one certificate in place for the scheduler: ``(True, id)``,
        ``(None, message)`` when the row is gone, else ``(False, message)``."""
        # Read before the call: a rollback expires the instance
        try:
            cert_id, common_name = cert.id, cert.common_name
        except ObjectDeletedError:
            db.session.rollback()
            return None, 'Certificate no longer exists'

        try:
            renew_certificate_in_place(
                cert, username=AUTO_RENEWAL_ACTOR, actor_user_id=None, rekey=False,
                regenerate_crl=regenerate_crl, trigger='auto', known_serial=known_serial)
        except RenewalError as e:
            db.session.rollback()
            if not AutoRenewalService._row_exists(cert_id):
                logger.info(f"Auto-renewal skipped cert {cert_id}: {e.message}")
                return None, e.message
            logger.warning(f"Auto-renewal of cert {cert_id} refused: {e.message}")
            AutoRenewalService._log_failure(cert_id, common_name, e.message)
            return False, e.message
        except Exception as e:
            db.session.rollback()
            logger.error(f"Auto-renewal of cert {cert_id} failed: {e}", exc_info=True)
            AutoRenewalService._log_failure(cert_id, common_name, 'Renewal failed')
            return False, 'Renewal failed'

        logger.info(f"Auto-renewed cert {cert_id} ({common_name})")
        return True, cert_id

    @staticmethod
    def _row_exists(cert_id) -> bool:
        """Whether the row is still stored, asked of the database rather
        than the identity map; True when that cannot be told."""
        try:
            return db.session.query(Certificate.id).filter(Certificate.id == cert_id).first() is not None
        except Exception:
            db.session.rollback()
            logger.warning(f"Could not check whether cert {cert_id} still exists", exc_info=True)
            return True

    @staticmethod
    def _log_failure(cert_id, common_name, reason: str):
        """Audit entry for a failed scheduled renewal; never raises."""
        from services.audit.staging import stage_audit_entry
        try:
            stage_audit_entry(
                action='certificate.auto_renewal_failed',
                resource_type='certificate',
                resource_id=str(cert_id),
                resource_name=common_name,
                details=f'Auto-renewal failed: {reason}',
                username=AUTO_RENEWAL_ACTOR,
                success=False,
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.warning(f"Auto-renewal failure of cert {cert_id} not audited", exc_info=True)

    @staticmethod
    def _declined(cert) -> bool:
        """True when an approver rejected the scheduler's renewal of this
        very certificate (same serial): a decision, kept until it changes."""
        import json as _json
        from models.policy import ApprovalRequest
        rows = ApprovalRequest.query.filter_by(status='rejected', request_type='renewal').filter(
            ApprovalRequest.request_data.like(f'%"certificate_id": {int(cert.id)},%')).all()
        for row in rows:
            try:
                data = _json.loads(row.request_data or '{}')
            except ValueError:
                continue
            if (data.get('trigger') == 'auto' and data.get('certificate_id') == cert.id
                    and data.get('serial_number') == cert.serial_number):
                return True
        return False

    @staticmethod
    def _held_for_approval(cert, *, already_queued: bool):
        """Why a renewal policy holds ``cert``: 'queued' (a request is
        queued now or already waits), 'declined' (its renewal was rejected),
        or None when no policy requires approval."""
        from services.approval_gate import certificate_scope, queue_renewal
        from services.policy_service import PolicyEvaluationService
        declined = not already_queued and AutoRenewalService._declined(cert)
        if already_queued or declined:
            ca_id, template_id, cn, dns = certificate_scope(cert)
            if PolicyEvaluationService.check_approval_required(
                    ca_id=ca_id, template_id=template_id, cn=cn, san_list=dns,
                    operation='renewal') is None:
                return None
            return 'declined' if declined else 'queued'
        _policy, approval = queue_renewal(None, cert, scheduled_by=AUTO_RENEWAL_ACTOR)
        if approval is None:
            return None
        logger.info(f"Auto-renewal of cert {cert.id} queued for approval (request #{approval.id})")
        return 'queued'

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
        # The batch works from the listing (id, serial): each commit in the
        # batch expires the listed instances, so every row is read again
        # before its turn (an operator may have renewed it, which is then
        # refused, or deleted it, which is then skipped)
        listed = [(c.id, c.serial_number) for c in certs]

        # Counted before the batch: a short certificate renewed here would
        # otherwise come back as not yet due
        stats = {'renewed': 0, 'failed': 0, 'skipped': 0, 'queued': 0, 'errors': [],
                 'waiting': AutoRenewalService.waiting_certificates(config)}
        # CAs whose CRL is published once, after the batch
        renewed_carefs = set()

        # A renewal an operator queued for approval is a human decision the
        # scheduler does not pre-empt, as long as that decision (or the
        # request's expiry) comes before the certificate expires; the
        # certificate is picked up again once the request is resolved
        from services.approval_gate import expire_stale_requests, pending_target_ids
        expire_stale_requests()
        awaiting_approval = pending_target_ids('renewal', 'certificate_id')

        for cert_id, listed_serial in listed:
            # Read again from the database, not from the identity map: the
            # first row of the batch is not expired yet, and a row deleted
            # meanwhile would otherwise be found as listed
            cert = db.session.get(Certificate, cert_id, populate_existing=True)
            if cert is None:
                logger.info(f"Auto-renewal skipped cert {cert_id}: deleted meanwhile")
                stats['skipped'] += 1
                continue
            if cert.archived:
                stats['skipped'] += 1
                continue
            common_name = cert.common_name
            deadline = awaiting_approval.get(str(cert.id))
            valid_to = to_naive_utc(cert.valid_to)
            if deadline is not None and valid_to is not None and deadline < valid_to:
                logger.info(f"Auto-renewal skipped cert {cert.id}: renewal awaiting approval")
                stats['skipped'] += 1
                continue
            # A policy that requires approval for renewals holds the scheduler
            # too: the renewal is queued once, and performed on approval only
            try:
                held = AutoRenewalService._held_for_approval(
                    cert, already_queued=str(cert.id) in awaiting_approval)
            except Exception as e:
                db.session.rollback()
                logger.error(f"Auto-renewal policy evaluation failed for cert {cert_id}: {e}",
                             exc_info=True)
                AutoRenewalService._log_failure(cert_id, common_name, 'Policy evaluation failed')
                stats['failed'] += 1
                stats['errors'].append({'cert_id': cert_id, 'common_name': common_name,
                                        'error': 'Policy evaluation failed'})
                continue
            if held == 'declined':
                logger.info(f"Auto-renewal skipped cert {cert_id}: its renewal was rejected")
                stats['skipped'] += 1
                continue
            if held:
                stats['queued'] += 1
                continue

            success, result = AutoRenewalService.renew_certificate(cert, regenerate_crl=False, known_serial=listed_serial)

            if success:
                stats['renewed'] += 1
                # The renewal links the row to the CA that really signed it
                # (resolved by signature when the row named none): that CA's
                # CRL is the one carrying the superseded serial
                if cert.caref:
                    renewed_carefs.add(cert.caref)
            elif success is None:
                stats['skipped'] += 1
            else:
                stats['failed'] += 1
                stats['errors'].append({
                    'cert_id': cert_id,
                    'common_name': common_name,
                    'error': result
                })

        AutoRenewalService._publish_crls(carefs=renewed_carefs)
        logger.info(f"Auto-renewal complete: {stats['renewed']} renewed, {stats['failed']} failed")

        # Send notifications if configured
        if config.get('notify_on_renewal') and stats['renewed'] > 0:
            AutoRenewalService._send_renewal_notification(stats)

        if config.get('notify_on_failure') and stats['failed'] > 0:
            AutoRenewalService._send_failure_notification(stats)

        return stats

    @staticmethod
    def _publish_crls(carefs) -> None:
        """Generate the CRL of each CA named in ``carefs`` that publishes a
        CDP; one failure does not stop the others."""
        from services.crl import CRLService
        for refid in sorted(carefs or ()):
            try:
                ca = CA.query.filter_by(refid=refid).first()
                if ca is None or not ca.cdp_enabled:
                    continue
                CRLService.generate_crl(ca.id, username=AUTO_RENEWAL_ACTOR)
            except Exception as e:
                db.session.rollback()
                logger.error(f"CRL of CA {refid} not published after auto-renewal: {e}", exc_info=True)

    @staticmethod
    def _send_renewal_notification(stats: dict):
        """Send notification about successful renewals"""
        from services.email_service import EmailService

        recipients = SystemConfig.query.filter_by(key='auto_renewal_notify_emails').first()
        if not recipients:
            return

        emails = _json_list('auto_renewal_notify_emails', recipients.value)
        if emails is None:
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

        emails = _json_list('auto_renewal_notify_emails', recipients.value)
        if emails is None:
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
