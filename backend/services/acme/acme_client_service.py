"""
ACME Client Service (RFC 8555)
Client for requesting certificates from external ACME servers.
Supports Let's Encrypt, HARICA, ZeroSSL, Buypass, Google Trust Services,
and any RFC 8555-compliant CA with optional EAB (§7.3.4).
"""
import json
import base64
import hashlib
import hmac
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List, Union

import requests
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding, utils as asym_utils
from cryptography.hazmat.backends import default_backend
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives.serialization import Encoding

from models import db, SystemConfig, Certificate, DnsProvider, AcmeClientOrder
from services.acme.dns_providers import create_provider, get_provider_class
from utils.safe_requests import create_session

logger = logging.getLogger(__name__)

# Supported key types for account keys and certificate keys
ACCOUNT_KEY_TYPES = {
    'RS256': {'alg': 'RS256', 'generate': lambda: rsa.generate_private_key(65537, 2048, default_backend())},
    'ES256': {'alg': 'ES256', 'generate': lambda: ec.generate_private_key(ec.SECP256R1(), default_backend())},
    'ES384': {'alg': 'ES384', 'generate': lambda: ec.generate_private_key(ec.SECP384R1(), default_backend())},
}

CERT_KEY_TYPES = {
    'RSA-2048': lambda: rsa.generate_private_key(65537, 2048, default_backend()),
    'RSA-4096': lambda: rsa.generate_private_key(65537, 4096, default_backend()),
    'EC-P256': lambda: ec.generate_private_key(ec.SECP256R1(), default_backend()),
    'EC-P384': lambda: ec.generate_private_key(ec.SECP384R1(), default_backend()),
}


