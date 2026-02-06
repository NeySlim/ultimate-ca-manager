"""
CRL Scheduler Task - Automatic CRL Regeneration
Monitors CRL expiration and regenerates when needed
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from models import db, CA
from models.crl import CRLMetadata
from services.crl_service import CRLService

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
            ca = CA.query.get(ca_id)
            if not ca:
                return False, f"CA {ca_id} not found"
            
            # Skip if no private key (can't sign CRL)
            if not ca.has_private_key:
                return False, f"CA '{ca.descr}' has no private key"
            
            # Get latest CRL
            latest_crl = CRLMetadata.query.filter_by(
                ca_id=ca_id
            ).order_by(CRLMetadata.created_at.desc()).first()
            
            if not latest_crl:
                return True, f"No CRL exists for CA '{ca.descr}' - needs generation"
            
            # Check if CRL is stale (past next_update)
            if latest_crl.is_stale:
                return True, f"CRL is stale for CA '{ca.descr}' - needs regeneration"
            
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
            ca = CA.query.get(ca_id)
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
        
        except Exception as e:
            logger.error(
                f"Error regenerating CRL for CA {ca_id}: {e}",
                exc_info=True
            )
            return False
    
    @staticmethod
    def execute() -> None:
        """
        Main task to check all CAs and regenerate CRLs as needed
        Called by scheduler every N seconds
        """
        try:
            logger.debug("Starting CRL regeneration check")
            
            # Get all CAs with private keys
            cas_with_keys = CA.query.filter_by(has_private_key=True).all()
            
            if not cas_with_keys:
                logger.debug("No CAs with private keys found")
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
        
        except Exception as e:
            logger.error(f"Error in CRL regeneration task: {e}", exc_info=True)


def get_crl_scheduler_task():
    """Factory function to get CRL scheduler task"""
    return CRLSchedulerTask.execute
