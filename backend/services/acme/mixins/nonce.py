"""Nonce management mixin for ACME service"""
import secrets
import logging
from datetime import timedelta

from models import db
from models.acme_models import AcmeNonce
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class NonceMixin:
    def generate_nonce(self) -> str:
        """Generate a new cryptographically secure nonce
        
        Returns:
            Nonce token (32 bytes, URL-safe base64)
        """
        nonce_token = secrets.token_urlsafe(32)
        
        # Store in database with 1 hour expiry
        nonce = AcmeNonce(
            token=nonce_token,
            expires_at=utc_now() + timedelta(hours=1)
        )
        db.session.add(nonce)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"DB commit failed: {e}")
            raise
        
        return nonce_token
    
    def validate_nonce(self, nonce_token: str) -> bool:
        """Validate and consume a nonce atomically (one-time use)
        
        Args:
            nonce_token: The nonce to validate
            
        Returns:
            True if valid, False otherwise
        """
        from sqlalchemy import and_
        # Atomic: update used=True WHERE token=X AND used=False AND not expired
        result = AcmeNonce.query.filter(
            and_(
                AcmeNonce.token == nonce_token,
                AcmeNonce.used == False,
                AcmeNonce.expires_at > utc_now()
            )
        ).update({
            'used': True,
            'used_at': utc_now()
        })
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"DB commit failed: {e}")
            raise
        return result > 0
    
    def cleanup_expired_nonces(self) -> int:
        """Remove expired nonces from database
        
        Returns:
            Number of nonces deleted
        """
        expired = AcmeNonce.query.filter(
            AcmeNonce.expires_at < utc_now()
        ).all()
        
        count = len(expired)
        for nonce in expired:
            db.session.delete(nonce)
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"DB commit failed: {e}")
            raise
        return count
