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

AUTHZ_INVALID_USER_MSG = (
    'Authorization is invalid for this order. Delete it and request a new certificate.'
)

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


def _legacy_directory_url() -> Optional[str]:
    """Read the legacy ``acme.client.directory_url`` SystemConfig value.

    Returns the trimmed URL or None. Used by :meth:`AcmeClientService.for_issuance`
    to honour the custom ACME directory configured via Settings (issue #147).
    """
    cfg = SystemConfig.query.filter_by(key='acme.client.directory_url').first()
    if not cfg or not cfg.value:
        return None
    url = str(cfg.value).strip()
    return url or None


class AcmeClientService:
    """
    ACME Client for Let's Encrypt and any RFC 8555-compliant CA.
    Handles the full certificate issuance workflow including EAB.
    """
    
    # Well-known ACME directories
    LE_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
    LE_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"

    def __init__(self, environment: str = None, directory_url: str = None,
                 account: 'AcmeClientAccount' = None):
        """
        Initialize ACME client.

        One of three resolution paths (priority order):
          1. `account=` explicit AcmeClientAccount instance.
          2. `directory_url=` explicit URL → lookup or create matching account.
          3. `environment=` 'staging'|'production' → lookup or create LE account.
          4. Neither given → use the row marked is_default=True.

        The resolved account becomes the single source of truth for directory URL,
        account key, account URL, EAB credentials, and key algorithm. The
        `environment` attribute is derived from the URL (staging/production/custom)
        and kept for backward compat with AcmeClientOrder.environment.
        """
        from models.acme_client_account import AcmeClientAccount

        self.account = self._resolve_account(account, directory_url, environment)
        self.directory_url = self.account.directory_url
        self.environment = self.account.derived_environment()
        self.directory = None
        self.account_key = None  # lazy-loaded from self.account.account_key
        self.account_url = self.account.account_url

        self.verify_ssl = self._get_verify_ssl()
        self.session = create_session(verify_ssl=self.verify_ssl)
        self.session.headers['User-Agent'] = 'UCM-ACME-Client/2.1'
        if not self.verify_ssl:
            logger.warning(
                "ACME client SSL verification disabled by settings "
                "(acme.client.verify_ssl=false)."
            )
    
    @staticmethod
    def _resolve_account(account, directory_url, environment):
        """Resolve constructor args to a persisted AcmeClientAccount row.

        Priority: explicit account > directory_url > environment > default.
        Creates a placeholder row if none matches (label/email filled with
        defaults, account_url/account_key empty until registration).
        """
        from models.acme_client_account import AcmeClientAccount

        if account is not None:
            return account

        target_url = None
        target_label = None
        if directory_url:
            target_url = directory_url
            if directory_url == AcmeClientAccount.LE_STAGING_URL:
                target_label = "Let's Encrypt Staging"
            elif directory_url == AcmeClientAccount.LE_PRODUCTION_URL:
                target_label = "Let's Encrypt Production"
            else:
                target_label = f"Custom ({directory_url[:40]})"
        elif environment == 'production':
            target_url = AcmeClientAccount.LE_PRODUCTION_URL
            target_label = "Let's Encrypt Production"
        elif environment == 'staging':
            target_url = AcmeClientAccount.LE_STAGING_URL
            target_label = "Let's Encrypt Staging"
        else:
            # No hint → use default-marked row
            default = AcmeClientAccount.query.filter_by(is_default=True).first()
            if default:
                return default
            # No default → fall back to staging
            target_url = AcmeClientAccount.LE_STAGING_URL
            target_label = "Let's Encrypt Staging"

        existing = AcmeClientAccount.query.filter_by(directory_url=target_url).first()
        if existing:
            return existing

        # Read default email from legacy SystemConfig (1-release back-compat),
        # else fall back to a placeholder. Email gets overwritten at registration.
        email_cfg = SystemConfig.query.filter_by(key='acme.client.email').first()
        email = (email_cfg.value if email_cfg and email_cfg.value else 'admin@localhost')
        alg_cfg = SystemConfig.query.filter_by(key='acme.client.account_key_type').first()
        algorithm = (alg_cfg.value if alg_cfg and alg_cfg.value in ACCOUNT_KEY_TYPES else 'ES256')

        new_account = AcmeClientAccount(
            directory_url=target_url,
            label=target_label,
            email=email,
            account_key_algorithm=algorithm,
            is_default=(AcmeClientAccount.query.count() == 0),
        )
        db.session.add(new_account)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            # Race: another request created it. Re-query.
            existing = AcmeClientAccount.query.filter_by(directory_url=target_url).first()
            if existing:
                return existing
            raise
        logger.info(f"Created placeholder ACME account: {target_label} ({target_url})")
        return new_account

    # ------------------------------------------------------------------
    # Issuance entry-point factory (issue #147)
    # ------------------------------------------------------------------
    @classmethod
    def for_issuance(cls, environment: Optional[str] = None,
                    account_id: Optional[int] = None) -> 'AcmeClientService':
        """Build the service for a NEW issuance / registration flow.

        Resolution priority (multi-CA aware):
          1. ``account_id`` — an explicit ``AcmeClientAccount`` row id. This is
             how per-request CA selection and same-CA renewals are honored: the
             requester picks an account, the order stores it, and renewal passes
             it back here. Wins over everything else.
          2. A configured custom directory
             (``SystemConfig['acme.client.directory_url']``) that is not Let's
             Encrypt — kept for the single-custom-CA setup so
             existing installs without an explicit selection still target it.
          3. ``environment=`` — Let's Encrypt staging/production (legacy).

        Also backfills legacy EAB (``acme.client.eab_kid`` / ``eab_hmac_key``)
        stored in SystemConfig onto the resolved account row.

        Use this for: ``request_certificate``, ``register_account``, and the
        background auto-poll. For operations on an EXISTING order use
        :meth:`for_order` so the CA chosen at creation time is preserved
        even if the directory setting later changes.
        """
        from models.acme_client_account import AcmeClientAccount

        # 1. Explicit account selection (multi-CA).
        if account_id is not None:
            acct = AcmeClientAccount.query.get(account_id)
            if acct is not None:
                svc = cls(account=acct)
                svc._sync_legacy_eab_to_account()
                return svc
            logger.warning(
                f"for_issuance: acme_client_account id={account_id} not found, "
                f"falling back to directory/environment resolution"
            )

        # 2. Configured custom directory (single-custom-CA back-compat).
        custom = _legacy_directory_url()
        if custom and custom not in (AcmeClientAccount.LE_STAGING_URL,
                                     AcmeClientAccount.LE_PRODUCTION_URL):
            svc = cls(directory_url=custom)
            svc._sync_legacy_eab_to_account()
            return svc
        # 3. Let's Encrypt staging/production mapping.
        return cls(environment=environment)

    @classmethod
    def for_order(cls, order: 'AcmeClientOrder') -> 'AcmeClientService':
        """Build the service for an EXISTING order (verify/finalize/status/renew).

        Prefers the order's pinned ``acme_client_account_id`` (migration 047+),
        then the account resolved from ``account_url`` (so a custom-CA order
        keeps its CA even if ``acme.client.directory_url`` was changed/cleared
        after creation), then falls back to :meth:`for_issuance`.
        """
        from models.acme_client_account import AcmeClientAccount

        if order and order.acme_client_account_id:
            acct = AcmeClientAccount.query.get(order.acme_client_account_id)
            if acct:
                return cls(account=acct)
        if order and order.account_url:
            account = AcmeClientAccount.query.filter_by(
                account_url=order.account_url).first()
            if account:
                return cls(account=account)
        return cls.for_issuance(environment=order.environment if order else None)

    def _sync_legacy_eab_to_account(self) -> bool:
        """Copy legacy EAB keys (``acme.client.eab_*``) onto the account row.

        The Settings UI persists EAB into SystemConfig, but issuance reads EAB
        from the ``AcmeClientAccount`` row. For a custom directory configured
        via Settings, the row is created on first use — backfill the EAB there
        so an EAB-required CA registration can succeed. Does
        NOT overwrite an EAB already present on the row.

        Returns True if the account was updated.
        """
        if not self.account:
            return False
        if self.account.eab_kid and self.account.eab_hmac_key:
            return False  # already configured on the row — leave it alone

        kid_cfg = SystemConfig.query.filter_by(key='acme.client.eab_kid').first()
        hmac_cfg = SystemConfig.query.filter_by(key='acme.client.eab_hmac_key').first()
        kid = (kid_cfg.value if kid_cfg and kid_cfg.value else '').strip() or None
        hmac_key = (hmac_cfg.value if hmac_cfg and hmac_cfg.value else '').strip() or None
        if not (kid and hmac_key):
            return False

        self.account.eab_kid = kid
        self.account.eab_hmac_key = hmac_key
        try:
            db.session.commit()
            logger.info(f"Backfilled legacy EAB onto account {self.account.id} "
                        f"({self.account.directory_url})")
            return True
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            logger.error(f"Failed to backfill legacy EAB onto account "
                         f"{self.account.id}: {exc}")
            return False

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
        
    def _http_timeout(self) -> int:
        from models.acme_client_account import AcmeClientAccount
        if self.account:
            return self.account.get_http_timeout_sec()
        return AcmeClientAccount.DEFAULT_HTTP_TIMEOUT_SEC

    def get_poll_settings(self) -> Dict[str, int]:
        """Per-CA order polling settings (timeout, interval, HTTP timeout)."""
        from models.acme_client_account import AcmeClientAccount
        if self.account:
            return {
                'order_poll_timeout_sec': self.account.get_order_poll_timeout_sec(),
                'order_poll_interval_sec': self.account.get_order_poll_interval_sec(),
                'http_timeout_sec': self.account.get_http_timeout_sec(),
            }
        return {
            'order_poll_timeout_sec': AcmeClientAccount.DEFAULT_ORDER_POLL_TIMEOUT_SEC,
            'order_poll_interval_sec': AcmeClientAccount.DEFAULT_ORDER_POLL_INTERVAL_SEC,
            'http_timeout_sec': AcmeClientAccount.DEFAULT_HTTP_TIMEOUT_SEC,
        }

    # =========================================================================
    # Directory & Nonce
    # =========================================================================
    
    def _fetch_directory(self) -> Dict[str, Any]:
        """Fetch ACME directory from server"""
        if self.directory:
            return self.directory
        
        resp = self.session.get(self.directory_url, timeout=self._http_timeout())
        resp.raise_for_status()
        self.directory = resp.json()
        logger.info(f"Fetched ACME directory from {self.directory_url}")
        return self.directory
    
    def _get_nonce(self) -> str:
        """Get a fresh nonce from the ACME server.

        The newNonce HEAD is retried with backoff: some ACME CAs (e.g. ZeroSSL)
        respond slowly/intermittently, and a single transient timeout here would
        otherwise fail challenge submission, status polling and finalization.
        """
        directory = self._fetch_directory()
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                resp = self.session.head(directory['newNonce'], timeout=30)
                resp.raise_for_status()
                return resp.headers['Replay-Nonce']
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    f"newNonce fetch failed (attempt {attempt + 1}/3): {exc}"
                )
                time.sleep(2 * (attempt + 1))
        raise last_exc  # type: ignore[misc]
    
    # =========================================================================
    # Account Key Management
    # =========================================================================
    
    def _get_account_key(self):
        """Load or create account private key (RSA or EC based on settings)"""
        if self.account_key:
            return self.account_key

        if self.account.account_key:
            # Stored value may be encrypted (ENC:...) or legacy plain PEM —
            # decrypt_text() is transparent for both cases.
            from security.encryption import decrypt_text
            self.account_key = serialization.load_pem_private_key(
                decrypt_text(self.account.account_key).encode(),
                password=None,
                backend=default_backend()
            )
            return self.account_key

        # Generate new key for this account
        acct_alg = self.account.account_key_algorithm if self.account.account_key_algorithm in ACCOUNT_KEY_TYPES else 'ES256'
        key_info = ACCOUNT_KEY_TYPES.get(acct_alg, ACCOUNT_KEY_TYPES['RS256'])
        self.account_key = key_info['generate']()

        pem = self.account_key.private_bytes(
            encoding=Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()

        # Encrypt at rest with the master key (no-op if encryption disabled).
        from security.encryption import encrypt_text
        self.account.account_key = encrypt_text(pem)
        self.account.account_key_algorithm = acct_alg
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to save ACME account key: {e}")
            raise
        logger.info(f"Generated new ACME account key ({acct_alg}) for {self.account.label}")
        
        return self.account_key
    
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
        self.account_url = self.account.account_url
        return self.account_url
    
    def _save_account_url(self, url: str) -> None:
        """Save account URL to database"""
        self.account_url = url
        self.account.account_url = url
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
            timeout=self._http_timeout(),
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
                 
                 # Persist the email used for registration
                 self.account.email = email
                 try:
                     db.session.commit()
                 except Exception as e:
                     db.session.rollback()
                     logger.error(f"Failed to update account email: {e}")
                 
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
        """Get EAB credentials for this account"""
        kid = self.account.eab_kid or None
        hmac_key = self.account.eab_hmac_key or None
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
                # Pin the order to its issuing CA account so renewals stay on the
                # same authority instead of re-resolving to the global default.
                acme_client_account_id=getattr(self.account, 'id', None),
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
                                'authz_url': authz_url,
                                'token': token,
                                'key_authorization': key_auth,
                                'dns_txt_name': f"_acme-challenge.{domain.lstrip('*.')}",
                                'dns_txt_value': dns_value if challenge_type == 'dns-01' else None,
                                'status': challenge['status'],
                                'authz_status': authz.get('status'),
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
    
    @staticmethod
    def _authz_error_detail(authz_data: dict) -> str:
        err = authz_data.get('error') or {}
        if isinstance(err, dict) and err.get('detail'):
            return str(err['detail'])
        return ''

    def check_authorization_status(
        self, order: AcmeClientOrder, domain: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """Fetch current authorization status from the CA (POST-as-GET)."""
        challenges = order.challenges_dict
        if domain not in challenges:
            return 'unknown', {}
        authz_url = challenges[domain].get('authz_url')
        if not authz_url:
            return challenges[domain].get('authz_status', 'unknown'), {}

        try:
            resp = self._post(authz_url, '')
            if resp.status_code != 200:
                return challenges[domain].get('authz_status', 'unknown'), {}
            authz = resp.json()
            status = authz.get('status', 'unknown')
            challenges[domain]['authz_status'] = status
            if authz.get('error'):
                challenges[domain]['authz_error'] = authz['error']
            for ch in authz.get('challenges', []):
                if ch.get('type') == order.challenge_type:
                    challenges[domain]['status'] = ch.get('status', challenges[domain].get('status'))
                    if ch.get('error'):
                        challenges[domain]['challenge_error'] = ch['error']
                    break
            order.set_challenges_dict(challenges)
            db.session.commit()
            return status, authz
        except Exception as exc:
            logger.warning('Authorization status check failed for %s: %s', domain, exc)
            return challenges[domain].get('authz_status', 'unknown'), {}

    def find_invalid_authorization(
        self, order: AcmeClientOrder,
    ) -> Optional[Tuple[str, str]]:
        """Return (domain, detail) when any authorization is invalid, else None."""
        for domain in order.challenges_dict:
            status, authz_data = self.check_authorization_status(order, domain)
            if status == 'invalid':
                detail = self._authz_error_detail(authz_data)
                msg = AUTHZ_INVALID_USER_MSG
                if detail:
                    msg = f'{AUTHZ_INVALID_USER_MSG} ({detail})'
                return domain, msg
        return None
    
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

            authz_status, authz_data = self.check_authorization_status(order, domain)
            if authz_status == 'invalid':
                detail = self._authz_error_detail(authz_data)
                msg = AUTHZ_INVALID_USER_MSG
                if detail:
                    msg = f'{AUTHZ_INVALID_USER_MSG} ({detail})'
                return False, msg
            if authz_status == 'valid' or challenge.get('status') == 'valid':
                return True, 'Authorization already valid'

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
                detail = error.get('detail', 'Unknown error')
                if 'invalid' in detail.lower():
                    return False, f'{AUTHZ_INVALID_USER_MSG} ({detail})'
                return False, f"Challenge submission failed: {detail}"
                
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
        Supports configurable key types (RSA-2048/4096, ECDSA P-256/P-384),
        external CSR (key_source=csr), and private key reuse on renewal
        (key_source=reuse).

        Returns:
            Tuple of (success, message, certificate_id)
        """
        try:
            # Check order is ready
            status, data = self.check_order_status(order)
            if status != 'ready':
                return False, f"Order not ready for finalization (status: {status})", None

            domains = order.domains_list
            primary_domain = domains[0]
            key_source = (getattr(order, 'key_source', None) or 'generate').lower()
            cert_key = None
            csr_b64 = None

            if key_source == 'csr':
                if not order.csr_pem:
                    return False, 'External CSR not stored on order', None
                from utils.acme_csr import (
                    load_pem_csr,
                    csr_domains_match_order,
                    csr_to_b64url_der,
                )
                try:
                    csr = load_pem_csr(order.csr_pem)
                except ValueError as exc:
                    return False, str(exc), None
                match_ok, match_msg = csr_domains_match_order(csr, domains)
                if not match_ok:
                    return False, match_msg, None
                csr_b64 = csr_to_b64url_der(csr)
            elif key_source == 'reuse':
                from utils.acme_csr import load_private_key_from_certificate
                from models import Certificate
                src_id = order.source_certificate_id or order.certificate_id
                if not src_id:
                    # First issuance: generate a key; renewals reuse it via source_certificate_id.
                    key_type = getattr(order, 'key_type', None) or self._get_default_key_type()
                    key_generator = CERT_KEY_TYPES.get(key_type, CERT_KEY_TYPES['RSA-2048'])
                    cert_key = key_generator()
                    csr_b64 = self._build_csr_b64(cert_key, domains, primary_domain)
                else:
                    src_cert = Certificate.query.get(src_id)
                    try:
                        cert_key = load_private_key_from_certificate(src_cert)
                    except ValueError as exc:
                        return False, str(exc), None
                    csr_b64 = self._build_csr_b64(cert_key, domains, primary_domain)
            else:
                key_type = getattr(order, 'key_type', None) or self._get_default_key_type()
                key_generator = CERT_KEY_TYPES.get(key_type, CERT_KEY_TYPES['RSA-2048'])
                cert_key = key_generator()
                csr_b64 = self._build_csr_b64(cert_key, domains, primary_domain)

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

            # Store private key (not available for external CSR-only issuance)
            key_pem = None
            if cert_key is not None:
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

    @staticmethod
    def _build_csr_b64(cert_key, domains: List[str], primary_domain: str) -> str:
        """Build a CSR for the given domains and return base64url DER."""
        if isinstance(cert_key, ec.EllipticCurvePrivateKey):
            if isinstance(cert_key.curve, ec.SECP384R1):
                hash_alg = hashes.SHA384()
            else:
                hash_alg = hashes.SHA256()
        else:
            hash_alg = hashes.SHA256()

        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, primary_domain),
        ])
        san_list = [x509.DNSName(d) for d in domains]
        csr = x509.CertificateSigningRequestBuilder().subject_name(
            subject
        ).add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        ).sign(cert_key, hash_alg, default_backend())

        csr_der = csr.public_bytes(Encoding.DER)
        return base64.urlsafe_b64encode(csr_der).rstrip(b'=').decode()
    
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