class AcmeClientService:
    """
    ACME Client for Let's Encrypt and any RFC 8555-compliant CA.
    Handles the full certificate issuance workflow including EAB.
    """
    
    # Well-known ACME directories
    LE_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
    LE_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"
    
    def __init__(self, environment: str = 'staging', directory_url: str = None):
        """
        Initialize ACME client.
        
        Args:
            environment: 'staging' or 'production' (for LE; ignored if directory_url set)
            directory_url: Custom ACME directory URL (overrides environment)
        """
        self.environment = environment
        
        # Custom directory URL takes precedence
        if directory_url:
            self.directory_url = directory_url
        else:
            # Check for configured custom URL
            custom_url = self._get_custom_directory_url()
            if custom_url:
                self.directory_url = custom_url
            else:
                self.directory_url = self.LE_PRODUCTION if environment == 'production' else self.LE_STAGING
        
        self.directory = None
        self.account_key = None
        self.account_url = None
        self.verify_ssl = self._get_verify_ssl()
        self.session = create_session(verify_ssl=self.verify_ssl)
        self.session.headers['User-Agent'] = 'UCM-ACME-Client/2.1'
        if not self.verify_ssl:
            logger.warning(
                "ACME client SSL verification disabled by settings "
                "(acme.client.verify_ssl=false)."
            )
    
    @staticmethod
    def _get_custom_directory_url() -> Optional[str]:
        """Get custom ACME directory URL from settings"""
        cfg = SystemConfig.query.filter_by(key='acme.client.directory_url').first()
        return cfg.value if cfg and cfg.value else None

    @staticmethod
    def _get_verify_ssl() -> bool:
        """Get ACME client TLS verification setting (default: True)."""
        cfg = SystemConfig.query.filter_by(key='acme.client.verify_ssl').first()
        if not cfg or cfg.value is None:
            return True
        parsed = str(cfg.value).strip().lower()
        if parsed in ('true', '1', 'yes', 'on'):
            return True
        if parsed in ('false', '0', 'no', 'off'):
            return False
        logger.warning(
            "Invalid acme.client.verify_ssl value '%s'; falling back to secure default (True).",
            cfg.value
        )
        return True
        
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
    
    def _get_account_key(self):
        """Load or create account private key (RSA or EC based on settings)"""
        if self.account_key:
            return self.account_key
        
        config_key = f'acme.client.{self.environment}.account_key'
        config = SystemConfig.query.filter_by(key=config_key).first()
        
        if config:
            # Stored value may be encrypted (ENC:...) or legacy plain PEM —
            # decrypt_private_key() is transparent for both cases.
            from security.encryption import decrypt_private_key
            self.account_key = serialization.load_pem_private_key(
                decrypt_private_key(config.value).encode(),
                password=None,
                backend=default_backend()
            )
        else:
            # Determine account key type from settings
            acct_alg = self._get_account_key_algorithm()
            key_info = ACCOUNT_KEY_TYPES.get(acct_alg, ACCOUNT_KEY_TYPES['RS256'])
            self.account_key = key_info['generate']()
            
            pem = self.account_key.private_bytes(
                encoding=Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode()

            # Encrypt at rest with the master key (no-op if encryption disabled)
            from security.encryption import encrypt_private_key
            stored_value = encrypt_private_key(pem)

            db.session.add(SystemConfig(
                key=config_key,
                value=stored_value,
                description=f"ACME client account key ({self.environment})"
            ))
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to save ACME account key: {e}")
                raise
            logger.info(f"Generated new ACME account key ({acct_alg}) for {self.environment}")
        
        return self.account_key
    
    def _get_account_key_algorithm(self) -> str:
        """Get the configured account key algorithm"""
        cfg = SystemConfig.query.filter_by(key='acme.client.account_key_type').first()
        alg = cfg.value if cfg else 'ES256'
        return alg if alg in ACCOUNT_KEY_TYPES else 'ES256'
    
    def _detect_key_algorithm(self, key) -> str:
        """Detect the JWS algorithm for a given key"""
        if isinstance(key, rsa.RSAPrivateKey):
            return 'RS256'
        elif isinstance(key, ec.EllipticCurvePrivateKey):
            curve = key.curve
            if isinstance(curve, ec.SECP256R1):
                return 'ES256'
            elif isinstance(curve, ec.SECP384R1):
                return 'ES384'
        return 'RS256'
    
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
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to save ACME account URL: {e}")
            raise
    
    # =========================================================================
    # JWS Signing (RFC 7515)
    # =========================================================================
    
    def _jwk_thumbprint(self, key) -> str:
        """Calculate JWK thumbprint (RFC 7638) for RSA or EC key"""
        public = key.public_key()
        
        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
        
        if isinstance(key, rsa.RSAPrivateKey):
            numbers = public.public_numbers()
            e = b64url(numbers.e.to_bytes(3, byteorder='big'))
            n_bytes = (numbers.n.bit_length() + 7) // 8
            n = b64url(numbers.n.to_bytes(n_bytes, byteorder='big'))
            jwk_json = json.dumps({"e": e, "kty": "RSA", "n": n}, separators=(',', ':'), sort_keys=True)
        elif isinstance(key, ec.EllipticCurvePrivateKey):
            numbers = public.public_numbers()
            curve = key.curve
            if isinstance(curve, ec.SECP256R1):
                crv, coord_len = "P-256", 32
            elif isinstance(curve, ec.SECP384R1):
                crv, coord_len = "P-384", 48
            else:
                raise ValueError(f"Unsupported EC curve: {curve.name}")
            x_val = b64url(numbers.x.to_bytes(coord_len, byteorder='big'))
            y_val = b64url(numbers.y.to_bytes(coord_len, byteorder='big'))
            # RFC 7638: canonical JSON with sorted keys
            jwk_json = json.dumps({"crv": crv, "kty": "EC", "x": x_val, "y": y_val}, separators=(',', ':'), sort_keys=True)
        else:
            raise ValueError(f"Unsupported key type: {type(key)}")
        
        thumbprint = hashlib.sha256(jwk_json.encode()).digest()
        return base64.urlsafe_b64encode(thumbprint).rstrip(b'=').decode()
    
    def _build_jwk(self, key) -> dict:
        """Build JWK dict for a key (RFC 7517)"""
        def b64url(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
        
        if isinstance(key, rsa.RSAPrivateKey):
            public = key.public_key()
            numbers = public.public_numbers()
            n_bytes = (numbers.n.bit_length() + 7) // 8
            return {
                "kty": "RSA",
                "e": b64url(numbers.e.to_bytes(3, byteorder='big')),
                "n": b64url(numbers.n.to_bytes(n_bytes, byteorder='big')),
            }
        elif isinstance(key, ec.EllipticCurvePrivateKey):
            public = key.public_key()
            numbers = public.public_numbers()
            curve = key.curve
            if isinstance(curve, ec.SECP256R1):
                crv, coord_len = "P-256", 32
            elif isinstance(curve, ec.SECP384R1):
                crv, coord_len = "P-384", 48
            else:
                raise ValueError(f"Unsupported EC curve: {curve.name}")
            return {
                "kty": "EC",
                "crv": crv,
                "x": b64url(numbers.x.to_bytes(coord_len, byteorder='big')),
                "y": b64url(numbers.y.to_bytes(coord_len, byteorder='big')),
            }
        raise ValueError(f"Unsupported key type: {type(key)}")
    
    def _sign_data(self, key, data: bytes) -> bytes:
        """Sign data with RSA or EC key, returning the signature bytes"""
        if isinstance(key, rsa.RSAPrivateKey):
            return key.sign(data, padding.PKCS1v15(), hashes.SHA256())
        elif isinstance(key, ec.EllipticCurvePrivateKey):
            curve = key.curve
            if isinstance(curve, ec.SECP256R1):
                hash_alg = hashes.SHA256()
                coord_len = 32
            elif isinstance(curve, ec.SECP384R1):
                hash_alg = hashes.SHA384()
                coord_len = 48
            else:
                raise ValueError(f"Unsupported EC curve: {curve.name}")
            # EC signature is DER-encoded; ACME needs raw r||s (RFC 7518 §3.4)
            der_sig = key.sign(data, ec.ECDSA(hash_alg))
            r, s = asym_utils.decode_dss_signature(der_sig)
            return r.to_bytes(coord_len, byteorder='big') + s.to_bytes(coord_len, byteorder='big')
        raise ValueError(f"Unsupported key type: {type(key)}")
    
    def _sign_jws(self, url: str, payload: Any, use_jwk: bool = False) -> Dict[str, str]:
        """
        Sign payload as JWS (JSON Web Signature) per RFC 7515.
        Supports RS256, ES256, ES384 based on account key type.
        
        Args:
            url: Target URL (included in protected header)
            payload: Payload to sign (dict or "" for POST-as-GET)
            use_jwk: Include JWK in header (for new account registration)
        """
        key = self._get_account_key()
        nonce = self._get_nonce()
        alg = self._detect_key_algorithm(key)
        
        # Build protected header
        protected = {
            "alg": alg,
            "nonce": nonce,
            "url": url,
        }
        
        if use_jwk:
            protected["jwk"] = self._build_jwk(key)
        else:
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
        signature = self._sign_data(key, signing_input)
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
        Supports External Account Binding (EAB) per RFC 8555 §7.3.4.
        
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
            
            # External Account Binding (EAB) — RFC 8555 §7.3.4
            eab_kid, eab_hmac_key = self._get_eab_credentials()
            if eab_kid and eab_hmac_key:
                eab_payload = self._build_eab_payload(eab_kid, eab_hmac_key, new_account_url)
                payload["externalAccountBinding"] = eab_payload
            elif directory.get('meta', {}).get('externalAccountRequired'):
                return False, "This ACME server requires External Account Binding (EAB). Configure eab_kid and eab_hmac_key in settings.", None
            
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
    
    def _get_eab_credentials(self) -> Tuple[Optional[str], Optional[str]]:
        """Get EAB credentials from settings"""
        kid_cfg = SystemConfig.query.filter_by(key='acme.client.eab_kid').first()
        hmac_cfg = SystemConfig.query.filter_by(key='acme.client.eab_hmac_key').first()
        kid = kid_cfg.value if kid_cfg and kid_cfg.value else None
        hmac_key = hmac_cfg.value if hmac_cfg and hmac_cfg.value else None
        return kid, hmac_key
    
    def _build_eab_payload(self, eab_kid: str, eab_hmac_key: str, url: str) -> dict:
        """
        Build External Account Binding JWS (RFC 8555 §7.3.4).
        The EAB is a JWS signed with the HMAC key, containing the account JWK as payload.
        """
        key = self._get_account_key()
        account_jwk = self._build_jwk(key)
        
        # Protected header for EAB — uses HS256 with the HMAC key
        protected = {
            "alg": "HS256",
            "kid": eab_kid,
            "url": url,
        }
        
        protected_b64 = base64.urlsafe_b64encode(
            json.dumps(protected).encode()
        ).rstrip(b'=').decode()
        
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(account_jwk).encode()
        ).rstrip(b'=').decode()
        
        # Decode the HMAC key (base64url-encoded per RFC 8555)
        # Add padding if needed
        padded = eab_hmac_key + '=' * (4 - len(eab_hmac_key) % 4)
        hmac_key_bytes = base64.urlsafe_b64decode(padded)
        
        # Sign with HMAC-SHA256
        signing_input = f"{protected_b64}.{payload_b64}".encode()
        mac = hmac.new(hmac_key_bytes, signing_input, hashlib.sha256).digest()
        signature_b64 = base64.urlsafe_b64encode(mac).rstrip(b'=').decode()
        
        return {
            "protected": protected_b64,
            "payload": payload_b64,
            "signature": signature_b64,
        }
    
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
        Supports configurable key types (RSA-2048/4096, ECDSA P-256/P-384).
        
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
            
            # Determine key type from order or settings
            key_type = getattr(order, 'key_type', None) or self._get_default_key_type()
            key_generator = CERT_KEY_TYPES.get(key_type, CERT_KEY_TYPES['RSA-2048'])
            cert_key = key_generator()
            
            # Pick hash algorithm based on key type
            if isinstance(cert_key, ec.EllipticCurvePrivateKey):
                if isinstance(cert_key.curve, ec.SECP384R1):
                    hash_alg = hashes.SHA384()
                else:
                    hash_alg = hashes.SHA256()
            else:
                hash_alg = hashes.SHA256()
            
            # Build CSR — CN must match a SAN exactly, otherwise LE treats it
            # as an extra identifier and rejects the CSR (wildcard bug #34)
            subject = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, primary_domain),
            ])
            
            # Add SANs
            san_list = [x509.DNSName(d) for d in domains]
            
            csr = x509.CertificateSigningRequestBuilder().subject_name(
                subject
            ).add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False
            ).sign(cert_key, hash_alg, default_backend())
            
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
                # RFC 8555 §7.1.3: order.expires is the *order resource* expiry
                # (~7 days for Let's Encrypt), NOT the certificate's notAfter.
                # The renewal scheduler compares expires_at against `now + threshold`,
                # so we must replace the order expiry with the cert's notAfter,
                # otherwise the cert will be renewed on every scheduler tick (issue #74).
                try:
                    # cert_pem is a chain; the leaf certificate is the first PEM block.
                    leaf_pem = cert_pem.split('-----END CERTIFICATE-----')[0] + '-----END CERTIFICATE-----\n'
                    leaf = x509.load_pem_x509_certificate(leaf_pem.encode(), default_backend())
                    not_after = leaf.not_valid_after_utc if hasattr(leaf, 'not_valid_after_utc') else leaf.not_valid_after
                    # Strip tzinfo for SQLite-naive datetime column consistency
                    order.expires_at = not_after.replace(tzinfo=None) if not_after.tzinfo else not_after
                except Exception as parse_err:
                    logger.warning(f"Could not parse cert notAfter for order {order.id}: {parse_err}")
                db.session.commit()

                logger.info(f"Certificate issued for {domains}, ID: {cert_id}, expires_at={order.expires_at}")
                return True, "Certificate issued and imported successfully", cert_id
            else:
                return False, "Certificate obtained but import failed", None
                
        except Exception as e:
            logger.error(f"Finalization error: {e}")
            order.status = 'error'
            order.error_message = str(e)
            try:
                db.session.commit()
            except Exception as commit_err:
                db.session.rollback()
                logger.error(f"Failed to save order error state: {commit_err}")
            return False, str(e), None
    
    def _import_certificate(
        self, 
        cert_pem: str, 
        key_pem: str, 
        domains: List[str],
        source: str = 'acme_client'
    ) -> Optional[int]:
        """
        Import certificate into UCM store using CertificateService.
        
        Let's Encrypt returns a full chain (end-entity + intermediates).
        We split it and pass the chain separately for proper storage.
        
        Returns:
            Certificate ID or None
        """
        try:
            from services.cert_service import CertificateService
            
            # Split PEM chain: first cert = end-entity, rest = chain
            pem_blocks = []
            current_block = []
            for line in cert_pem.strip().splitlines():
                current_block.append(line)
                if line.strip() == '-----END CERTIFICATE-----':
                    pem_blocks.append('\n'.join(current_block))
                    current_block = []
            
            if not pem_blocks:
                logger.error("No PEM certificates found in ACME response")
                return None
            
            end_entity_pem = pem_blocks[0]
            chain_pem = '\n'.join(pem_blocks[1:]) if len(pem_blocks) > 1 else None
            
            # Use domain as description (no "Let's Encrypt:" prefix)
            primary_domain = domains[0]
            
            cert_record = CertificateService.import_certificate(
                descr=primary_domain,
                cert_pem=end_entity_pem,
                key_pem=key_pem,
                chain_pem=chain_pem,
                username='system',
                source=source
            )
            
            return cert_record.id if cert_record else None
            
        except Exception as e:
            logger.error(f"Certificate import error: {e}")
            return None
    
    # =========================================================================
    # Configuration Helpers
    # =========================================================================
    
    def _get_default_key_type(self) -> str:
        """Get the default certificate key type from settings"""
        cfg = SystemConfig.query.filter_by(key='acme.client.key_type').first()
        kt = cfg.value if cfg else 'RSA-2048'
        return kt if kt in CERT_KEY_TYPES else 'RSA-2048'
    
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
