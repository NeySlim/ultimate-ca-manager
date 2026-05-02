"""Order management mixin for ACME service"""
import secrets
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from models import db
from models.acme_models import AcmeOrder, AcmeAuthorization, AcmeChallenge
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class OrderMixin:
    def create_order(
        self,
        account_id: str,
        identifiers: List[Dict[str, str]],
        not_before: Optional[datetime] = None,
        not_after: Optional[datetime] = None
    ) -> AcmeOrder:
        """Create a new certificate order
        
        Args:
            account_id: ACME account ID
            identifiers: List of identifiers [{"type": "dns", "value": "example.com"}]
            not_before: Requested validity start (optional)
            not_after: Requested validity end (optional)
            
        Returns:
            AcmeOrder object
        """
        order = AcmeOrder(
            account_id=account_id,
            status="pending",
            identifiers=json.dumps(identifiers),
            not_before=not_before,
            not_after=not_after,
            expires=utc_now() + timedelta(days=7)
        )
        
        db.session.add(order)
        db.session.flush()  # Get order.order_id
        
        # Create authorizations for each identifier
        for identifier in identifiers:
            auth = self._create_authorization(
                order_id=order.order_id,
                identifier=identifier,
                account_id=account_id
            )
            order.authorizations.append(auth)
        
        # Check if all authorizations are already valid (reuse case)
        # If so, set order to "ready" immediately
        if order.authorizations and all(a.status == "valid" for a in order.authorizations):
            order.status = "ready"
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"DB commit failed: {e}")
            raise
        
        return order
    
    def _create_authorization(
        self,
        order_id: str,
        identifier: Dict[str, str],
        account_id: str = None
    ) -> AcmeAuthorization:
        """Create authorization with challenges (checking for reuse)
        
        Args:
            order_id: Parent order ID
            identifier: Identifier dict {"type": "dns", "value": "example.com"}
            account_id: Account ID for authorization reuse lookup
            
        Returns:
            AcmeAuthorization object
        """
        # Check for existing valid authorization for this account/identifier (Authorization Reuse)
        if account_id:
            try:
                identifier_json = json.dumps(identifier)
                
                # Check both order-linked and standalone (pre-auth) authorizations
                valid_auth = AcmeAuthorization.query.filter(
                    AcmeAuthorization.account_id == account_id,
                    AcmeAuthorization.identifier == identifier_json,
                    AcmeAuthorization.status == 'valid',
                    AcmeAuthorization.expires > utc_now()
                ).order_by(AcmeAuthorization.expires.desc()).first()
                
                if valid_auth:
                    # Reuse found! Create a new pre-validated authorization
                    auth = AcmeAuthorization(
                        order_id=order_id,
                        account_id=account_id,
                        status="valid",
                        identifier=identifier_json,
                        expires=valid_auth.expires
                    )
                    
                    db.session.add(auth)
                    db.session.flush()
                    
                    # Create pre-validated challenges (clients may check them)
                    self._create_challenges(auth, status="valid", validated=utc_now())
                    
                    return auth
            except Exception as e:
                # Log but continue with new auth
                logger.error(f"Error checking auth reuse: {e}")

        # Check if this identifier is auto-approved (issue #69)
        # Admin-configured domains with auto_approve=True skip challenges:
        # the authorization is created directly in `valid` state and the
        # order will move straight to `ready`. Only applies to dns-typed
        # identifiers and only when UCM issues locally.
        if identifier.get('type') == 'dns':
            domain_value = identifier.get('value', '')
            if self._is_domain_auto_approved(domain_value):
                logger.warning(
                    "ACME auto-approve: skipping challenge validation for "
                    f"{domain_value} (account={account_id}, order={order_id})"
                )
                try:
                    from services.audit_service import AuditService
                    AuditService.log_action(
                        username='acme',
                        action='acme_auto_approve',
                        resource_type='acme_authorization',
                        resource_id=domain_value,
                        details={
                            'domain': domain_value,
                            'account_id': account_id,
                            'order_id': order_id,
                        },
                        success=True
                    )
                except Exception as audit_err:
                    logger.error(f"Failed to audit auto-approve: {audit_err}")

                auth = AcmeAuthorization(
                    order_id=order_id,
                    account_id=account_id,
                    status='valid',
                    identifier=json.dumps(identifier),
                    wildcard=identifier.get('value', '').startswith('*.'),
                    expires=utc_now() + timedelta(days=7),
                )
                db.session.add(auth)
                db.session.flush()
                self._create_challenges(auth, status='valid', validated=utc_now())
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"DB commit failed: {e}")
                    raise
                return auth

        # No reuse - create new pending authorization
        auth = AcmeAuthorization(
            order_id=order_id,
            account_id=account_id,
            status="pending",
            identifier=json.dumps(identifier),
            expires=utc_now() + timedelta(days=7)
        )
        
        db.session.add(auth)
        db.session.flush()  # Get auth.authorization_id
        
        # Create pending challenges
        self._create_challenges(auth, status="pending")
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"DB commit failed: {e}")
            raise
        
        return auth
    
    def create_pre_authorization(
        self,
        account_id: str,
        identifier: Dict[str, str]
    ) -> AcmeAuthorization:
        """Create standalone pre-authorization (RFC 8555 §7.4.1)
        
        Pre-authorizations are created via newAuthz endpoint before
        placing an order. They can be reused when the order is created.
        
        Args:
            account_id: Account ID requesting pre-authorization
            identifier: Identifier dict {"type": "dns", "value": "example.com"}
            
        Returns:
            AcmeAuthorization object
        """
        # Check for existing valid authorization
        identifier_json = json.dumps(identifier)
        
        existing = AcmeAuthorization.query.filter(
            AcmeAuthorization.account_id == account_id,
            AcmeAuthorization.identifier == identifier_json,
            AcmeAuthorization.status == 'valid',
            AcmeAuthorization.expires > utc_now()
        ).first()
        
        if existing:
            return existing
        
        # Create new pending authorization (no order_id)
        is_wildcard = identifier.get('value', '').startswith('*.')

        # Issue #69: honor auto_approve on admin-configured domains (dns type only)
        domain_value = identifier.get('value', '')
        skip_challenges = (
            identifier.get('type') == 'dns'
            and domain_value
            and self._is_domain_auto_approved(domain_value)
        )
        initial_status = 'valid' if skip_challenges else 'pending'

        auth = AcmeAuthorization(
            order_id=None,
            account_id=account_id,
            status=initial_status,
            identifier=identifier_json,
            wildcard=is_wildcard,
            expires=utc_now() + timedelta(days=7)
        )
        
        db.session.add(auth)
        db.session.flush()
        
        if skip_challenges:
            self._create_challenges(auth, status='valid', validated=utc_now())
            try:
                from services.audit_service import AuditService
                AuditService.log_action(
                    username='acme',
                    action='acme_auto_approve',
                    resource_type='acme_authorization',
                    resource_id=str(auth.id),
                    details={
                        'domain': domain_value,
                        'account_id': account_id,
                        'flow': 'pre_authorization',
                    },
                )
            except Exception as audit_exc:
                logger.warning(f"Audit log for auto_approve failed: {audit_exc}")
        else:
            self._create_challenges(auth, status="pending")
        
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"DB commit failed: {e}")
            raise
        
        return auth

    @staticmethod
    def _is_domain_auto_approved(domain: str) -> bool:
        """Check whether an identifier should skip ACME challenges (issue #69).

        An identifier is auto-approved when either table matches the domain
        (exact or parent, case-insensitive, wildcard-stripped) AND the entry
        has ``auto_approve=True``.

        - ``AcmeLocalDomain`` — internal ACME issuance
        - ``AcmeDomain`` — DNS-provider-mapped issuance

        Returns False on any error so the default stays "require challenge".
        """
        if not domain:
            return False
        try:
            normalized = domain.strip().lower()
            if normalized.startswith('*.'):
                normalized = normalized[2:]
            if not normalized:
                return False

            from models.acme_models import AcmeDomain, AcmeLocalDomain

            candidates = [normalized]
            parts = normalized.split('.')
            for i in range(1, len(parts)):
                candidates.append('.'.join(parts[i:]))

            for candidate in candidates:
                local = AcmeLocalDomain.query.filter_by(domain=candidate).first()
                if local and local.auto_approve:
                    return True
                public = AcmeDomain.query.filter_by(domain=candidate).first()
                if public and public.auto_approve:
                    return True
        except Exception as exc:
            logger.error(f"auto_approve lookup failed for {domain}: {exc}")
            return False

        return False

    def _create_challenges(self, auth: AcmeAuthorization, status: str, validated: datetime = None):
        """Helper to create standard challenges for an authorization"""
        # HTTP-01 Challenge
        http_token = secrets.token_urlsafe(32)
        http_challenge = AcmeChallenge(
            authorization_id=auth.authorization_id,
            type="http-01",
            status=status,
            token=http_token,
            url=f"{self.base_url}/acme/challenge/{secrets.token_urlsafe(16)}",
            validated=validated
        )
        auth.challenges.append(http_challenge)
        
        # DNS-01 Challenge
        dns_token = secrets.token_urlsafe(32)
        dns_challenge = AcmeChallenge(
            authorization_id=auth.authorization_id,
            type="dns-01",
            status=status,
            token=dns_token,
            url=f"{self.base_url}/acme/challenge/{secrets.token_urlsafe(16)}",
            validated=validated
        )
        auth.challenges.append(dns_challenge)
        
        # TLS-ALPN-01 Challenge (RFC 8737)
        tls_token = secrets.token_urlsafe(32)
        tls_challenge = AcmeChallenge(
            authorization_id=auth.authorization_id,
            type="tls-alpn-01",
            status=status,
            token=tls_token,
            url=f"{self.base_url}/acme/challenge/{secrets.token_urlsafe(16)}",
            validated=validated
        )
        auth.challenges.append(tls_challenge)
    
    def get_order(self, order_id: str) -> Optional[AcmeOrder]:
        """Get order by ID
        
        Args:
            order_id: Order identifier
            
        Returns:
            AcmeOrder or None
        """
        return AcmeOrder.query.filter_by(order_id=order_id).first()
    
    def get_challenge(self, challenge_id: str) -> Optional[AcmeChallenge]:
        """Get challenge by ID
        
        Args:
            challenge_id: Challenge identifier
            
        Returns:
            AcmeChallenge or None
        """
        return AcmeChallenge.query.filter_by(challenge_id=challenge_id).first()
