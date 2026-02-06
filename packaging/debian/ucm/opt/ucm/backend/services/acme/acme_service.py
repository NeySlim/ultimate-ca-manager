"""
ACME Protocol Service Layer
Implements RFC 8555 - Automatic Certificate Management Environment (ACME)
"""
import secrets
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
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


class AcmeService:
    """ACME Protocol Service implementing RFC 8555"""
    
    # ACME Directory URLs
    DIRECTORY_URLS = {
        "newNonce": "/acme/new-nonce",
        "newAccount": "/acme/new-account",
        "newOrder": "/acme/new-order",
        "revokeCert": "/acme/revoke-cert",
        "keyChange": "/acme/key-change",
    }
    
    # Challenge types supported
    SUPPORTED_CHALLENGES = ["http-01", "dns-01"]
    
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
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        db.session.add(nonce)
        db.session.commit()
        
        return nonce_token
    
    def validate_nonce(self, nonce_token: str) -> bool:
        """Validate and consume a nonce (one-time use)
        
        Args:
            nonce_token: The nonce to validate
            
        Returns:
            True if valid, False otherwise
        """
        nonce = AcmeNonce.query.filter_by(token=nonce_token).first()
        
        if not nonce:
            return False
        
        if nonce.used:
            # Already used - replay attack attempt
            return False
        
        if datetime.utcnow() > nonce.expires_at:
            # Expired nonce
            db.session.delete(nonce)
            db.session.commit()
            return False
        
        # Mark as used
        nonce.used = True
        nonce.used_at = datetime.utcnow()
        db.session.commit()
        
        return True
    
    def cleanup_expired_nonces(self) -> int:
        """Remove expired nonces from database
        
        Returns:
            Number of nonces deleted
        """
        expired = AcmeNonce.query.filter(
            AcmeNonce.expires_at < datetime.utcnow()
        ).all()
        
        count = len(expired)
        for nonce in expired:
            db.session.delete(nonce)
        
        db.session.commit()
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
            created_at=datetime.utcnow()
        )
        
        db.session.add(account)
        db.session.commit()
        
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
        db.session.commit()
        
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
            expires=datetime.utcnow() + timedelta(days=7)
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
        
        db.session.commit()
        
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
                # Find valid authorization for same account and identifier
                # We reuse the logic by creating a new valid authorization
                # to avoid schema changes (many-to-many complexity)
                identifier_json = json.dumps(identifier)
                
                valid_auth = AcmeAuthorization.query.join(AcmeOrder).filter(
                    AcmeOrder.account_id == account_id,
                    AcmeAuthorization.identifier == identifier_json,
                    AcmeAuthorization.status == 'valid',
                    AcmeAuthorization.expires > datetime.utcnow()
                ).order_by(AcmeAuthorization.expires.desc()).first()
                
                if valid_auth:
                    # Reuse found! Create a new pre-validated authorization
                    auth = AcmeAuthorization(
                        order_id=order_id,
                        status="valid",
                        identifier=identifier_json,
                        expires=valid_auth.expires  # Carry over expiration or extend? Let's carry over for safety
                    )
                    
                    db.session.add(auth)
                    db.session.flush()
                    
                    # Create pre-validated challenges (clients may check them)
                    self._create_challenges(auth, status="valid", validated=datetime.utcnow())
                    
                    return auth
            except Exception as e:
                # Log but continue with new auth
                print(f"Error checking auth reuse: {e}")

        # No reuse - create new pending authorization
        auth = AcmeAuthorization(
            order_id=order_id,
            status="pending",
            identifier=json.dumps(identifier),
            expires=datetime.utcnow() + timedelta(days=7)
        )
        
        db.session.add(auth)
        db.session.flush()  # Get auth.authorization_id
        
        # Create pending challenges
        self._create_challenges(auth, status="pending")
        
        db.session.commit()
        
        return auth

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
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            if response.text.strip() == key_authz:
                challenge.status = "valid"
                challenge.validated = datetime.utcnow()
                
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
            db.session.commit()
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
            answers = dns.resolver.resolve(txt_record, 'TXT')
            
            for rdata in answers:
                if txt_value in str(rdata):
                    challenge.status = "valid"
                    challenge.validated = datetime.utcnow()
                    
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
            db.session.commit()
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
                db.session.commit()
    
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
            ca_refid: CA to sign with (optional, uses default if not provided)
            
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
            db.session.commit()
            return False, error
        
        # Update order status
        order.status = "valid"
        order.csr = csr_pem
        order.certificate_id = cert_id
        order.certificate_url = f"{self.base_url}/acme/cert/{order.order_id}"
        db.session.commit()
        
        return True, None
    
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
        except:
            pass
        
        # Get SANs
        try:
            san_ext = csr.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            for name in san_ext.value:
                if isinstance(name, x509.DNSName):
                    if name.value not in domains:
                        domains.append(name.value)
        except:
            pass
        
        return domains
    
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
                except:
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
    
    def get_directory(self) -> Dict[str, str]:
        """Get ACME directory (RFC 8555 Section 7.1.1)
        
        Returns:
            Dictionary of ACME endpoints
        """
        return {
            key: f"{self.base_url}{path}"
            for key, path in self.DIRECTORY_URLS.items()
        }
