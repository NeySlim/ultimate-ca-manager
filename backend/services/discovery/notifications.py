"""
Notifications mixin — sends email digest after a discovery scan completes.
"""
import logging
from typing import Dict
from models import db

logger = logging.getLogger(__name__)


class NotificationsMixin:

    def _send_notifications(self, profile_id: int, summary: Dict,
                            new_certs: int, changed_certs: int, expiring_ids=()):
        """Send email digest if profile has notifications enabled.

        *expiring_ids*: discovered certificates in the expiry window not yet
        reported under their fingerprint; they are marked reported once sent.
        """
        if not profile_id:
            return
        from models import ScanProfile
        profile = db.session.get(ScanProfile, profile_id)
        if not profile:
            return
        expiring_ids = list(expiring_ids or []) if profile.notify_on_expiry else []
        expiring_certs = len(expiring_ids)

        should_notify = (
            (profile.notify_on_new and new_certs > 0) or
            (profile.notify_on_change and changed_certs > 0) or
            (profile.notify_on_expiry and expiring_certs > 0)
        )
        if not should_notify:
            return

        try:
            from services.email_service import EmailService

            # The profile's address, else the SMTP sender, as the form says
            smtp = EmailService.get_smtp_config()
            recipient = profile.notify_email or (smtp.smtp_from if smtp else None)
            if not recipient:
                logger.info("Discovery notification skipped: no recipient configured")
                return
            recipients = [recipient]

            parts = []
            if new_certs > 0:
                parts.append(f"{new_certs} new unmanaged certificate(s)")
            if changed_certs > 0:
                parts.append(f"{changed_certs} certificate(s) changed")
            if expiring_certs > 0:
                parts.append(f"{expiring_certs} certificate(s) newly expiring or expired")

            from html import escape as html_escape
            safe_name = html_escape(profile.name)
            subject = f"[UCM] Discovery scan '{profile.name}': {', '.join(parts)}"
            body = (
                f"<h2>Discovery Scan Complete: {safe_name}</h2>"
                f"<p>Targets scanned: {summary['total_targets']}</p>"
                f"<p>Certificates found: {summary['certs_found']}</p>"
                f"<p>New unmanaged: <strong>{new_certs}</strong></p>"
                f"<p>Changed: <strong>{changed_certs}</strong></p>"
                f"<p>Newly expiring within 30 days or expired: "
                f"<strong style='color:#e67e22'>{expiring_certs}</strong></p>"
                f"<p>Errors: {summary['errors']}</p>"
            )

            sent, _detail = EmailService.send_email(
                recipients=recipients,
                subject=subject,
                body_html=body,
                body_text=body.replace('<p>', '').replace('</p>', '\n')
                              .replace('<h2>', '').replace('</h2>', '\n')
                              .replace('<strong>', '').replace('</strong>', ''),
                notification_type='discovery_scan',
                resource_type='discovery',
            )
            if not sent:
                logger.warning(f"Discovery notification not sent: {_detail}")
                return
            logger.info(f"Discovery notification sent to {len(recipients)} recipients")
            if expiring_ids:
                self._mark_expiry_reported(expiring_ids)
        except Exception as e:
            logger.warning(f"Failed to send discovery notification: {e}")

    @staticmethod
    def _expiring_in_window(profile_id):
        """``(count, ids)`` of the profile's certificates expiring within 30 days or
        expired; *ids* only those not yet reported under their current fingerprint."""
        from datetime import datetime, timedelta, timezone
        from models import DiscoveredCertificate
        if not profile_id:
            return 0, []
        threshold = datetime.now(timezone.utc) + timedelta(days=30)
        rows = DiscoveredCertificate.query.filter(
            DiscoveredCertificate.scan_profile_id == profile_id,
            DiscoveredCertificate.not_after.isnot(None),
            DiscoveredCertificate.not_after <= threshold,
            DiscoveredCertificate.scan_error.is_(None),
        ).all()
        return len(rows), [r.id for r in rows if r.expiry_notified_fingerprint != r.fingerprint_sha256]

    @staticmethod
    def _mark_expiry_reported(ids):
        from models import DiscoveredCertificate
        for row in DiscoveredCertificate.query.filter(DiscoveredCertificate.id.in_(ids)).all():
            row.expiry_notified_fingerprint = row.fingerprint_sha256
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.warning(f"Could not record the expiry alerts sent: {e}")
