"""
Notifications mixin — sends email digest after a discovery scan completes.
"""
import logging
from typing import Dict
from models import db

logger = logging.getLogger(__name__)


class NotificationsMixin:

    def _send_notifications(self, profile_id: int, summary: Dict,
                            new_certs: int, changed_certs: int, expiring_certs: int = 0):
        """Send email digest if profile has notifications enabled."""
        if not profile_id:
            return
        from models import ScanProfile
        profile = db.session.get(ScanProfile, profile_id)
        if not profile:
            return

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
                parts.append(f"{expiring_certs} certificate(s) expiring soon")

            from html import escape as html_escape
            safe_name = html_escape(profile.name)
            subject = f"[UCM] Discovery scan '{profile.name}': {', '.join(parts)}"
            body = (
                f"<h2>Discovery Scan Complete: {safe_name}</h2>"
                f"<p>Targets scanned: {summary['total_targets']}</p>"
                f"<p>Certificates found: {summary['certs_found']}</p>"
                f"<p>New unmanaged: <strong>{new_certs}</strong></p>"
                f"<p>Changed: <strong>{changed_certs}</strong></p>"
                f"<p>Expiring within 30 days: <strong style='color:#e67e22'>{expiring_certs}</strong></p>"
                f"<p>Errors: {summary['errors']}</p>"
            )

            EmailService.send_email(
                recipients=recipients,
                subject=subject,
                body_html=body,
                body_text=body.replace('<p>', '').replace('</p>', '\n')
                              .replace('<h2>', '').replace('</h2>', '\n')
                              .replace('<strong>', '').replace('</strong>', ''),
                notification_type='discovery_scan',
                resource_type='discovery',
            )
            logger.info(f"Discovery notification sent to {len(recipients)} recipients")
        except Exception as e:
            logger.warning(f"Failed to send discovery notification: {e}")
