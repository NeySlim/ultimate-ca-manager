"""
CRL Scheduler Task - Automatic CRL Regeneration
Monitors CRL expiration / publish schedule and regenerates when needed
"""
import logging
from typing import Optional

from models import db, CA
from models.crl import CRLMetadata
from services.crl_service import CRLService
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class CRLSchedulerTask:
    """
    Handles automatic CRL regeneration based on publish schedule and expiration.

    Strategy:
    - Prefer ``next_publish`` when set (decoupled from nextUpdate validity)
    - Else regenerate when within threshold of next_update (default 24h)
    - Always regenerate if no base CRL or next_update has passed
    """

    # Fallback when next_publish is unset: regenerate this many hours before next_update
    REGENERATION_THRESHOLD_HOURS = 24

    @staticmethod
    def should_regenerate_crl(ca_id: int) -> tuple[bool, Optional[str]]:
        """
        Check if a CA's full CRL should be regenerated.

        Returns:
            Tuple of (should_regenerate: bool, reason: str or None)
        """
        try:
            ca = db.session.get(CA, ca_id)
            if not ca:
                return False, f"CA {ca_id} not found"

            if not ca.has_private_key:
                return False, f"CA '{ca.descr}' has no private key"

            latest_crl = CRLMetadata.query.filter_by(
                ca_id=ca_id, is_delta=False
            ).order_by(CRLMetadata.crl_number.desc()).first()

            if not latest_crl:
                return True, f"No CRL exists for CA '{ca.descr}' - needs generation"

            now = utc_now()

            if latest_crl.is_stale:
                return True, f"CRL is stale for CA '{ca.descr}' - needs regeneration"

            if latest_crl.next_publish is not None and now >= latest_crl.next_publish:
                return (
                    True,
                    f"CRL publish due for CA '{ca.descr}' "
                    f"(next_publish={latest_crl.next_publish.isoformat()})"
                )

            hours_until_expiry = (latest_crl.next_update - now).total_seconds() / 3600
            if hours_until_expiry <= CRLSchedulerTask.REGENERATION_THRESHOLD_HOURS:
                return (
                    True,
                    f"CRL expires in {hours_until_expiry:.1f}h for CA '{ca.descr}' "
                    f"(threshold: {CRLSchedulerTask.REGENERATION_THRESHOLD_HOURS}h)"
                )

            return False, None

        except Exception as e:
            logger.error(f"Error checking CRL regeneration for CA {ca_id}: {e}", exc_info=True)
            return False, f"Error: {str(e)}"

    @staticmethod
    def regenerate_crl(ca_id: int, username: str = "scheduler") -> bool:
        """Regenerate full CRL for a specific CA."""
        try:
            ca = db.session.get(CA, ca_id)
            if not ca:
                logger.error(f"Cannot regenerate CRL: CA {ca_id} not found")
                return False

            logger.info(f"Regenerating CRL for CA '{ca.descr}' (ID: {ca_id})")

            crl_metadata = CRLService.generate_crl(
                ca_id=ca_id,
                username=username
            )

            logger.info(
                f"Successfully generated CRL for CA '{ca.descr}' "
                f"(#{crl_metadata.crl_number}, {crl_metadata.revoked_count} revoked certs)"
            )
            return True

        except Exception as e:
            logger.error(
                f"Error regenerating CRL for CA {ca_id}: {e}",
                exc_info=True
            )
            return False

    @staticmethod
    def execute() -> None:
        """
        Main task to check all CAs and regenerate CRLs as needed.
        Called by scheduler every N seconds.
        """
        try:
            logger.debug("Starting CRL regeneration check")

            cas_with_cdp = CA.query.filter_by(cdp_enabled=True).all()
            cas_with_keys = [ca for ca in cas_with_cdp if ca.has_private_key]

            if not cas_with_keys:
                logger.debug("No CAs with CDP enabled and private key found")
                return

            regenerated_count = 0
            skipped_count = 0
            error_count = 0

            for ca in cas_with_keys:
                should_regen, reason = CRLSchedulerTask.should_regenerate_crl(ca.id)

                if should_regen:
                    logger.info(f"Regenerating CRL: {reason}")
                    success = CRLSchedulerTask.regenerate_crl(ca.id)
                    if success:
                        regenerated_count += 1
                    else:
                        error_count += 1
                else:
                    if reason:
                        logger.debug(f"Skipping CRL regeneration: {reason}")
                    skipped_count += 1

            logger.info(
                f"CRL regeneration check complete: "
                f"regenerated={regenerated_count}, "
                f"skipped={skipped_count}, "
                f"errors={error_count}"
            )

            # Check delta CRLs for CAs with delta enabled
            # NOTE: has_private_key is a @property — filter in Python
            delta_cas = [
                ca for ca in CA.query.filter_by(cdp_enabled=True, delta_crl_enabled=True).all()
                if ca.has_private_key
            ]

            delta_count = 0
            for ca in delta_cas:
                try:
                    latest_delta = CRLService.get_latest_delta_crl(ca.id)
                    interval_hours = ca.delta_crl_interval or 4

                    need_delta = False
                    if not latest_delta:
                        base = CRLService.get_latest_base_crl(ca.id)
                        if base:
                            need_delta = True
                    elif latest_delta.is_stale:
                        need_delta = True
                    else:
                        age_hours = (utc_now() - latest_delta.this_update).total_seconds() / 3600
                        if age_hours >= interval_hours:
                            need_delta = True

                    if need_delta:
                        CRLService.generate_delta_crl(
                            ca.id,
                            validity_hours=interval_hours * 2,
                            username='scheduler'
                        )
                        delta_count += 1
                except Exception as e:
                    logger.error(f"Error generating delta CRL for CA {ca.id}: {e}")

            if delta_count > 0:
                logger.info(f"Generated {delta_count} delta CRL(s)")

        except Exception as e:
            logger.error(f"Error in CRL regeneration task: {e}", exc_info=True)


def get_crl_scheduler_task():
    """Factory function to get CRL scheduler task"""
    return CRLSchedulerTask.execute
