"""Order management mixin for ACME service"""
import secrets
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy.orm.attributes import set_committed_value

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
        not_after: Optional[datetime] = None,
        replaces: Optional[str] = None,
        profile: Optional[str] = None,
    ) -> AcmeOrder:
        """Create a new certificate order

        Args:
            account_id: ACME account ID
            identifiers: List of identifiers [{"type": "dns", "value": "example.com"}]
            not_before: Requested validity start (optional)
            not_after: Requested validity end (optional)
            replaces: RFC 9773 CertID replaced by this order (optional)
            profile: Selected ACME certificate profile name (optional)

        Returns:
            AcmeOrder object
        """
        order = AcmeOrder(
            account_id=account_id,
            status="pending",
            identifiers=json.dumps(identifiers),
            not_before=not_before,
            not_after=not_after,
            replaces=replaces,
            profile=profile,
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
    
    @staticmethod
    def _normalize_authorization_identifier(
        identifier: Dict[str, str]
    ) -> tuple[Dict[str, str], bool]:
        """Return the RFC 8555 authorization identifier and wildcard flag."""
        value = identifier.get('value', '')
        is_wildcard = (
            identifier.get('type') == 'dns'
            and isinstance(value, str)
            and value.startswith('*.')
        )
        normalized = {
            **identifier,
            'value': value[2:] if is_wildcard else value,
        }
        return normalized, is_wildcard

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
        authorization_identifier, is_wildcard = self._normalize_authorization_identifier(
            identifier
        )
        identifier_json = json.dumps(authorization_identifier)

        # Check for existing valid authorization for this account/identifier (Authorization Reuse)
        if account_id:
            try:
                
                # Check both order-linked and standalone (pre-auth) authorizations.
                # Must match the wildcard flag too: after identifier normalization
                # strips the "*." prefix, a wildcard and a base-domain authorization
                # share the same identifier JSON. Reusing a non-wildcard authz
                # (validatable via HTTP-01) for a wildcard order would let an
                # apex web-control prove a wildcard, bypassing RFC 8555 §8.4.
                valid_auth = AcmeAuthorization.query.filter(
                    AcmeAuthorization.account_id == account_id,
                    AcmeAuthorization.identifier == identifier_json,
                    AcmeAuthorization.wildcard == is_wildcard,
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
                        wildcard=is_wildcard,
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
                    identifier=identifier_json,
                    wildcard=is_wildcard,
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
            identifier=identifier_json,
            wildcard=is_wildcard,
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
        authorization_identifier, is_wildcard = self._normalize_authorization_identifier(
            identifier
        )
        identifier_json = json.dumps(authorization_identifier)
        
        # wildcard must match: a normalized identifier is shared between a
        # wildcard and its base domain, so reuse must not cross that boundary
        # (RFC 8555 §8.4 — wildcard requires dns-01).
        existing = AcmeAuthorization.query.filter(
            AcmeAuthorization.account_id == account_id,
            AcmeAuthorization.identifier == identifier_json,
            AcmeAuthorization.wildcard == is_wildcard,
            AcmeAuthorization.status == 'valid',
            AcmeAuthorization.expires > utc_now()
        ).first()

        if existing:
            return existing
        
        # Create new pending authorization (no order_id)
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
        """Helper to create standard challenges for an authorization.

        RFC 8555 §7.1.3 / §8.4: wildcard identifiers (``*.example.com``)
        MUST NOT be validated via HTTP-01 or TLS-ALPN-01 — only DNS-01.
        Offering the others would let an attacker who controls a single host
        under the apex obtain a wildcard cert covering the entire zone.
        
        RFC 8738: IP identifiers MUST NOT be validated via DNS-01 — only
        HTTP-01 and TLS-ALPN-01.
        """
        # Detect identifier type and wildcard status
        identifier_type = auth.identifier_type
        value = auth.identifier_value
        is_wildcard = auth.wildcard is True or (
            isinstance(value, str) and value.startswith('*.')
        )
        is_ip = identifier_type == 'ip'

        # DNS-01 Challenge — DNS identifiers only (RFC 8738 forbids DNS-01 for IPs)
        if not is_ip:
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

        if is_wildcard:
            # Per RFC 8555 §8.4 — wildcard MUST be DNS-01 only
            # Note: wildcards are only valid for DNS identifiers, not IPs
            return

        # HTTP-01 Challenge (DNS non-wildcard + IP identifiers)
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

        # TLS-ALPN-01 Challenge (RFC 8737/8738) — DNS non-wildcard + IP identifiers
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
    
    @staticmethod
    def _problem_data(error_type: str, detail: str) -> Dict[str, Any]:
        return {
            'type': f'urn:ietf:params:acme:error:{error_type}',
            'detail': detail,
        }

    @classmethod
    def _problem(cls, error_type: str, detail: str) -> str:
        return json.dumps(cls._problem_data(error_type, detail))

    @staticmethod
    def _challenge_problem(challenge: AcmeChallenge) -> Dict[str, Any]:
        try:
            problem = (
                json.loads(challenge.error)
                if isinstance(challenge.error, str)
                else challenge.error
            )
        except (TypeError, ValueError):
            problem = None
        if not isinstance(problem, dict):
            return {
                'type': 'urn:ietf:params:acme:error:malformed',
                'detail': 'Authorization failed',
            }
        return {
            'type': problem.get(
                'type', 'urn:ietf:params:acme:error:malformed'
            ),
            'detail': problem.get('detail', 'Authorization failed'),
        }

    def _set_order_authorization_error(
        self,
        order: AcmeOrder,
        fallback: Dict[str, Any],
    ) -> None:
        """Store a compound problem when multiple authorizations failed."""
        failed_authorizations = order.authorizations.filter_by(
            status='invalid'
        ).order_by(AcmeAuthorization.id).all()
        subproblems = []
        for authorization in failed_authorizations:
            challenge = authorization.challenges.filter_by(
                status='invalid'
            ).order_by(AcmeChallenge.id).first()
            problem = (
                self._challenge_problem(challenge)
                if challenge is not None
                else {
                    'type': 'urn:ietf:params:acme:error:malformed',
                    'detail': 'Authorization failed',
                }
            )
            subproblems.append({
                **problem,
                'identifier': dict(authorization.identifier_obj),
            })

        if len(subproblems) > 1:
            order.error = json.dumps({
                'type': 'urn:ietf:params:acme:error:compound',
                'detail': 'Multiple authorization failures',
                'subproblems': subproblems,
            })
        else:
            order.error = json.dumps(fallback)

    def expire_order_if_needed(self, order: AcmeOrder) -> bool:
        """Lazily invalidate an expired non-final order."""
        if order.status not in ('pending', 'ready') or order.expires >= utc_now():
            return False

        order.status = 'invalid'
        problem = self._problem_data('malformed', 'Order has expired')
        order.error = json.dumps(problem)
        for authorization in order.authorizations:
            if authorization.status == 'pending':
                self._expire_authorization(authorization, update_order=False)
        self._set_order_authorization_error(order, problem)
        self._commit_state_change('expire ACME order')
        return True

    def expire_authorization_if_needed(self, authorization: AcmeAuthorization) -> bool:
        """Lazily invalidate an expired pending authorization."""
        if authorization.status != 'pending' or authorization.expires >= utc_now():
            return False

        self._expire_authorization(authorization, update_order=True)
        self._commit_state_change('expire ACME authorization')
        return True

    def _expire_authorization(
        self,
        authorization: AcmeAuthorization,
        *,
        update_order: bool,
    ) -> None:
        problem = self._problem_data('malformed', 'Authorization has expired')
        authorization.status = 'invalid'
        for challenge in authorization.challenges:
            if challenge.status in ('pending', 'processing'):
                challenge.status = 'invalid'
                challenge.error = json.dumps(problem)

        order = authorization.order
        if update_order and order:
            if order.status in ('pending', 'ready'):
                order.status = 'invalid'
            if order.status == 'invalid':
                self._set_order_authorization_error(order, problem)

    @staticmethod
    def _commit_state_change(context: str) -> None:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f'Failed to {context}: {e}')
            raise

    def begin_order_processing(self, order: AcmeOrder) -> None:
        """Persist the ready-to-processing transition before issuance."""
        order.status = 'processing'
        self._commit_state_change('mark ACME order processing')

    def restore_processing_order(self, order_id: str) -> None:
        """Restore retryable finalize failures that did not invalidate the order."""
        order = AcmeOrder.query.filter_by(order_id=order_id).first()
        if order is None:
            return
        db.session.refresh(order)
        if order.status == 'processing':
            order.status = 'ready'
            self._commit_state_change('restore ACME order ready status')

    def invalidate_processing_order(
        self,
        order_id: str,
        error_type: str,
        detail: str,
    ) -> None:
        """Finish a processing order as invalid with an ACME problem."""
        order = AcmeOrder.query.filter_by(order_id=order_id).first()
        if order is None:
            return
        db.session.refresh(order)
        if order.status == 'processing':
            order.status = 'invalid'
            order.error = self._problem(error_type, detail)
            self._commit_state_change('mark ACME order invalid')

    def get_order(self, order_id: str) -> Optional[AcmeOrder]:
        """Get order by ID.

        IssuanceMixin still validates its input as ``ready``. During the
        synchronous finalize call the persisted RFC state is ``processing``;
        expose ``ready`` only to that internal compatibility check.
        """
        order = AcmeOrder.query.filter_by(order_id=order_id).first()
        if (
            order is not None
            and order.status == 'processing'
            and getattr(self, '_finalizing_order_id', None) == order_id
        ):
            set_committed_value(order, 'status', 'ready')
        return order
    
    def get_challenge(self, challenge_id: str) -> Optional[AcmeChallenge]:
        """Get challenge by ID
        
        Args:
            challenge_id: Challenge identifier
            
        Returns:
            AcmeChallenge or None
        """
        return AcmeChallenge.query.filter_by(challenge_id=challenge_id).first()
