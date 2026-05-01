"""Account management mixin for ACME service"""
import json
import logging
from typing import Optional, Dict, Any, List, Tuple

from models import db
from models.acme_models import AcmeAccount
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class AccountMixin:
    def create_account(
        self, 
        jwk: Dict[str, Any],
        contact: List[str] = None,
        terms_of_service_agreed: bool = False,
        external_account_binding: Dict[str, Any] = None
    ) -> Tuple[AcmeAccount, bool]:
        """Create or retrieve ACME account
        
        Args:
            jwk: JSON Web Key (public key)
            contact: List of contact URIs (e.g., mailto:admin@example.com)
            terms_of_service_agreed: Whether client agreed to ToS
            external_account_binding: EAB for restricted servers (optional)
            
        Returns:
            Tuple of (AcmeAccount, is_new_account)
        """
        # Generate JWK thumbprint for deduplication
        jwk_thumbprint = self._compute_jwk_thumbprint(jwk)
        
        # Check if account already exists
        existing = AcmeAccount.query.filter_by(
            jwk_thumbprint=jwk_thumbprint
        ).first()
        
        if existing:
            # Return existing account
            return existing, False
        
        # Create new account
        account = AcmeAccount(
            jwk=json.dumps(jwk),
            jwk_thumbprint=jwk_thumbprint,
            contact=json.dumps(contact) if contact else None,
            status="valid",
            terms_of_service_agreed=terms_of_service_agreed,
            created_at=utc_now()
        )
        
        db.session.add(account)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"DB commit failed: {e}")
            raise
        
        return account, True
    
    def get_account_by_kid(self, account_id: str) -> Optional[AcmeAccount]:
        """Get account by Key ID (account URL)
        
        Args:
            account_id: Account identifier from URL
            
        Returns:
            AcmeAccount or None
        """
        return AcmeAccount.query.filter_by(account_id=account_id).first()
    
    def deactivate_account(self, account_id: str) -> bool:
        """Deactivate an ACME account
        
        Args:
            account_id: Account identifier
            
        Returns:
            True if successful
        """
        account = self.get_account_by_kid(account_id)
        if not account:
            return False
        
        account.status = "deactivated"
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"DB commit failed: {e}")
            raise
        
        return True
