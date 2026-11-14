"""
CRL Scheduler Task - Automatic CRL Regeneration
Monitors CRL expiration and regenerates when needed
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fips_mode import FipsRestricted
from models import db, CA
from models.crl import CRLMetadata
from services.crl_service import CRLService
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class CRLSchedulerTask:
    """
    Handles automatic CRL regeneration based on expiration
    
    Strategy:
    - Check all CAs with private keys
    - For each CA, get latest CRL
    - If CRL is within threshold of expiration (or missing), regenerate
    - Default threshold: regenerate when 24 hours before expiration
    """
    
    # Regenerate CRL when this many hours before expiration
    REGENERATION_THRESHOLD_HOURS = 24
    
    @staticmethod
    def should_regenerate_crl(ca_id: int) -> tuple[bool, Optional[str]]:
        """
        Check if a CA's CRL should be regenerated
        
        Args:
            ca_id: CA database ID
            
        Returns:
            Tuple of (should_regenerate: bool, reason: str or None)
        """
        try:
            ca = db.session.get(CA, ca_id)
            if not ca:
                return False, f"CA {ca_id} not found"
            
            # Skip if no private key (can't sign CRL)
            if not ca.has_private_key:
                return False, f"CA '{ca.descr}' has no private key"

            # Skip pending external-CSR CAs (no certificate yet)
            if not ca.crt:
                return False, f"CA '{ca.descr}' is awaiting its certificate"
            
            # Get latest CRL
            latest_crl = CRLMetadata.query.filter_by(
                ca_id=ca_id, is_delta=False
            ).order_by(CRLMetadata.created_at.desc()).first()
            
            if not latest_crl:
                return True, f"No CRL exists for CA '{ca.descr}' - needs generation"
            
            # Check if CRL is stale (past next_update)
            if latest_crl.is_stale:
                return True, f"CRL is stale for CA '{ca.descr}' - needs regeneration"
            
            # Publish cadence decoupled from validity (#207): when configured,
            # republish once the latest CRL is older than the interval, well
            # before nextUpdate — the validity margin is the grace period.
            if ca.crl_publish_interval_hours:
                age_hours = (utc_now() - latest_crl.this_update).total_seconds() / 3600
                if age_hours >= ca.crl_publish_interval_hours:
                    return (
                        True,
                        f"CRL publish interval reached for CA '{ca.descr}' "
                        f"(age {age_hours:.1f}h >= {ca.crl_publish_interval_hours}h)"
                    )

            # Check if approaching expiration
            hours_until_expiry = latest_crl.days_until_expiry * 24
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
        """
        Regenerate CRL for a specific CA
        
        Args:
            ca_id: CA database ID
            username: Username to record in audit log
            
        Returns:
            True if successful, False if failed
        """
        try:
            ca = db.session.get(CA, ca_id)
            if not ca:
                logger.error(f"Cannot regenerate CRL: CA {ca_id} not found")
                return False
            
            logger.info(f"Regenerating CRL for CA '{ca.descr}' (ID: {ca_id})")
            
            # Generate new CRL using CRLService
            crl_metadata = CRLService.generate_crl(
                ca_id=ca_id,
                username=username
            )
            
            logger.info(
                f"Successfully generated CRL for CA '{ca.descr}' "
                f"(#{ crl_metadata.crl_number}, {crl_metadata.revoked_count} revoked certs)"
            )
            return True

        except FipsRestricted as e:
            # Expected state, repeated every pass until the CA changes: one line, no trace
            logger.warning(f"CRL of CA {ca_id} not signed: {e}")
            return False
        except Exception as e:
            logger.error(
                f"Error regenerating CRL for CA {ca_id}: {e}",
                exc_info=True
            )
            return False
    
    # HA: the CRL of a CA is published by one node at a time; a dead holder's lease ends
    LEASE = timedelta(minutes=15)

    @staticmethod
    def _under_lease(ca_id: int, run, retries=None):
        """*run(ca_id)* on the node holding the CA's lease, None on the others, which append to
        *retries* when that lease frees. Due-ness is read again by *run* under the lease: a CRL
        committed by the previous holder counts."""
        from utils.ha import ha_enabled
        if not ha_enabled():
            return run(ca_id)
        from utils.config_cas import ConfigLease
        lease = ConfigLease(f'crl_schedule_lease_{ca_id}', CRLSchedulerTask.LEASE)
        try:
            if not lease.take():
                logger.info(f"CRL of CA {ca_id} left to the node publishing it")
                if retries is not None and lease.retry_in() is not None:
                    retries.append(lease.retry_in())
                return None
        except Exception as e:
            db.session.rollback()
            logger.error(f"CRL of CA {ca_id} not reserved: {e}")
            return False
        try:
            return run(ca_id)
        finally:
            lease.end()

    @staticmethod
    def _regenerate_if_due(ca_id: int):
        should_regen, reason = CRLSchedulerTask.should_regenerate_crl(ca_id)
        if not should_regen:
            return None
        logger.info(f"Regenerating CRL: {reason}")
        return CRLSchedulerTask.regenerate_crl(ca_id)

    @staticmethod
    def _delta_interval_if_due(ca_id: int):
        """The CA's delta interval in hours when its delta CRL is due, else None."""
        ca = db.session.get(CA, ca_id)
        interval_hours = ca.delta_crl_interval or 4
        latest_delta = CRLService.get_latest_delta_crl(ca_id)
        if not latest_delta:
            # Only generate delta if a base CRL exists
            return interval_hours if CRLService.get_latest_base_crl(ca_id) else None
        if latest_delta.is_stale:
            return interval_hours
        age_hours = (utc_now() - latest_delta.this_update).total_seconds() / 3600
        return interval_hours if age_hours >= interval_hours else None

    @staticmethod
    def _delta_if_due(ca_id: int):
        interval_hours = CRLSchedulerTask._delta_interval_if_due(ca_id)
        if interval_hours is None:
            return None
        CRLService.generate_delta_crl(ca_id, validity_hours=interval_hours * 2, username='scheduler')
        return True

    @staticmethod
    def execute():
        """
        Main task to check all CAs and regenerate CRLs as needed
        Called by scheduler every N seconds. A CA left to the node holding its lease asks
        one retry of the whole pass once the last such lease is over.
        """
        retries = []
        try:
            logger.debug("Starting CRL regeneration check")
            
            # Get all CAs with CDP enabled (auto-regen)
            # NOTE: has_private_key is a @property, NOT a DB column — cannot use filter_by
            # Offline CAs are excluded: in password_protected mode the key is
            # still present but passphrase-encrypted, so has_private_key is
            # true while signing is impossible — attempting it raised a
            # traceback on every cycle instead of a skip.
            cas_with_cdp = CA.query.filter_by(cdp_enabled=True).all()
            cas_with_keys = [
                ca for ca in cas_with_cdp
                if ca.has_private_key and ca.crt and not ca.offline
            ]
            offline_skipped = sum(
                1 for ca in cas_with_cdp if ca.has_private_key and ca.offline
            )
            if offline_skipped:
                logger.debug(
                    "CRL regeneration: %s offline CA(s) skipped", offline_skipped
                )
            
            if not cas_with_keys:
                logger.debug("No CAs with CDP enabled and private key found")
                return
            
            regenerated_count = 0
            skipped_count = 0
            error_count = 0
            
            for ca in cas_with_keys:
                ca_id = ca.id
                should_regen, reason = CRLSchedulerTask.should_regenerate_crl(ca_id)
                
                if should_regen:
                    success = CRLSchedulerTask._under_lease(ca_id, CRLSchedulerTask._regenerate_if_due,
                                                            retries)
                    if success is None:
                        skipped_count += 1
                    elif success:
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
                if ca.has_private_key and ca.crt and not ca.offline
            ]
            
            delta_count = 0
            for ca in delta_cas:
                ca_id = ca.id
                try:
                    if CRLSchedulerTask._delta_interval_if_due(ca_id) is not None \
                            and CRLSchedulerTask._under_lease(ca_id, CRLSchedulerTask._delta_if_due, retries):
                        delta_count += 1
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Error generating delta CRL for CA {ca_id}: {e}")
            
            if delta_count > 0:
                logger.info(f"Generated {delta_count} delta CRL(s)")
        
        except Exception as e:
            logger.error(f"Error in CRL regeneration task: {e}", exc_info=True)
        if retries:
            return {'status': 'ok', 'retry_in': max(retries)}
        return None


def get_crl_scheduler_task():
    """Factory function to get CRL scheduler task"""
    return CRLSchedulerTask.execute
