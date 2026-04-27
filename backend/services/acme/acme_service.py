"""
ACME Protocol Service Layer
Implements RFC 8555 - Automatic Certificate Management Environment (ACME)
"""
import secrets
import json
import socket
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
import logging
from cryptography.hazmat.backends import default_backend
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
import base64
import hashlib

from models import db
from models.acme_models import (
    AcmeAccount, AcmeOrder, AcmeAuthorization, 
    AcmeChallenge, AcmeNonce
)
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class AcmeService:
    """ACME Protocol Service implementing RFC 8555"""
    
    # ACME Directory URLs
    DIRECTORY_URLS = {
        "newNonce": "/acme/new-nonce",
        "newAccount": "/acme/new-account",
        "newOrder": "/acme/new-order",
        "newAuthz": "/acme/new-authz",
        "revokeCert": "/acme/revoke-cert",
        "keyChange": "/acme/key-change",
    }
    
    # Challenge types supported
    SUPPORTED_CHALLENGES = ["http-01", "dns-01", "tls-alpn-01"]

    
    def __init__(self, base_url: str = "https://localhost:8443"):
        """Initialize ACME service
        
        Args:
            base_url: Base URL for ACME endpoints (e.g., https://ucm.local:8443)
        """
        self.base_url = base_url.rstrip('/')
    
    # ==================== Nonce Management ====================
    
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
    
    # ==================== Account Management ====================
    
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
    
    # ==================== Order Management ====================
    
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
    
    # ==================== Challenge Management ====================
    
    def get_challenge(self, challenge_id: str) -> Optional[AcmeChallenge]:
        """Get challenge by ID
        
        Args:
            challenge_id: Challenge identifier
            
        Returns:
            AcmeChallenge or None
        """
        return AcmeChallenge.query.filter_by(challenge_id=challenge_id).first()
    
    def validate_http01_challenge(
        self,
        challenge: AcmeChallenge,
        account: AcmeAccount
    ) -> bool:
        """Validate HTTP-01 challenge
        
        Args:
            challenge: AcmeChallenge object
            account: AcmeAccount object for key authorization
            
        Returns:
            True if validation successful
        """
        import requests
        
        # Get identifier from authorization
        auth = challenge.authorization
        identifier = json.loads(auth.identifier)
        domain = identifier.get("value", "")
        
        # Compute key authorization
        key_authz = self._compute_key_authorization(
            challenge.token,
            account.jwk_thumbprint
        )
        
        # Fetch from well-known URL
        url = f"http://{domain}/.well-known/acme-challenge/{challenge.token}"
        
        try:
            # SSRF protection: reject domains resolving to private/loopback IPs
            # unless explicitly allowed (local ACME is meant for internal infra).
            if not self._acme_allow_private_ips():
                from utils.ssrf_protection import validate_host_not_private
                try:
                    validate_host_not_private(domain)
                except ValueError as ssrf_err:
                    challenge.status = "invalid"
                    challenge.error = json.dumps({
                        "type": "urn:ietf:params:acme:error:rejectedIdentifier",
                        "detail": "Domain resolves to a non-public address"
                    })
                    db.session.commit()
                    logger.warning(f"HTTP-01 SSRF blocked for {domain}: {ssrf_err}")
                    return False
            
            response = requests.get(url, timeout=10, allow_redirects=False)
            response.raise_for_status()
            
            if response.text.strip() == key_authz:
                challenge.status = "valid"
                challenge.validated = utc_now()
                
                # Update authorization status
                self._update_authorization_status(auth)
                
                db.session.commit()
                return True
            else:
                challenge.status = "invalid"
                challenge.error = json.dumps({
                    "type": "urn:ietf:params:acme:error:incorrectResponse",
                    "detail": "Key authorization mismatch"
                })
                db.session.commit()
                return False
                
        except Exception as e:
            challenge.status = "invalid"
            challenge.error = json.dumps({
                "type": "urn:ietf:params:acme:error:connection",
                "detail": str(e)
            })
            try:
                db.session.commit()
            except Exception as commit_err:
                db.session.rollback()
                logger.error(f"DB commit failed: {commit_err}")
                raise
            return False
    
    def validate_dns01_challenge(
        self,
        challenge: AcmeChallenge,
        account: AcmeAccount
    ) -> bool:
        """Validate DNS-01 challenge
        
        Args:
            challenge: AcmeChallenge object
            account: AcmeAccount object
            
        Returns:
            True if validation successful
        """
        import dns.resolver
        
        # Get identifier from authorization
        auth = challenge.authorization
        identifier = json.loads(auth.identifier)
        domain = identifier.get("value", "")
        
        # Compute key authorization
        key_authz = self._compute_key_authorization(
            challenge.token,
            account.jwk_thumbprint
        )
        
        # Compute DNS TXT record value
        txt_value = base64.urlsafe_b64encode(
            hashlib.sha256(key_authz.encode()).digest()
        ).decode().rstrip('=')
        
        # Query DNS
        txt_record = f"_acme-challenge.{domain}"
        
        try:
            # Optional override: allow operators to point DNS-01 validation at
            # a specific authoritative resolver (e.g. an internal BIND9 fed by
            # cert-manager rfc2136) regardless of the system /etc/resolv.conf.
            # Comma-separated list in SystemConfig key ``acme.dns01_nameservers``.
            custom_ns = self._acme_dns01_nameservers()
            if custom_ns:
                resolver = dns.resolver.Resolver(configure=False)
                resolver.nameservers = custom_ns
                resolver.timeout = 5
                resolver.lifetime = 10
                answers = resolver.resolve(txt_record, 'TXT')
            else:
                answers = dns.resolver.resolve(txt_record, 'TXT')
            
            for rdata in answers:
                # RFC 8555 §8.4: TXT record content must EQUAL the key authorization hash.
                # dnspython TXT records expose .strings as a list of bytes per quoted-string segment.
                matched = False
                try:
                    for s in rdata.strings:
                        if s.decode('utf-8', errors='replace') == txt_value:
                            matched = True
                            break
                except AttributeError:
                    # Fallback (non-TXT or unusual rdata): exact string compare
                    matched = (str(rdata).strip('"') == txt_value)
                
                if matched:
                    challenge.status = "valid"
                    challenge.validated = utc_now()
                    
                    # Update authorization status
                    self._update_authorization_status(auth)
                    
                    db.session.commit()
                    return True
            
            # No matching TXT record found
            challenge.status = "invalid"
            challenge.error = json.dumps({
                "type": "urn:ietf:params:acme:error:incorrectResponse",
                "detail": f"No matching TXT record found at {txt_record}"
            })
            db.session.commit()
            return False
            
        except Exception as e:
            challenge.status = "invalid"
            challenge.error = json.dumps({
                "type": "urn:ietf:params:acme:error:dns",
                "detail": str(e)
            })
            try:
                db.session.commit()
            except Exception as commit_err:
                db.session.rollback()
                logger.error(f"DB commit failed: {commit_err}")
                raise
            return False
    
    def validate_tls_alpn01_challenge(
        self,
        challenge: AcmeChallenge,
        account: AcmeAccount
    ) -> bool:
        """Validate TLS-ALPN-01 challenge (RFC 8737)
        
        Connects to the domain on port 443 with the acme-tls/1 ALPN extension,
        verifies the self-signed certificate contains the acmeIdentifier extension
        with the correct key authorization hash.
        
        Args:
            challenge: AcmeChallenge object
            account: AcmeAccount object
            
        Returns:
            True if validation successful
        """
        import ssl
        import socket
        
        auth = challenge.authorization
        identifier = json.loads(auth.identifier)
        domain = identifier.get("value", "")
        
        # Compute key authorization hash
        key_authz = self._compute_key_authorization(
            challenge.token,
            account.jwk_thumbprint
        )
        expected_hash = hashlib.sha256(key_authz.encode()).digest()
        
        try:
            # SSRF protection: reject domains resolving to private/loopback IPs
            # unless explicitly allowed (local ACME is meant for internal infra).
            if not self._acme_allow_private_ips():
                from utils.ssrf_protection import validate_host_not_private
                try:
                    validate_host_not_private(domain)
                except ValueError as ssrf_err:
                    challenge.status = "invalid"
                    challenge.error = json.dumps({
                        "type": "urn:ietf:params:acme:error:rejectedIdentifier",
                        "detail": "Domain resolves to a non-public address"
                    })
                    db.session.commit()
                    logger.warning(f"TLS-ALPN-01 SSRF blocked for {domain}: {ssrf_err}")
                    return False
            
            # Create SSL context with acme-tls/1 ALPN
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.set_alpn_protocols(['acme-tls/1'])
            
            # Connect to domain
            with socket.create_connection((domain, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                    # Verify ALPN was negotiated
                    negotiated = ssock.selected_alpn_protocol()
                    if negotiated != 'acme-tls/1':
                        raise ValueError(f"ALPN negotiation failed: {negotiated}")
                    
                    # Get peer certificate
                    cert_der = ssock.getpeercert(binary_form=True)
                    if not cert_der:
                        raise ValueError("No certificate presented")
                    
                    # Parse certificate and check acmeIdentifier extension
                    from cryptography import x509 as x509_mod
                    cert = x509_mod.load_der_x509_certificate(cert_der, default_backend())
                    
                    # acmeIdentifier OID: 1.3.6.1.5.5.7.1.31
                    acme_id_oid = x509_mod.ObjectIdentifier("1.3.6.1.5.5.7.1.31")
                    
                    try:
                        ext = cert.extensions.get_extension_for_oid(acme_id_oid)
                        # UnrecognizedExtension.value returns raw DER bytes directly
                        ext_value = ext.value.value
                        # DER-encoded: OCTET STRING tag (0x04) + length (0x20=32)
                        if len(ext_value) > 2 and ext_value[0] == 0x04:
                            # Skip the outer OCTET STRING wrapper
                            actual_hash = ext_value[2:]
                        else:
                            actual_hash = ext_value
                        
                        if actual_hash == expected_hash:
                            challenge.status = "valid"
                            challenge.validated = utc_now()
                            self._update_authorization_status(auth)
                            db.session.commit()
                            return True
                        else:
                            raise ValueError("acmeIdentifier hash mismatch")
                    except x509_mod.ExtensionNotFound:
                        raise ValueError("Certificate missing acmeIdentifier extension")
        
        except Exception as e:
            challenge.status = "invalid"
            challenge.error = json.dumps({
                "type": "urn:ietf:params:acme:error:tls",
                "detail": str(e)
            })
            try:
                db.session.commit()
            except Exception as commit_err:
                db.session.rollback()
                logger.error(f"DB commit failed: {commit_err}")
                raise
            return False
    
    def _update_authorization_status(self, auth: AcmeAuthorization):
        """Update authorization status based on challenges
        
        Args:
            auth: AcmeAuthorization object
        """
        # Check if any challenge is valid
        valid_challenges = [c for c in auth.challenges if c.status == "valid"]
        
        if valid_challenges:
            auth.status = "valid"
            
            # Update order status if all authorizations are valid
            order = auth.order
            all_valid = all(a.status == "valid" for a in order.authorizations)
            
            if all_valid:
                order.status = "ready"
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"DB commit failed: {e}")
                    raise
    
    # ==================== Certificate Finalization ====================
    
    def finalize_order(
        self,
        order_id: str,
        csr_pem: str,
        ca_refid: str = None
    ) -> Tuple[bool, Optional[str]]:
        """Finalize order and issue certificate
        
        Args:
            order_id: Order identifier
            csr_pem: PEM-encoded Certificate Signing Request
            ca_refid: CA to sign with (optional, resolved from domain config → global default → first available)
            
        Returns:
            Tuple of (success, error_message)
        """
        order = self.get_order(order_id)
        
        if not order:
            return False, "Order not found"
        
        if order.status != "ready":
            return False, f"Order status is {order.status}, must be 'ready'"
        
        # Parse CSR
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            
            csr = x509.load_pem_x509_csr(csr_pem.encode(), default_backend())
        except Exception as e:
            return False, f"Invalid CSR: {str(e)}"
        
        # Validate CSR matches order identifiers
        csr_domains = self._extract_domains_from_csr(csr)
        order_identifiers = json.loads(order.identifiers)
        order_domains = [id['value'] for id in order_identifiers if id.get('type') == 'dns']
        
        if set(csr_domains) != set(order_domains):
            return False, f"CSR domains {csr_domains} don't match order domains {order_domains}"
        
        # CAA record check (RFC 6844 + RFC 8555 §8.1)
        try:
            from utils.caa_checker import check_caa_for_domains
            from models import SystemConfig
            
            caa_identifiers = []
            try:
                caa_cfg = SystemConfig.query.filter_by(key='acme_caa_identifiers').first()
                if caa_cfg and caa_cfg.value:
                    caa_identifiers = [v.strip() for v in caa_cfg.value.split(',') if v.strip()]
            except Exception:
                pass
            
            if not caa_identifiers:
                # Use server hostname as default CAA identity
                from flask import request as flask_request
                try:
                    caa_identifiers = [flask_request.host.split(':')[0]]
                except Exception:
                    pass
            
            caa_allowed, caa_reason = check_caa_for_domains(order_domains, caa_identifiers)
            if not caa_allowed:
                logger.warning(f"CAA check failed for order {order_id}: {caa_reason}")
                return False, f"CAA check failed: {caa_reason}"
            logger.debug(f"CAA check passed for {order_domains}: {caa_reason}")
        except ImportError:
            logger.debug("dns.resolver not available, skipping CAA check")
        except Exception as e:
            logger.warning(f"CAA check error (non-blocking): {e}")
        
        # Resolve CA: domain-specific → global default → first available
        if not ca_refid:
            ca_refid = self._resolve_ca_for_domains(order_domains)
        
        # Sign certificate with UCM CA
        success, cert_id, error = self._sign_certificate_with_ca(
            order=order,
            csr_pem=csr_pem,
            ca_refid=ca_refid
        )
        
        if not success:
            order.status = "invalid"
            order.error = json.dumps({
                "type": "urn:ietf:params:acme:error:serverInternal",
                "detail": error
            })
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"DB commit failed: {e}")
                raise
            return False, error
        
        # Update order status
        order.status = "valid"
        order.csr = csr_pem
        order.certificate_id = cert_id
        order.certificate_url = f"{self.base_url}/acme/cert/{order.order_id}"
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"DB commit failed: {e}")
            raise
        
        # Auto-supersede: revoke previous certs for same domains if enabled
        self._auto_supersede(order, cert_id)
        
        return True, None
    
    def _auto_supersede(self, new_order, new_cert_id: int):
        """Revoke previous certificates for the same domains if revoke_on_renewal is enabled."""
        try:
            from models import SystemConfig, Certificate
            from models.acme_models import AcmeOrder
            
            setting = SystemConfig.query.filter_by(key='acme.revoke_on_renewal').first()
            if not setting or setting.value != 'true':
                return
            
            # Find previous orders with same identifiers and account
            previous_orders = AcmeOrder.query.filter(
                AcmeOrder.account_id == new_order.account_id,
                AcmeOrder.identifiers == new_order.identifiers,
                AcmeOrder.certificate_id.isnot(None),
                AcmeOrder.certificate_id != new_cert_id,
                AcmeOrder.status == 'valid'
            ).all()
            
            if not previous_orders:
                return
            
            from services.cert_service import CertificateService
            for prev_order in previous_orders:
                cert = Certificate.query.get(prev_order.certificate_id)
                if cert and not cert.revoked:
                    try:
                        CertificateService.revoke_certificate(
                            cert_id=cert.id,
                            reason='superseded',
                            username='system'
                        )
                        logger.info(f"Auto-superseded certificate {cert.id} (replaced by {new_cert_id})")
                    except Exception as e:
                        logger.warning(f"Failed to supersede certificate {cert.id}: {e}")
        except Exception as e:
            logger.warning(f"Auto-supersede check failed: {e}")
    
    def _extract_domains_from_csr(self, csr) -> List[str]:
        """Extract domain names from CSR
        
        Args:
            csr: x509.CertificateSigningRequest object
            
        Returns:
            List of domain names
        """
        from cryptography import x509
        
        domains = []
        
        # Get CN from subject
        try:
            cn = csr.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
            domains.append(cn)
        except Exception:
            pass
        
        # Get SANs
        try:
            san_ext = csr.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            for name in san_ext.value:
                if isinstance(name, x509.DNSName):
                    if name.value not in domains:
                        domains.append(name.value)
        except Exception:
            pass
        
        return domains
    
    def _resolve_ca_for_domains(self, domains: list) -> Optional[str]:
        """Resolve which CA should sign for the given domains.
        
        Resolution order:
        1. Local ACME domain mapping (acme_local_domains table)
        2. DNS domain-specific CA (acme_domains.issuing_ca_id)
        3. Global default from acme.issuing_ca_id config
        4. None (will fall back to first available CA in _sign_certificate_with_ca)
        """
        from api.v2.acme_local_domains import find_local_domain_ca
        from api.v2.acme_domains import find_provider_for_domain
        from models import SystemConfig, CA
        
        # Check local ACME domain mapping first
        for domain in domains:
            ca_id = find_local_domain_ca(domain)
            if ca_id:
                ca = CA.query.get(ca_id)
                if ca and ca.prv:
                    return ca.refid
        
        # Check DNS domain-specific CA
        for domain in domains:
            result = find_provider_for_domain(domain)
            if result and result.get('issuing_ca_id'):
                ca = CA.query.get(result['issuing_ca_id'])
                if ca and ca.prv:
                    return ca.refid
        
        # Fall back to global default
        ca_id_cfg = SystemConfig.query.filter_by(key='acme.issuing_ca_id').first()
        if ca_id_cfg and ca_id_cfg.value:
            ca = CA.query.filter_by(refid=ca_id_cfg.value).first()
            if not ca:
                try:
                    ca = CA.query.get(int(ca_id_cfg.value))
                except (ValueError, TypeError):
                    pass
            if ca and ca.prv:
                return ca.refid
        
        return None
    
    def _sign_certificate_with_ca(
        self,
        order: AcmeOrder,
        csr_pem: str,
        ca_refid: str = None
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Sign CSR with UCM CA
        
        Args:
            order: AcmeOrder object
            csr_pem: PEM-encoded CSR
            ca_refid: CA refid (optional)
            
        Returns:
            Tuple of (success, certificate_id, error_message)
        """
        from models import CA, Certificate
        import secrets
        import base64
        
        # Get CA (use first available if not specified)
        if ca_refid:
            ca = CA.query.filter_by(refid=ca_refid).first()
        else:
            # Find first CA with private key
            ca = CA.query.filter(CA.prv.isnot(None)).first()
        
        if not ca:
            return False, None, "No CA available for signing"
        
        if not ca.prv:
            return False, None, f"CA {ca.refid} has no private key"
        
        # Extract CN from CSR for better description
        descr = f"ACME Certificate - Order {order.order_id}"
        try:
            from cryptography.hazmat.backends import default_backend
            from cryptography import x509
            csr_bytes = csr_pem.encode() if isinstance(csr_pem, str) else csr_pem
            csr = x509.load_pem_x509_csr(csr_bytes, default_backend())
            
            # Try to get CN from subject
            cn = None
            for attr in csr.subject:
                if attr.oid == x509.oid.NameOID.COMMON_NAME:
                    cn = attr.value
                    break
            
            # If no CN, try first DNS name from SAN
            if not cn:
                try:
                    san_ext = csr.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                    for name in san_ext.value:
                        if isinstance(name, x509.DNSName):
                            cn = name.value
                            break
                except Exception:
                    pass
            
            # Use CN as description if found
            if cn:
                descr = cn
        except Exception as e:
            # Keep default description if extraction fails
            pass
        
        # Create certificate record with CSR
        cert = Certificate(
            refid=secrets.token_urlsafe(16),
            descr=descr,
            caref=ca.refid,
            csr=base64.b64encode(csr_pem.encode()).decode('utf-8'),
            cert_type='server_cert',
            source='acme',
            created_by='acme'
        )
        db.session.add(cert)
        db.session.flush()  # Get cert.id
        
        # Sign CSR using existing CertificateService
        try:
            from services.cert_service import CertificateService
            
            signed_cert = CertificateService.sign_csr(
                cert_id=cert.id,
                caref=ca.refid,
                cert_type='server_cert',
                validity_days=90,  # ACME certificates typically 90 days
                digest='sha256',
                username='acme'
            )
            
            return True, signed_cert.id, None
            
        except Exception as e:
            db.session.rollback()
            return False, None, f"Certificate signing failed: {str(e)}"
    
    # ==================== Utility Methods ====================
    
    def _compute_jwk_thumbprint(self, jwk: Dict[str, Any]) -> str:
        """Compute JWK thumbprint per RFC 7638
        
        Args:
            jwk: JSON Web Key
            
        Returns:
            Base64url-encoded SHA-256 thumbprint
        """
        # Extract required fields in lexicographic order
        if jwk.get("kty") == "RSA":
            thumbprint_input = {
                "e": jwk["e"],
                "kty": jwk["kty"],
                "n": jwk["n"]
            }
        elif jwk.get("kty") == "EC":
            thumbprint_input = {
                "crv": jwk["crv"],
                "kty": jwk["kty"],
                "x": jwk["x"],
                "y": jwk["y"]
            }
        else:
            raise ValueError(f"Unsupported key type: {jwk.get('kty')}")
        
        # Serialize to JSON (no whitespace)
        json_str = json.dumps(thumbprint_input, sort_keys=True, separators=(',', ':'))
        
        # Compute SHA-256
        digest = hashlib.sha256(json_str.encode()).digest()
        
        # Base64url encode
        return base64.urlsafe_b64encode(digest).decode().rstrip('=')
    
    def _compute_key_authorization(self, token: str, jwk_thumbprint: str) -> str:
        """Compute key authorization for challenges
        
        Args:
            token: Challenge token
            jwk_thumbprint: JWK thumbprint
            
        Returns:
            Key authorization string (token.thumbprint)
        """
        return f"{token}.{jwk_thumbprint}"

    def _acme_allow_private_ips(self) -> bool:
        """Whether HTTP-01 / TLS-ALPN-01 may target private/internal IPs.

        Local ACME is typically used to issue certificates for INTERNAL
        infrastructure (.lan, .local, .corp, etc.) which by definition
        resolves to RFC 1918 / link-local addresses. Blocking those would
        make the local ACME server unusable for its main use case.

        Defaults to True. Operators who only want to issue for public
        domains can flip ``acme.allow_private_ips`` to ``false``.
        """
        try:
            from models import SystemConfig
            setting = SystemConfig.query.filter_by(key='acme.allow_private_ips').first()
            if setting is None:
                return True
            return str(setting.value).strip().lower() in ('1', 'true', 'yes', 'on')
        except Exception:
            return True
    
    def _acme_dns01_nameservers(self) -> list:
        """Optional list of DNS servers to use for DNS-01 challenge validation.

        When set (SystemConfig key ``acme.dns01_nameservers``, comma-separated
        IPs), DNS-01 validation queries those resolvers instead of the system
        resolver. Useful when the authoritative DNS for the validation zone
        (e.g. a local BIND9 driven by cert-manager rfc2136) is not reachable
        via the OS /etc/resolv.conf chain.

        Returns an empty list when unset.
        """
        try:
            from models import SystemConfig
            setting = SystemConfig.query.filter_by(key='acme.dns01_nameservers').first()
            if not setting or not setting.value:
                return []
            return [ip.strip() for ip in str(setting.value).split(',') if ip.strip()]
        except Exception:
            return []

    def validate_eab(self, eab_data: Dict[str, Any], account_jwk: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate External Account Binding (RFC 8555 §7.3.4)
        
        The EAB is a JWS signed with a pre-shared HMAC key, binding
        the ACME account key to an external account.
        
        Args:
            eab_data: The externalAccountBinding JWS object
            account_jwk: The account JWK being registered
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            import hmac as hmac_lib
            
            # EAB must have protected, payload, signature
            if not all(k in eab_data for k in ('protected', 'payload', 'signature')):
                return False, "Missing required JWS fields"
            
            # Decode protected header
            protected_b64 = eab_data['protected']
            protected_json = base64.urlsafe_b64decode(protected_b64 + '==')
            protected = json.loads(protected_json)
            
            # Verify algorithm is HS256 (HMAC-SHA256) per RFC 8555
            alg = protected.get('alg', '')
            if alg not in ('HS256', 'HS384', 'HS512'):
                return False, f"Invalid EAB algorithm: {alg}. Must be HMAC-based"
            
            # Extract key ID (the external account identifier)
            kid = protected.get('kid', '')
            if not kid:
                return False, "EAB missing kid (external account ID)"
            
            # Look up the HMAC key for this external account.
            # Preferred path: dedicated AcmeEabCredential table (v2.139+).
            # Fallback: legacy SystemConfig 'acme_eab_keys' JSON blob.
            from models import SystemConfig, AcmeEabCredential
            from utils.datetime_utils import utc_now as _utc_now

            credential = AcmeEabCredential.query.filter_by(kid=kid).first()
            hmac_key_b64 = None
            legacy = False

            if credential is not None:
                if not credential.is_usable:
                    return False, f"EAB credential not usable (status={credential.status})"
                hmac_key_b64 = credential.hmac_key_b64
            else:
                eab_config = SystemConfig.query.filter_by(key='acme_eab_keys').first()
                eab_keys_json = eab_config.value if eab_config else '{}'
                try:
                    eab_keys = json.loads(eab_keys_json)
                except Exception:
                    eab_keys = {}
                hmac_key_b64 = eab_keys.get(kid)
                legacy = True

            if not hmac_key_b64:
                return False, "Unknown external account"

            # Decode the HMAC key
            hmac_key = base64.urlsafe_b64decode(hmac_key_b64 + '==')
            
            # Verify the payload is the account JWK
            payload_b64 = eab_data['payload']
            payload_bytes = base64.urlsafe_b64decode(payload_b64 + '==')
            try:
                payload_jwk = json.loads(payload_bytes)
                # The payload should be the account public key
                if payload_jwk.get('kty') != account_jwk.get('kty'):
                    return False, "EAB payload does not match account key"
            except Exception:
                return False, "EAB payload is not valid JSON"
            
            # Verify HMAC signature
            signing_input = f"{protected_b64}.{payload_b64}".encode('ascii')
            
            if alg == 'HS256':
                mac = hmac_lib.new(hmac_key, signing_input, hashlib.sha256).digest()
            elif alg == 'HS384':
                mac = hmac_lib.new(hmac_key, signing_input, hashlib.sha384).digest()
            else:  # HS512
                mac = hmac_lib.new(hmac_key, signing_input, hashlib.sha512).digest()
            
            expected_sig = base64.urlsafe_b64encode(mac).rstrip(b'=').decode('ascii')
            actual_sig = eab_data['signature']
            
            if not hmac_lib.compare_digest(expected_sig, actual_sig):
                return False, "EAB signature verification failed"

            # Mark credential as used (single-use semantics, RFC 8555 §7.3.4).
            # The actual binding to the freshly-created AcmeAccount is done
            # by the caller (new_account handler) via mark_eab_used().
            try:
                if legacy:
                    eab_config = SystemConfig.query.filter_by(key='acme_eab_keys').first()
                    eab_keys_json = eab_config.value if eab_config else '{}'
                    try:
                        eab_keys = json.loads(eab_keys_json)
                    except Exception:
                        eab_keys = {}
                    eab_keys.pop(kid, None)
                    if eab_config:
                        eab_config.value = json.dumps(eab_keys)
                    else:
                        db.session.add(SystemConfig(key='acme_eab_keys', value=json.dumps(eab_keys)))
                else:
                    credential.status = 'used'
                    credential.used_at = _utc_now()
                db.session.commit()
            except Exception as commit_err:
                db.session.rollback()
                logger.error(f"Failed to persist EAB key consumption: {commit_err}")
            
            return True, None
            
        except Exception as e:
            logger.error(f"EAB validation error: {e}")
            return False, str(e)

    def mark_eab_used(self, kid: str, account_id: str) -> None:
        """Bind an EAB credential to the ACME account that consumed it.

        Called from the new-account handler once the account row is
        committed. Best-effort: does nothing for legacy SystemConfig
        credentials or unknown kids.
        """
        try:
            from models import AcmeEabCredential
            cred = AcmeEabCredential.query.filter_by(kid=kid).first()
            if cred is not None and cred.used_by_account_id is None:
                cred.used_by_account_id = account_id
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.warning(f"Failed to bind EAB credential {kid} to account {account_id}: {e}")
    
    def get_directory(self) -> Dict[str, str]:
        """Get ACME directory (RFC 8555 Section 7.1.1)
        
        Returns:
            Dictionary of ACME endpoints
        """
        return {
            key: f"{self.base_url}{path}"
            for key, path in self.DIRECTORY_URLS.items()
        }
