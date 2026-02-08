"""
ACME Client Service
Client for requesting certificates from external ACME servers (Let's Encrypt)
UCM acts as an ACME CLIENT (not server) to obtain trusted certificates.
"""
import json
import base64
import hashlib
import time
import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
from urllib.parse import urljoin

import requests
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding
from cryptography.hazmat.backends import default_backend
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from models import db, SystemConfig, Certificate, DnsProvider, AcmeClientOrder
from services.acme.dns_providers import create_provider, get_provider_class

logger = logging.getLogger(__name__)


class AcmeClientService:
    """
    ACME Client for Let's Encrypt and compatible CAs.
    Handles the full certificate issuance workflow.
    """
    
    # Let's Encrypt directories
    LE_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
    LE_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"
    
    def __init__(self, environment: str = 'staging'):
        """
        Initialize ACME client.
        
        Args:
            environment: 'staging' or 'production'
        """
        self.environment = environment
        self.directory_url = self.LE_PRODUCTION if environment == 'production' else self.LE_STAGING
        self.directory = None
        self.account_key = None
        self.account_url = None
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'UCM-ACME-Client/2.1'
        
    # =========================================================================
    # Directory & Nonce
    # =========================================================================
    
    def _fetch_directory(self) -> Dict[str, Any]:
        """Fetch ACME directory from server"""
        if self.directory:
            return self.directory
        
        resp = self.session.get(self.directory_url, timeout=30)
        resp.raise_for_status()
        self.directory = resp.json()
        logger.info(f"Fetched ACME directory from {self.directory_url}")
        return self.directory
    
    def _get_nonce(self) -> str:
        """Get a fresh nonce from the ACME server"""
        directory = self._fetch_directory()
        resp = self.session.head(directory['newNonce'], timeout=10)
        return resp.headers['Replay-Nonce']
    
    # =========================================================================
    # Account Key Management
    # =========================================================================
    
    def _get_account_key(self) -> rsa.RSAPrivateKey:
        """Load or create account private key"""
        if self.account_key:
            return self.account_key
        
        config_key = f'acme.client.{self.environment}.account_key'
        config = SystemConfig.query.filter_by(key=config_key).first()
        
        if config:
            self.account_key = serialization.load_pem_private_key(
                config.value.encode(),
                password=None,
                backend=default_backend()
            )
        else:
            # Generate new RSA key
            self.account_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            pem = self.account_key.private_bytes(
                encoding=Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode()
            
            db.session.add(SystemConfig(
                key=config_key,
                value=pem,
                description=f"ACME client account key ({self.environment})"
            ))
            db.session.commit()
            logger.info(f"Generated new ACME account key for {self.environment}")
        
        return self.account_key
    
    def _get_account_url(self) -> Optional[str]:
        """Get stored account URL"""
        if self.account_url:
            return self.account_url
        
        config_key = f'acme.client.{self.environment}.account_url'
        config = SystemConfig.query.filter_by(key=config_key).first()
        if config:
            self.account_url = config.value
        return self.account_url
    
    def _save_account_url(self, url: str) -> None:
        """Save account URL to database"""
        self.account_url = url
        config_key = f'acme.client.{self.environment}.account_url'
        config = SystemConfig.query.filter_by(key=config_key).first()
        if config:
            config.value = url
        else:
            db.session.add(SystemConfig(
                key=config_key,
                value=url,
                description=f"ACME client account URL ({self.environment})"
            ))
        db.session.commit()
    
    # =========================================================================
    # JWS Signing (RFC 7515)
    # =========================================================================
    
    def _jwk_thumbprint(self, key: rsa.RSAPrivateKey) -> str:
        """Calculate JWK thumbprint (RFC 7638)"""
        public = key.public_key()
        numbers = public.public_numbers()
        
        # Convert to base64url
        def b64url(n, length):
            data = n.to_bytes(length, byteorder='big')
            return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
        
        # RSA key: e and n
        e = b64url(numbers.e, 3)  # e is typically 65537 = 3 bytes
        n = b64url(numbers.n, 256)  # 2048-bit = 256 bytes
        
        # JWK thumbprint is SHA-256 of canonical JSON
        jwk_json = json.dumps({"e": e, "kty": "RSA", "n": n}, separators=(',', ':'), sort_keys=True)
        thumbprint = hashlib.sha256(jwk_json.encode()).digest()
        return base64.urlsafe_b64encode(thumbprint).rstrip(b'=').decode()
    
    def _sign_jws(self, url: str, payload: Any, use_jwk: bool = False) -> Dict[str, str]:
        """
        Sign payload as JWS (JSON Web Signature).
        
        Args:
            url: Target URL (included in protected header)
            payload: Payload to sign (dict or "" for POST-as-GET)
            use_jwk: Include JWK in header (for new account)
        """
        key = self._get_account_key()
        nonce = self._get_nonce()
        
        # Build protected header
        protected = {
            "alg": "RS256",
            "nonce": nonce,
            "url": url,
        }
        
        if use_jwk:
            # New account registration - include JWK
            public = key.public_key()
            numbers = public.public_numbers()
            
            def b64url_int(n, length):
                data = n.to_bytes(length, byteorder='big')
                return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
            
            protected["jwk"] = {
                "kty": "RSA",
                "e": b64url_int(numbers.e, 3),
                "n": b64url_int(numbers.n, 256),
            }
        else:
            # Use account URL (kid)
            account_url = self._get_account_url()
            if not account_url:
                raise ValueError("No account registered. Register first.")
            protected["kid"] = account_url
        
        # Encode protected header
        protected_b64 = base64.urlsafe_b64encode(
            json.dumps(protected).encode()
        ).rstrip(b'=').decode()
        
        # Encode payload
        if payload == "":
            payload_b64 = ""
        else:
            payload_b64 = base64.urlsafe_b64encode(
                json.dumps(payload).encode()
            ).rstrip(b'=').decode()
        
        # Sign
        signing_input = f"{protected_b64}.{payload_b64}".encode()
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()
        
        return {
            "protected": protected_b64,
            "payload": payload_b64,
            "signature": signature_b64,
        }
    
    def _post(self, url: str, payload: Any, use_jwk: bool = False) -> requests.Response:
        """POST signed JWS to ACME endpoint"""
        jws = self._sign_jws(url, payload, use_jwk=use_jwk)
        resp = self.session.post(
            url,
            json=jws,
            headers={"Content-Type": "application/jose+json"},
            timeout=30
        )
        return resp
    
    # =========================================================================
    # Account Management
    # =========================================================================
    
    def register_account(self, email: str) -> Tuple[bool, str, Optional[str]]:
        """
        Register or retrieve existing ACME account.
        
        Args:
            email: Contact email address
        
        Returns:
            Tuple of (success, message, account_url)
        """
        try:
            directory = self._fetch_directory()
            new_account_url = directory['newAccount']
            
            payload = {
                "termsOfServiceAgreed": True,
                "contact": [f"mailto:{email}"],
            }
            
            resp = self._post(new_account_url, payload, use_jwk=True)
            
            if resp.status_code in [200, 201]:
                account_url = resp.headers.get('Location')
                self._save_account_url(account_url)
                
                status = "created" if resp.status_code == 201 else "existing"
                logger.info(f"ACME account {status}: {account_url}")
                return True, f"Account {status} successfully", account_url
            else:
                error = resp.json()
                return False, f"Account registration failed: {error.get('detail', 'Unknown error')}", None
                
        except Exception as e:
            logger.error(f"Account registration error: {e}")
            return False, str(e), None
    
    def ensure_account(self, email: str) -> Tuple[bool, str]:
        """Ensure account exists, register if needed"""
        if self._get_account_url():
            return True, "Account already registered"
        return self.register_account(email)[:2]
    
    # =========================================================================
    # Order Management
    # =========================================================================
    
    def create_order(
        self, 
        domains: List[str],
        email: str,
        challenge_type: str = 'dns-01',
        dns_provider_id: Optional[int] = None
    ) -> Tuple[bool, str, Optional[AcmeClientOrder]]:
        """
        Create a new certificate order.
        
        Args:
            domains: List of domain names
            email: Contact email
            challenge_type: 'http-01' or 'dns-01'
            dns_provider_id: DNS provider for DNS-01 challenges
        
        Returns:
            Tuple of (success, message, order)
        """
        try:
            # Ensure account exists
            success, msg = self.ensure_account(email)
            if not success:
                return False, msg, None
            
            # Create order at Let's Encrypt
            directory = self._fetch_directory()
            
            identifiers = [{"type": "dns", "value": d} for d in domains]
            payload = {"identifiers": identifiers}
            
            resp = self._post(directory['newOrder'], payload)
            
            if resp.status_code not in [200, 201]:
                error = resp.json()
                return False, f"Order creation failed: {error.get('detail', 'Unknown error')}", None
            
            order_data = resp.json()
            order_url = resp.headers.get('Location')
            
            # Create local order record
            order = AcmeClientOrder(
                domains=json.dumps(domains),
                challenge_type=challenge_type,
                environment=self.environment,
                status='pending',
                order_url=order_url,
                account_url=self.account_url,
                finalize_url=order_data.get('finalize'),
                dns_provider_id=dns_provider_id,
                expires_at=datetime.fromisoformat(order_data['expires'].rstrip('Z'))
            )
            
            # Fetch and store challenges
            challenges_data = {}
            for authz_url in order_data.get('authorizations', []):
                authz_resp = self._post(authz_url, "")  # POST-as-GET
                if authz_resp.status_code == 200:
                    authz = authz_resp.json()
                    domain = authz['identifier']['value']
                    
                    for challenge in authz.get('challenges', []):
                        if challenge['type'] == challenge_type:
                            # Calculate key authorization
                            token = challenge['token']
                            thumbprint = self._jwk_thumbprint(self._get_account_key())
                            key_auth = f"{token}.{thumbprint}"
                            
                            # For DNS-01, value is base64url(sha256(key_auth))
                            if challenge_type == 'dns-01':
                                digest = hashlib.sha256(key_auth.encode()).digest()
                                dns_value = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
                            else:
                                dns_value = key_auth
                            
                            challenges_data[domain] = {
                                'url': challenge['url'],
                                'token': token,
                                'key_authorization': key_auth,
                                'dns_txt_name': f"_acme-challenge.{domain.lstrip('*.')}",
                                'dns_txt_value': dns_value if challenge_type == 'dns-01' else None,
                                'status': challenge['status'],
                            }
                            break
            
            order.set_challenges_dict(challenges_data)
            db.session.add(order)
            db.session.commit()
            
            logger.info(f"Created ACME order for {domains}: {order_url}")
            return True, "Order created successfully", order
            
        except Exception as e:
            logger.error(f"Order creation error: {e}")
            db.session.rollback()
            return False, str(e), None
    
    # =========================================================================
    # Challenge Handling
    # =========================================================================
    
    def setup_dns_challenge(self, order: AcmeClientOrder) -> Tuple[bool, str, Dict]:
        """
        Set up DNS-01 challenges using the configured DNS provider.
        
        Returns:
            Tuple of (success, message, challenge_info)
        """
        if order.challenge_type != 'dns-01':
            return False, "Order is not using DNS-01 challenge", {}
        
        challenges = order.challenges_dict
        if not challenges:
            return False, "No challenges found for order", {}
        
        # Get DNS provider
        if order.dns_provider_id:
            dns_provider_model = DnsProvider.query.get(order.dns_provider_id)
            if not dns_provider_model:
                return False, "DNS provider not found", {}
            
            try:
                credentials = json.loads(dns_provider_model.credentials) if dns_provider_model.credentials else {}
                provider = create_provider(dns_provider_model.provider_type, credentials)
            except Exception as e:
                return False, f"Failed to initialize DNS provider: {e}", {}
        else:
            # Use manual provider
            provider = create_provider('manual', {})
        
        results = {}
        all_success = True
        
        for domain, challenge in challenges.items():
            record_name = challenge['dns_txt_name']
            record_value = challenge['dns_txt_value']
            
            success, message = provider.create_txt_record(
                domain=domain.lstrip('*.'),
                record_name=record_name,
                record_value=record_value,
                ttl=300
            )
            
            results[domain] = {
                'success': success,
                'message': message,
                'record_name': record_name,
                'record_value': record_value,
            }
            
            if not success:
                all_success = False
        
        return all_success, "DNS challenges set up" if all_success else "Some challenges failed", results
    
    def verify_challenge(self, order: AcmeClientOrder, domain: str) -> Tuple[bool, str]:
        """
        Tell ACME server to verify a challenge.
        
        Args:
            order: The order
            domain: Domain to verify
        
        Returns:
            Tuple of (success, message)
        """
        try:
            challenges = order.challenges_dict
            if domain not in challenges:
                return False, f"No challenge found for {domain}"
            
            challenge = challenges[domain]
            challenge_url = challenge['url']
            
            # POST empty object to trigger validation
            resp = self._post(challenge_url, {})
            
            if resp.status_code == 200:
                result = resp.json()
                challenge['status'] = result.get('status', 'processing')
                order.set_challenges_dict(challenges)
                db.session.commit()
                
                return True, f"Challenge submitted: {result.get('status')}"
            else:
                error = resp.json()
                return False, f"Challenge submission failed: {error.get('detail', 'Unknown error')}"
                
        except Exception as e:
            logger.error(f"Challenge verification error: {e}")
            return False, str(e)
    
    def check_order_status(self, order: AcmeClientOrder) -> Tuple[str, Dict]:
        """
        Check current order status from ACME server.
        
        Returns:
            Tuple of (status, order_data)
        """
        try:
            resp = self._post(order.order_url, "")  # POST-as-GET
            if resp.status_code == 200:
                data = resp.json()
                order.status = data.get('status', order.status)
                if data.get('certificate'):
                    order.certificate_url = data['certificate']
                db.session.commit()
                return data.get('status'), data
            return order.status, {}
        except Exception as e:
            logger.error(f"Status check error: {e}")
            return order.status, {}
    
    # =========================================================================
    # Finalization
    # =========================================================================
    
    def finalize_order(self, order: AcmeClientOrder) -> Tuple[bool, str, Optional[int]]:
        """
        Finalize order and download certificate.
        
        Returns:
            Tuple of (success, message, certificate_id)
        """
        try:
            # Check order is ready
            status, data = self.check_order_status(order)
            if status != 'ready':
                return False, f"Order not ready for finalization (status: {status})", None
            
            # Generate CSR
            domains = order.domains_list
            primary_domain = domains[0]
            
            # Generate key pair for certificate
            cert_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            
            # Build CSR
            subject = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, primary_domain.lstrip('*.')),
            ])
            
            # Add SANs
            san_list = [x509.DNSName(d) for d in domains]
            
            csr = x509.CertificateSigningRequestBuilder().subject_name(
                subject
            ).add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False
            ).sign(cert_key, hashes.SHA256(), default_backend())
            
            # Encode CSR as base64url DER
            csr_der = csr.public_bytes(Encoding.DER)
            csr_b64 = base64.urlsafe_b64encode(csr_der).rstrip(b'=').decode()
            
            # Submit CSR to finalize URL
            resp = self._post(order.finalize_url, {"csr": csr_b64})
            
            if resp.status_code not in [200, 201]:
                error = resp.json()
                return False, f"Finalization failed: {error.get('detail', 'Unknown error')}", None
            
            # Poll for certificate
            order_data = resp.json()
            order.status = order_data.get('status', 'processing')
            db.session.commit()
            
            # Wait for certificate (poll up to 30 seconds)
            for _ in range(10):
                if order_data.get('certificate'):
                    break
                time.sleep(3)
                status, order_data = self.check_order_status(order)
                if status == 'invalid':
                    return False, "Order became invalid during finalization", None
            
            if not order_data.get('certificate'):
                return False, "Certificate not ready after polling", None
            
            # Download certificate
            cert_url = order_data['certificate']
            cert_resp = self._post(cert_url, "")
            
            if cert_resp.status_code != 200:
                return False, "Failed to download certificate", None
            
            cert_pem = cert_resp.text
            
            # Store private key
            key_pem = cert_key.private_bytes(
                encoding=Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode()
            
            # Import into UCM certificate store
            cert_id = self._import_certificate(
                cert_pem=cert_pem,
                key_pem=key_pem,
                domains=domains,
                source='acme_client'
            )
            
            if cert_id:
                order.certificate_id = cert_id
                order.status = 'issued'
                db.session.commit()
                
                logger.info(f"Certificate issued for {domains}, ID: {cert_id}")
                return True, "Certificate issued and imported successfully", cert_id
            else:
                return False, "Certificate obtained but import failed", None
                
        except Exception as e:
            logger.error(f"Finalization error: {e}")
            order.status = 'error'
            order.error_message = str(e)
            db.session.commit()
            return False, str(e), None
    
    def _import_certificate(
        self, 
        cert_pem: str, 
        key_pem: str, 
        domains: List[str],
        source: str = 'acme_client'
    ) -> Optional[int]:
        """
        Import certificate into UCM store.
        
        Returns:
            Certificate ID or None
        """
        try:
            from services.certificate_service import CertificateService
            
            # Parse certificate to extract details
            cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
            
            # Create certificate record
            cert_record = Certificate(
                descr=f"Let's Encrypt: {domains[0]}",
                subject_cn=domains[0].lstrip('*.'),
                cert=cert_pem,
                prv=key_pem,
                serial_number=format(cert.serial_number, 'x'),
                valid_from=cert.not_valid_before_utc,
                valid_to=cert.not_valid_after_utc,
                source=source,
                refid=secrets.token_hex(8),
            )
            
            db.session.add(cert_record)
            db.session.commit()
            
            return cert_record.id
            
        except Exception as e:
            logger.error(f"Certificate import error: {e}")
            return None
    
    # =========================================================================
    # Cleanup
    # =========================================================================
    
    def cleanup_dns_challenge(self, order: AcmeClientOrder) -> Tuple[bool, str]:
        """
        Clean up DNS records after certificate issuance.
        """
        if order.challenge_type != 'dns-01' or not order.dns_provider_id:
            return True, "No cleanup needed"
        
        dns_provider_model = DnsProvider.query.get(order.dns_provider_id)
        if not dns_provider_model or dns_provider_model.provider_type == 'manual':
            return True, "Manual cleanup required"
        
        try:
            credentials = json.loads(dns_provider_model.credentials) if dns_provider_model.credentials else {}
            provider = create_provider(dns_provider_model.provider_type, credentials)
            
            challenges = order.challenges_dict
            for domain, challenge in challenges.items():
                provider.delete_txt_record(
                    domain=domain.lstrip('*.'),
                    record_name=challenge['dns_txt_name']
                )
            
            return True, "DNS records cleaned up"
            
        except Exception as e:
            logger.warning(f"DNS cleanup error: {e}")
            return False, str(e)
