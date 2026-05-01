"""Challenge validation mixin for ACME service"""
import json
import hashlib
import base64
import logging

from models import db
from models.acme_models import AcmeChallenge, AcmeAuthorization
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class ChallengeMixin:
    def validate_http01_challenge(
        self,
        challenge: AcmeChallenge,
        account
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
        account
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
        account
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
                    from cryptography.hazmat.backends import default_backend
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
