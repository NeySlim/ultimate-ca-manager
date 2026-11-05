"""
ACME Client Service (RFC 8555)
Client for requesting certificates from external ACME servers.
Supports Let's Encrypt, HARICA, ZeroSSL, Google Trust Services,
and any RFC 8555-compliant CA with optional EAB (§7.3.4).
"""
import json
import base64
import hashlib
import hmac
import ipaddress
import time
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Any, Optional, Tuple, List, Union, TYPE_CHECKING

import requests
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import load_only
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding, utils as asym_utils
from cryptography.hazmat.backends import default_backend
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives.serialization import Encoding

from models import db, SystemConfig, Certificate, DnsProvider, AcmeClientOrder
from services.acme.dns_providers import create_provider, get_provider_class
from services.acme.dns_selfcheck import acme_allow_loopback_upstream
from services.acme.jwk_thumbprint import jwk_thumbprint
from services.acme import outbound
from utils.safe_requests import create_session
from utils.acme_csr import extract_domains_from_csr
from utils.acme_ip import (
    extract_ip_from_csr_san,
    normalize_ip_for_identifier,
    TlsAlpn01Listener,
)
import fips_mode
from cryptography.exceptions import UnsupportedAlgorithm
from utils.revocation_reasons import normalize_revocation_reason
from utils import key_algorithms, ssrf_protection
from utils.ca_profile import default_digest_for_key_type
from utils.signing_hash import HASH_BY_NAME, signing_hash_for
from utils.san_parse import strip_wildcard
from services.acme.dns_txt_lock import txt_record_lock
from services.acme.order_lease import LEASE_LOST

if TYPE_CHECKING:
    from models.acme_client_account import AcmeClientAccount

logger = logging.getLogger(__name__)

AUTHZ_INVALID_USER_MSG = (
    'Authorization is invalid for this order. Delete it and request a new certificate.'
)

# Supported key types for account keys and certificate keys
ACCOUNT_KEY_TYPES = {
    'RS256': {'alg': 'RS256', 'generate': lambda: key_algorithms.generate('RSA-2048')},
    'ES256': {'alg': 'ES256', 'generate': lambda: key_algorithms.generate('EC-P256')},
    'ES384': {'alg': 'ES384', 'generate': lambda: key_algorithms.generate('EC-P384')},
}

CERT_KEY_TYPES = {
    'RSA-2048': lambda: key_algorithms.generate('RSA-2048'),
    'RSA-4096': lambda: key_algorithms.generate('RSA-4096'),
    'EC-P256': lambda: key_algorithms.generate('EC-P256'),
    'EC-P384': lambda: key_algorithms.generate('EC-P384'),
    # Certificate keys only: an ACME account key has no Brainpool JWS algorithm
    'EC-BP256': lambda: key_algorithms.generate('EC-BP256'),
    'EC-BP384': lambda: key_algorithms.generate('EC-BP384'),
    # Certificate keys only, registered when this build has ML-DSA; FIPS mode refuses them
    **{label: (lambda label=label: key_algorithms.generate(label))
       for label in key_algorithms.labels('ML-DSA')},
}


def fips_key_type_refusal(label):
    """Why FIPS mode refuses the certificate key type *label*, or None."""
    alg = key_algorithms.get(label)
    if alg is not None and not alg.fips_approved and fips_mode.enabled():
        return f'{alg.display} keys not available in FIPS mode'
    return None


def fips_private_key_refusal(private_key):
    """Why FIPS mode refuses signing with *private_key* (a reused key), or None."""
    return fips_key_type_refusal(key_algorithms.label_for_private_key(private_key))


def fips_csr_refusal(csr):
    """Why FIPS mode refuses an external CSR's key, or None; read without loading the key."""
    if not fips_mode.enabled():
        return None
    from services.fips_preflight import certificate_key
    name, approved = certificate_key(csr)
    if approved:
        return None
    oid = csr.public_key_algorithm_oid.dotted_string
    if name == f'unreadable key ({oid})':
        return (f'The CSR key (algorithm {oid}) cannot be read; FIPS mode accepts RSA 2048+ '
                'and ECDSA P-256, P-384 or P-521 keys')
    return f'{name} keys not available in FIPS mode'


def csr_identifiers_match_order(
    csr: x509.CertificateSigningRequest,
    order_identifiers: List[str],
) -> Tuple[bool, str]:
    """Compare DNS and RFC 8738 IP SAN identifiers with an ACME order."""
    csr_values = {
        ('dns', value.lower().rstrip('.'))
        for value in extract_domains_from_csr(csr)
        if normalize_ip_for_identifier(value) is None
    }
    csr_values.update(
        ('ip', normalize_ip_for_identifier(value))
        for value in extract_ip_from_csr_san(csr)
    )

    order_values = set()
    for value in order_identifiers:
        normalized_ip = normalize_ip_for_identifier(value)
        if normalized_ip is not None:
            order_values.add(('ip', normalized_ip))
        else:
            order_values.add(('dns', value.lower().rstrip('.')))

    if not csr_values:
        return False, 'CSR contains no DNS or IP identifiers'
    if csr_values != order_values:
        csr_display = sorted(value for _kind, value in csr_values)
        order_display = sorted(value for _kind, value in order_values)
        return False, (
            f"CSR identifiers {csr_display} don't match order identifiers "
            f'{order_display}'
        )
    return True, 'CSR identifiers match order'


def get_stored_tls_alpn_port() -> int:
    """Stored TLS-ALPN-01 listen port (``acme.client.tls_alpn_port``); 443 when missing or invalid."""
    cfg = SystemConfig.query.filter_by(key='acme.client.tls_alpn_port').first()
    try:
        return int(cfg.value) if cfg and cfg.value else 443
    except (TypeError, ValueError):
        return 443


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

    _order_retry_after = None

    def __init__(self, environment: str = None, directory_url: str = None,
                 account: 'AcmeClientAccount' = None,
                 tls_alpn_port: Optional[int] = None):
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
        self._tls_alpn_port_override = tls_alpn_port

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

        def _first_for_url(url):
            """When several accounts share a directory URL (#276), prefer the
            default one, otherwise deterministically the oldest row."""
            return (AcmeClientAccount.query
                    .filter_by(directory_url=url)
                    .order_by(AcmeClientAccount.is_default.desc(),
                              AcmeClientAccount.id.asc())
                    .first())

        existing = _first_for_url(target_url)
        if existing:
            return existing

        # The placeholder is load-bearing: an installation that never set the
        # key still has to be able to create the account row, and the address
        # is overwritten at registration. The settings API reporting None for
        # the same key is not a contradiction -- it answers "what did the
        # operator configure", not "what will be registered".
        from services.settings_registry import effective

        email = effective('acme.client.email')
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
            existing = _first_for_url(target_url)
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
            acct = db.session.get(AcmeClientAccount, account_id)
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
            acct = db.session.get(AcmeClientAccount, order.acme_client_account_id)
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
        raw_hmac = (hmac_cfg.value if hmac_cfg and hmac_cfg.value else '').strip()
        if raw_hmac:
            from security.encryption import decrypt_text
            hmac_key = decrypt_text(raw_hmac).strip() or None
        else:
            hmac_key = None
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

    def wait_for_order(self, order: AcmeClientOrder) -> Tuple[str, Dict]:
        """Poll until the authorizations are settled: the order leaves `pending`, or the per-CA
        poll timeout runs out. Returns the last status and body."""
        deadline, interval = self._order_poll_limits()
        while True:
            status, data = self.check_order_status(order)
            if status != 'pending' or not self._sleep_before_next_poll(deadline, interval):
                return status, data

    def _order_poll_limits(self) -> Tuple[float, int]:
        poll = self.get_poll_settings()
        return (time.monotonic() + max(1, int(poll['order_poll_timeout_sec'])),
                max(1, int(poll['order_poll_interval_sec'])))

    def _sleep_before_next_poll(self, deadline: float, interval: int) -> bool:
        """Wait as long as the CA's last Retry-After asks (RFC 8555 §7.4), or the interval.
        False when the deadline has passed: nothing more to poll."""
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(self._order_retry_after or interval, remaining))
        return True

    def _note_retry_after(self, response) -> None:
        """Keep the seconds asked by this response; none or unreadable leaves the interval."""
        try:
            retry_at = self._parse_retry_after(response.headers.get('Retry-After'))
        except (ValueError, OverflowError):
            retry_at = None
        wait = (retry_at - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds() if retry_at else 0
        self._order_retry_after = wait if wait > 0 else None

    # =========================================================================
    # Directory & Nonce
    # =========================================================================

    @staticmethod
    def _validate_outbound_acme_url(url: str) -> None:
        """Block loopback/cloud-metadata targets for ACME sub-URLs from directory JSON."""
        outbound.validate_outbound_acme_url(url)


    def _fetch_directory(self) -> Dict[str, Any]:
        """Fetch ACME directory from server"""
        if self.directory:
            return self.directory

        resp = ssrf_protection.safe_request_get(
            self.directory_url,
            allow_loopback=acme_allow_loopback_upstream(),
            timeout=self._http_timeout(),
            verify=self.verify_ssl,
            headers={'User-Agent': self.session.headers.get('User-Agent', 'UCM-ACME-Client/2.1')},
        )
        resp.raise_for_status()
        self.directory = resp.json()
        logger.info(f"Fetched ACME directory from {self.directory_url}")
        return self.directory
    
    def _get_nonce(self) -> str:
        """Get a nonce for the ACME server, reusing a pooled one first.

        Pooled values are Replay-Nonce headers kept from earlier responses (RFC
        8555 §6.5), which saves a HEAD /new-nonce round-trip; a stale pooled
        value is still covered by the badNonce retry in _post. The HEAD falls
        back to the shared backoff, on the operator's configured HTTP timeout
        rather than a hard-coded 30 that ignored it.
        """
        pooled = outbound.nonce_pool_pop(self.directory_url)
        if pooled:
            return pooled
        directory = self._fetch_directory()
        return outbound.fetch_nonce(
            directory['newNonce'],
            timeout=self._http_timeout(),
            verify=self.verify_ssl,
            headers=dict(self.session.headers),
        )


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
        # One default for an unknown label, not two disagreeing ones: the line
        # above already guarantees membership, so the `.get` fallback to RS256
        # was unreachable and said the opposite of the ES256 it followed.
        acct_alg = self.account.account_key_algorithm if self.account.account_key_algorithm in ACCOUNT_KEY_TYPES else 'ES256'
        key_info = ACCOUNT_KEY_TYPES[acct_alg]
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
        # Account keys are generated or imported as RSA, P-256 or P-384 only
        raise ValueError(f'Unsupported ACME account key: {type(key).__name__}')
    
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
        """Calculate JWK thumbprint (RFC 7638) for RSA or EC key

        Takes a key object rather than a JWK dict, which is why it stays here:
        it has to derive the JWK first. The canonicalization that follows is
        the shared one, so this cannot drift from the thumbprint the server
        stored on the account or the one the proxy compares against.
        """
        return jwk_thumbprint(self._build_jwk(key))


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
    
    def _sign_jws(self, url: str, payload: Any, use_jwk: bool = False,
                  nonce: Optional[str] = None) -> Dict[str, str]:
        """
        Sign payload as JWS (JSON Web Signature) per RFC 7515.
        Supports RS256, ES256, ES384 based on account key type.

        Args:
            url: Target URL (included in protected header)
            payload: Payload to sign (dict or "" for POST-as-GET)
            use_jwk: Include JWK in header (for new account registration)
            nonce: Nonce to sign with; a fresh one is taken when omitted. The
                badNonce retry passes the one the server just handed back.
        """
        key = self._get_account_key()
        nonce = nonce or self._get_nonce()
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
        """POST signed JWS to ACME endpoint, retrying once on badNonce.

        RFC 8555 §6.5: on badNonce the server returns a fresh nonce and the
        client retries with it. Without the retry a badNonce was terminal here,
        while the proxy side recovered from the same answer.
        """
        self._validate_outbound_acme_url(url)
        resp = self._sign_and_post(url, payload, use_jwk=use_jwk)

        fresh_nonce = outbound.bad_nonce_retry_value(resp)
        if fresh_nonce:
            logger.warning(f"Upstream rejected nonce on {url}, retrying with fresh nonce")
            resp = self._sign_and_post(url, payload, use_jwk=use_jwk,
                                       nonce=fresh_nonce)
        return resp

    def _sign_and_post(self, url: str, payload: Any, use_jwk: bool = False,
                       nonce: Optional[str] = None) -> requests.Response:
        """Build a JWS with the given nonce (or a fresh one) and POST it once.

        ``nonce`` is passed only when the retry has one to spend, so the normal
        path calls _sign_jws exactly as it always did.
        """
        jws = self._sign_jws(url, payload, use_jwk=use_jwk,
                             **({'nonce': nonce} if nonce else {}))
        resp = ssrf_protection.safe_request_post(
            url,
            allow_loopback=acme_allow_loopback_upstream(),
            json=jws,
            headers={
                "Content-Type": "application/jose+json",
                **dict(self.session.headers),
            },
            timeout=self._http_timeout(),
            verify=self.verify_ssl,
        )
        # A 400 may be badNonce, whose nonce the retry spends: pooling it would serve it twice.
        if getattr(resp, 'status_code', None) != 400:
            headers = getattr(resp, 'headers', None)
            replay_nonce = headers.get('Replay-Nonce') if hasattr(headers, 'get') else None
            outbound.nonce_pool_push(self.directory_url, replay_nonce)
        return resp


    @staticmethod
    def validate_revocation_reason(reason: int) -> int:
        """Validate an RFC 5280 CRLReason code accepted by ACME."""
        valid_reasons = {0, 1, 2, 3, 4, 5, 6, 8, 9, 10}
        if isinstance(reason, bool) or not isinstance(reason, int) or reason not in valid_reasons:
            raise ValueError("Invalid certificate revocation reason code")
        return reason

    @staticmethod
    def _load_x509_certificate(certificate) -> x509.Certificate:
        """Load a certificate model, X.509 object, PEM, or DER value."""
        if isinstance(certificate, x509.Certificate):
            return certificate

        if isinstance(certificate, Certificate):
            if not certificate.crt:
                raise ValueError("Certificate data is unavailable")
            try:
                raw = base64.b64decode(certificate.crt, validate=True)
            except (ValueError, base64.binascii.Error) as exc:
                raise ValueError("Invalid certificate data") from exc
        elif isinstance(certificate, str):
            raw = certificate.encode()
        elif isinstance(certificate, (bytes, bytearray)):
            raw = bytes(certificate)
        else:
            raise ValueError("Unsupported certificate value")

        try:
            if raw.lstrip().startswith(b'-----BEGIN CERTIFICATE-----'):
                return x509.load_pem_x509_certificate(raw, default_backend())
            return x509.load_der_x509_certificate(raw, default_backend())
        except ValueError as exc:
            raise ValueError("Invalid certificate data") from exc

    @staticmethod
    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

    @classmethod
    def certificate_identifier(cls, certificate) -> str:
        """Build the RFC 9773 CertID: base64url(AKI).base64url(serial)."""
        cert_obj = cls._load_x509_certificate(certificate)
        try:
            aki = cert_obj.extensions.get_extension_for_class(
                x509.AuthorityKeyIdentifier
            ).value.key_identifier
        except x509.ExtensionNotFound as exc:
            raise ValueError("Certificate has no Authority Key Identifier") from exc
        if not aki:
            raise ValueError("Certificate has no Authority Key Identifier")

        # The value bytes of the DER INTEGER: a leading 1 bit takes a zero byte (RFC 9773 §4.1)
        serial_length = cert_obj.serial_number.bit_length() // 8 + 1
        serial_bytes = cert_obj.serial_number.to_bytes(serial_length, 'big')
        return f"{cls._b64url(aki)}.{cls._b64url(serial_bytes)}"

    @staticmethod
    def _parse_ari_datetime(value: str) -> datetime:
        if not isinstance(value, str) or not value:
            raise ValueError("Invalid ARI suggested window")
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError("Invalid ARI suggested window") from exc
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    @staticmethod
    def _parse_retry_after(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        now = datetime.now(timezone.utc)
        try:
            seconds = int(value)
            if seconds < 0:
                raise ValueError
            retry_at = now + timedelta(seconds=seconds)
        except (TypeError, ValueError):
            try:
                retry_at = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Invalid ARI Retry-After header") from exc
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            retry_at = retry_at.astimezone(timezone.utc)
        return retry_at.replace(tzinfo=None)

    def revoke_certificate(self, certificate_pem_or_der, reason: int = 0) -> requests.Response:
        """Revoke a certificate upstream using the registered account KID.

        The certificate is encoded as base64url DER and the request is signed
        with the external ACME account key, as required by RFC 8555 §7.6.
        """
        reason = self.validate_revocation_reason(reason)
        cert_obj = self._load_x509_certificate(certificate_pem_or_der)
        directory = self._fetch_directory()
        revoke_url = directory.get('revokeCert')
        if not revoke_url:
            raise ValueError("ACME server does not advertise certificate revocation")

        payload = {
            'certificate': self._b64url(
                cert_obj.public_bytes(serialization.Encoding.DER)
            ),
            'reason': reason,
        }
        return self._post(revoke_url, payload, use_jwk=False)

    def get_renewal_info(self, certificate) -> Optional[Dict[str, Any]]:
        """Fetch and parse upstream ACME Renewal Information (RFC 9773)."""
        directory = self._fetch_directory()
        renewal_base_url = directory.get('renewalInfo')
        if not renewal_base_url:
            return None

        cert_id = self.certificate_identifier(certificate)
        renewal_url = f"{renewal_base_url.rstrip('/')}/{cert_id}"
        self._validate_outbound_acme_url(renewal_url)
        response = ssrf_protection.safe_request_get(
            renewal_url,
            allow_loopback=acme_allow_loopback_upstream(),
            timeout=self._http_timeout(),
            verify=self.verify_ssl,
            headers=dict(self.session.headers),
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"ACME renewal information request failed with HTTP {response.status_code}"
            )

        try:
            data = response.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as exc:
            raise ValueError("Invalid ACME renewal information response") from exc
        window = data.get('suggestedWindow') if isinstance(data, dict) else None
        if not isinstance(window, dict):
            raise ValueError("Invalid ACME renewal information response")
        start = self._parse_ari_datetime(window.get('start'))
        end = self._parse_ari_datetime(window.get('end'))
        if end <= start:
            raise ValueError("Invalid ARI suggested window")

        return {
            'cert_id': cert_id,
            'suggested_window': {'start': start, 'end': end},
            'retry_after': self._parse_retry_after(
                response.headers.get('Retry-After')
            ),
        }

    def _fetch_alternate_chain_pem(self, url: str) -> str:
        """POST-as-GET an alternate certificate URL from directory Link headers."""
        self._validate_outbound_acme_url(url)
        resp = self._post(url, "")
        if resp.status_code != 200:
            raise RuntimeError(
                f'Alternate chain fetch failed: HTTP {resp.status_code}'
            )
        return resp.text

    def _select_certificate_chain(self, cert_resp) -> str:
        from services.acme.acme_chain_selection import select_acme_certificate_chain

        acct = getattr(self, 'account', None)
        preferred = None
        if acct is not None:
            preferred = (acct.preferred_chain or '').strip() or None
        return select_acme_certificate_chain(
            cert_resp.text,
            cert_resp.headers,
            preferred,
            self._fetch_alternate_chain_pem,
        )

    # =========================================================================
    # Account Management
    # =========================================================================
    
    def register_account(self, email: Optional[str]) -> Tuple[bool, str, Optional[str]]:
        """
        Register or retrieve existing ACME account.
        Supports External Account Binding (EAB) per RFC 8555 §7.3.4.

        Args:
            email: Contact email address, or None to register without a
                contact (RFC 8555 makes `contact` optional; Let's Encrypt
                accepts contact-less registrations)

        Returns:
            Tuple of (success, message, account_url)
        """
        try:
            directory = self._fetch_directory()
            new_account_url = directory['newAccount']

            payload = {"termsOfServiceAgreed": True}
            if email:
                payload["contact"] = [f"mailto:{email}"]
            
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

                 # Persist the email used for registration (keep the existing
                 # one on a contact-less registration)
                 if email:
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
    
    def deactivate_account(self) -> Tuple[bool, str]:
        """Deactivate the account upstream (RFC 8555 §7.3.6).

        POSTs {"status": "deactivated"} to the account URL, signed with the
        account key (kid header). Deactivation is permanent — a successfully
        deactivated account can never be re-enabled or registered again with
        the same key.

        Returns:
            Tuple of (success, message)
        """
        account_url = self._get_account_url()
        if not account_url:
            return False, 'Account is not registered'
        try:
            resp = self._post(account_url, {"status": "deactivated"})
            if resp.status_code == 200:
                try:
                    status = (resp.json() or {}).get('status', '')
                except ValueError:
                    status = ''
                if status == 'deactivated':
                    logger.info(f"ACME account deactivated: {account_url}")
                    return True, 'Account deactivated'
                return False, f"ACME server acknowledged the request but account status is {status!r}"
            try:
                detail = (resp.json() or {}).get('detail') or f'HTTP {resp.status_code}'
            except ValueError:
                detail = f'HTTP {resp.status_code}'
            return False, f'Account deactivation failed: {detail}'
        except Exception as e:
            logger.error(f"ACME account deactivation error: {e}")
            return False, str(e)

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
        dns_provider_id: Optional[int] = None,
        replaces: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[AcmeClientOrder]]:
        """
        Create a new certificate order.
        
        Args:
            domains: List of DNS names and/or IP addresses
            email: Contact email
            challenge_type: 'http-01', 'dns-01', or 'tls-alpn-01'
            dns_provider_id: DNS provider for DNS-01 challenges
        
        Returns:
            Tuple of (success, message, order)
        """
        try:
            if challenge_type not in ('dns-01', 'http-01', 'tls-alpn-01'):
                return False, 'Unsupported ACME challenge type', None

            identifiers = []
            normalized_domains = []
            for value in domains:
                normalized_ip = normalize_ip_for_identifier(value)
                identifier_type = 'ip' if normalized_ip is not None else 'dns'
                normalized_value = normalized_ip or value
                identifiers.append({'type': identifier_type, 'value': normalized_value})
                normalized_domains.append(normalized_value)

            if challenge_type == 'dns-01' and any(
                identifier['type'] == 'ip' for identifier in identifiers
            ):
                return False, 'dns-01 cannot be used with IP identifiers', None

            # Ensure account exists
            success, msg = self.ensure_account(email)
            if not success:
                return False, msg, None

            # Create order at the external ACME CA.
            directory = self._fetch_directory()

            payload = {"identifiers": identifiers}
            sent_replaces = bool(replaces and directory.get('renewalInfo'))
            if sent_replaces:
                payload['replaces'] = replaces

            resp = self._post(directory['newOrder'], payload)

            # RFC 9773 `replaces` is best-effort: Boulder rejects a newOrder
            # whose replaces designates an already-replaced certificate
            # (alreadyReplaced/409). Without a fallback the renewal fails on
            # every cycle until expiry — retry once without the field.
            if resp.status_code not in [200, 201] and sent_replaces:
                try:
                    err_body = resp.json()
                except Exception:
                    err_body = {}
                err_text = f"{err_body.get('type', '')} {err_body.get('detail', '')}".lower()
                # A CA may reject the field however it likes. A rate limit is not about it,
                # whatever its status: RFC 8555 §6.6 names it by type.
                rate_limited = resp.status_code == 429 or 'ratelimited' in err_text
                if not rate_limited and (400 <= resp.status_code < 500 or 'replace' in err_text):
                    logger.warning(
                        "newOrder with replaces rejected (%s); retrying without "
                        "replaces: %s", resp.status_code, err_body.get('detail'),
                    )
                    payload.pop('replaces', None)
                    resp = self._post(directory['newOrder'], payload)

            if resp.status_code not in [200, 201]:
                error = resp.json()
                return False, f"Order creation failed: {error.get('detail', 'Unknown error')}", None
            
            order_data = resp.json()
            order_url = resp.headers.get('Location')
            
            # Create local order record
            order = AcmeClientOrder(
                domains=json.dumps(normalized_domains),
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
                    authz_identifier = authz['identifier']
                    domain = authz_identifier['value']
                    if authz_identifier.get('type') == 'ip':
                        domain = normalize_ip_for_identifier(domain) or domain
                    # A wildcard authz names the base domain (RFC 8555 §7.1.4): keep it apart from the apex
                    if authz.get('wildcard') and not domain.startswith('*.'):
                        domain = f"*.{domain}"

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
                                'identifier_type': authz_identifier.get('type', 'dns'),
                                'dns_txt_name': f"_acme-challenge.{strip_wildcard(domain)}",
                                'dns_txt_value': dns_value if challenge_type == 'dns-01' else None,
                                'status': challenge['status'],
                                'authz_status': authz.get('status'),
                            }
                            break
            
            order.set_challenges_dict(challenges_data)
            db.session.add(order)
            db.session.commit()
            
            logger.info(f"Created ACME order for {normalized_domains}: {order_url}")
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
            dns_provider_model = db.session.get(DnsProvider, order.dns_provider_id)
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
            
            with txt_record_lock(record_name):
                success, message = provider.create_txt_record(
                    domain=strip_wildcard(domain),
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
        for challenge in authz_data.get('challenges') or []:
            challenge_error = challenge.get('error') or {}
            if isinstance(challenge_error, dict) and challenge_error.get('detail'):
                return str(challenge_error['detail'])
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

            if order.challenge_type == 'tls-alpn-01':
                return self._verify_tls_alpn_challenge(order, domain)

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

    def _tls_alpn_listen_port(self) -> int:
        """Resolve the proof-listener port (443, overrideable for test setups)."""
        if self._tls_alpn_port_override is not None:
            port = int(self._tls_alpn_port_override)
        else:
            port = get_stored_tls_alpn_port()
        if not 1 <= port <= 65535:
            raise ValueError('TLS-ALPN-01 listen port must be between 1 and 65535')
        return port

    def _create_tls_alpn_listener(self, identifier: str, key_authorization: str):
        return TlsAlpn01Listener(
            identifier,
            key_authorization,
            port=self._tls_alpn_listen_port(),
        )

    def _verify_tls_alpn_challenge(
        self, order: AcmeClientOrder, identifier: str,
    ) -> Tuple[bool, str]:
        """Serve the RFC 8737 proof while the external CA validates it."""
        challenges = order.challenges_dict
        challenge = challenges.get(identifier)
        if not challenge:
            return False, f'No challenge found for {identifier}'

        listener = self._create_tls_alpn_listener(
            identifier, challenge['key_authorization']
        )
        try:
            listener.start()
            response = self._post(challenge['url'], {})
            if response.status_code != 200:
                try:
                    detail = response.json().get('detail', 'Unknown error')
                except Exception:
                    detail = 'Unknown error'
                return False, f'Challenge submission failed: {detail}'

            result = response.json()
            challenge['status'] = result.get('status', 'processing')
            order.set_challenges_dict(challenges)
            db.session.commit()
            if challenge['status'] == 'valid':
                return True, 'TLS-ALPN-01 challenge validated'

            poll = self.get_poll_settings()
            timeout = max(1, int(poll['order_poll_timeout_sec']))
            interval = max(1, int(poll['order_poll_interval_sec']))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                authz_status, authz_data = self.check_authorization_status(
                    order, identifier
                )
                if authz_status == 'valid':
                    return True, 'TLS-ALPN-01 challenge validated'
                if authz_status == 'invalid':
                    detail = self._authz_error_detail(authz_data)
                    message = AUTHZ_INVALID_USER_MSG
                    if detail:
                        message = f'{message} ({detail})'
                    return False, message
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(min(interval, remaining))

            return False, (
                f'TLS-ALPN-01 validation timed out after {timeout}s while '
                f'the listener was active on port {listener.port}'
            )
        except Exception as exc:
            logger.error('TLS-ALPN-01 verification failed for %s: %s', identifier, exc)
            return False, str(exc)
        finally:
            listener.stop()

    def fetch_order_state(self, order: AcmeClientOrder) -> str:
        """The order's status at the CA, written nowhere; 'gone' when the CA no longer has it."""
        resp = self._post(order.order_url, "")  # POST-as-GET
        if resp.status_code in (404, 410):
            return 'gone'
        if resp.status_code != 200:
            raise RuntimeError(f"Status of order {order.id} unavailable: HTTP {resp.status_code}")
        return resp.json().get('status') or 'gone'

    @staticmethod
    def write_order_status(order, status: str) -> bool:
        """Write a status, unless the order is issued: that means imported here, which the CA
        cannot know and the scheduler needs. Tested in the write, as a background finalize may
        import at any moment. The caller commits, and sees the outcome after that.

        Returns False when an import won: the caller's failure is then no longer the order's."""
        return AcmeClientOrder.query.filter(
            AcmeClientOrder.id == order.id, AcmeClientOrder.status != 'issued',
        ).update({'status': status}, synchronize_session=False) > 0

    def check_order_status(self, order: AcmeClientOrder) -> Tuple[str, Dict]:
        """
        Check current order status from ACME server.
        
        Returns:
            Tuple of (status, order_data)
        """
        try:
            resp = self._post(order.order_url, "")  # POST-as-GET
            self._note_retry_after(resp)
            if resp.status_code == 200:
                data = resp.json()
                self.write_order_status(order, data.get('status', order.status))
                if data.get('certificate'):
                    order.certificate_url = data['certificate']
                db.session.commit()
                return data.get('status'), data
            return order.status, {}
        except Exception as e:
            logger.error(f"Status check error: {e}")
            if isinstance(e, SQLAlchemyError):
                # Otherwise every later statement of this request fails too
                db.session.rollback()
            return order.status, {}
    
    # =========================================================================
    # Finalization
    # =========================================================================
    
    @staticmethod
    def _revoked_as_compromised(certificate) -> bool:
        return bool(certificate.revoked
                    and normalize_revocation_reason(certificate.revoke_reason) == 'keyCompromise')

    @classmethod
    def _key_revoked_as_compromised(cls, public_key) -> bool:
        """Whether any row holding this key was revoked as compromised: a key reused along
        renewals sits on several certificates, and only one of them may carry the revocation."""
        wanted = public_key.public_bytes(Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        rows = Certificate.query.options(load_only(Certificate.crt, Certificate.revoked, Certificate.revoke_reason))
        for row in rows.filter(Certificate.revoked.is_(True)).all():
            if not row.crt or not cls._revoked_as_compromised(row):
                continue
            try:
                held = cls._load_x509_certificate(row).public_key()
            except (ValueError, UnsupportedAlgorithm):
                continue  # a row this build cannot read says nothing about this key
            if held.public_bytes(Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) == wanted:
                return True
        return False

    def held_finalize_key(self, order: AcmeClientOrder) -> Tuple[Optional[str], Optional[str]]:
        """The PEM key an order the CA already finalized was certified with: ``(pem, None)``,
        ``(None, None)`` for an external CSR, ``(None, error)`` when the key is not held."""
        pending = order.pending_key
        if pending:
            return pending, None
        key_source = (order.key_source or 'generate').lower()
        if key_source == 'csr':
            return None, None
        src_id = order.source_certificate_id or order.certificate_id
        if key_source == 'reuse' and src_id:
            # The key the request carried, even if revoked since: it is the certificate's
            src_cert = db.session.get(Certificate, src_id)
            if src_cert is None or not src_cert.prv:
                return None, 'The certificate holding the key to reuse no longer exists'
            from utils.key_codec import load_pem_bytes
            return load_pem_bytes(src_cert.prv, context=f'certificate {src_id}').decode(), None
        return None, ('The key this order was finalized with was not kept: '
                      'the certificate cannot be imported, request a new one')

    def _finalize_key(self, order, domains, primary_domain):
        """``(key or None, CSR b64url, key to keep as pending, error)`` for a finalize request."""
        key_source = (getattr(order, 'key_source', None) or 'generate').lower()
        pending = order.pending_key
        if pending:
            # A request that may never have reached the CA: sent again with the same key
            cert_key = serialization.load_pem_private_key(pending.encode(), password=None)
            return cert_key, self._build_csr_b64(cert_key, domains, primary_domain), True, None

        if key_source == 'csr':
            if not order.csr_pem:
                return None, None, False, 'External CSR not stored on order'
            from utils.acme_csr import load_pem_csr, csr_to_b64url_der
            try:
                csr = load_pem_csr(order.csr_pem)
            except ValueError as exc:
                return None, None, False, str(exc)
            match_ok, match_msg = csr_identifiers_match_order(csr, domains)
            if not match_ok:
                return None, None, False, match_msg
            if self._key_revoked_as_compromised(csr.public_key()):
                return None, None, False, 'The key of this CSR was revoked as compromised: submit a new CSR'
            return None, csr_to_b64url_der(csr), False, None

        cert_key = None
        if key_source == 'reuse':
            from utils.acme_csr import load_private_key_from_certificate
            src_id = order.source_certificate_id or order.certificate_id
            src_cert = db.session.get(Certificate, src_id) if src_id else None
            if src_id and src_cert is None:
                return None, None, False, 'The certificate holding the key to reuse no longer exists'
            if src_cert is not None and not self._revoked_as_compromised(src_cert):
                try:
                    cert_key = load_private_key_from_certificate(src_cert)
                except ValueError as exc:
                    return None, None, False, str(exc)
                refusal = fips_private_key_refusal(cert_key)
                if refusal:
                    return None, None, False, refusal
                if self._key_revoked_as_compromised(cert_key.public_key()):
                    cert_key = None
            if src_cert is not None and cert_key is None:
                logger.warning("Order %s does not reuse the key of certificate %s, revoked as "
                               "compromised: a new key is generated", order.id, src_id)
            if cert_key is not None:
                return cert_key, self._build_csr_b64(cert_key, domains, primary_domain), False, None
        # First issuance of a reuse order, or a key that must not be certified again
        cert_key, key_error = self._generate_cert_key(order)
        if key_error:
            return None, None, False, key_error
        return cert_key, self._build_csr_b64(cert_key, domains, primary_domain), True, None

    @staticmethod
    def _keep_before_request(lease) -> bool:
        """Commit what the finalize request depends on; False when ``lease`` was lost."""
        if lease is not None:
            return lease.refresh()
        db.session.commit()
        return True

    def finalize_order(self, order: AcmeClientOrder, *, renews: Optional[AcmeClientOrder] = None,
                       lease=None) -> Tuple[bool, str, Optional[int]]:
        """Finalize ``order``, download its certificate and import it: ``(success, message, certificate_id)``.

        First issuance (``renews`` None): the certificate goes into a new row, which ``order``
        then names. Renewal: ``order`` is the one the renewal opened and ``renews`` the order
        it renews. The certificate is written into the row ``renews`` names, which keeps its
        id and refid (a new row only when that one is gone or revoked); ``renews`` takes over
        the order and certificate URLs and ``order`` is deleted, in one commit, then
        certificate.renewed is emitted.

        A key generated here is stored on the order and committed before the finalize
        request, and removed with the import. An order the CA already took (processing or
        valid) is resumed with that key, the external CSR (key_source csr) or the key of the
        source certificate (reuse). ``lease`` is refreshed before the request and before the
        import: once lost, this finalization stops and leaves the order to its new holder.
        """
        try:
            status, data = self.check_order_status(order)
            domains = order.domains_list
            primary_domain = domains[0]

            if status in ('processing', 'valid'):
                if not data:  # the CA did not answer
                    return False, f"Order not ready for finalization (status: {status})", None
                key_pem, key_error = self.held_finalize_key(order)
                if key_error:
                    return False, key_error, None
                order_data = data
            elif status != 'ready':
                return False, f"Order not ready for finalization (status: {status})", None
            else:
                cert_key, csr_b64, keep, key_error = self._finalize_key(order, domains, primary_domain)
                if key_error:
                    return False, key_error, None
                key_pem = cert_key.private_bytes(
                    encoding=Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ).decode() if cert_key is not None else None
                if keep:
                    order.pending_key = key_pem
                if not self._keep_before_request(lease):
                    return False, LEASE_LOST, None

                resp = self._post(order.finalize_url, {"csr": csr_b64})
                if resp.status_code not in [200, 201]:
                    error = resp.json()
                    return False, f"Finalization failed: {error.get('detail', 'Unknown error')}", None
                order_data = resp.json()
                self.write_order_status(order, order_data.get('status', 'processing'))
                db.session.commit()
                if not order_data.get('certificate'):
                    self._note_retry_after(resp)

            if not order_data.get('certificate'):
                deadline, interval = self._order_poll_limits()
                while not order_data.get('certificate'):
                    if not self._sleep_before_next_poll(deadline, interval):
                        return False, "Certificate not ready after polling", None
                    status, order_data = self.check_order_status(order)
                    if status == 'invalid':
                        return False, "Order became invalid during finalization", None

            if lease is not None and not lease.refresh():
                return False, LEASE_LOST, None

            cert_url = order_data['certificate']
            cert_resp = self._post(cert_url, "")
            if cert_resp.status_code != 200:
                message = "Failed to download certificate"
                self._record_finalize_failure(order, message)
                return False, message, None
            cert_pem = self._select_certificate_chain(cert_resp)

            if renews is not None:
                return self._complete_renewal(order, renews, cert_pem, key_pem, cert_url)

            cert_id = self._import_certificate(
                cert_pem=cert_pem,
                key_pem=key_pem,
                domains=domains,
                source='acme_client'
            )
            if not cert_id:
                message = "Certificate obtained but import failed"
                self._record_finalize_failure(order, message)
                return False, message, None

            order.certificate_id = cert_id
            order.certificate_url = cert_url
            order.status = 'issued'
            order.error_message = None
            order.pending_key = None
            # RFC 8555 §7.1.3: order.expires is the order resource's expiry, not the
            # certificate's; the scheduler compares expires_at with its threshold (issue #74).
            not_after = self._not_after(cert_pem, order)
            if not_after is not None:
                order.expires_at = not_after
            db.session.commit()

            logger.info(f"Certificate issued for {domains}, ID: {cert_id}, expires_at={order.expires_at}")
            return True, "Certificate issued and imported successfully", cert_id

        except Exception as e:
            logger.error(f"Finalization error: {e}")
            # A database error's text carries the statement and its values
            message = 'Database error during finalization' if isinstance(e, SQLAlchemyError) else str(e)
            self._record_finalize_failure(order, message)
            return False, message, None

    @staticmethod
    def _not_after(cert_pem: str, order) -> Optional[datetime]:
        """The leaf's notAfter, naive UTC; None when it cannot be read."""
        try:
            from services.acme.client_certificates import load_leaf
            return load_leaf(cert_pem).not_valid_after_utc.replace(tzinfo=None)
        except Exception as parse_err:
            logger.warning(f"Could not parse cert notAfter for order {order.id}: {parse_err}")
            return None

    def _complete_renewal(self, order, renews, cert_pem, key_pem, cert_url):
        """The renewal half of finalize_order: certificate written, ``renews`` updated and
        ``order`` deleted in one commit."""
        from services.acme import client_certificates

        row = db.session.get(Certificate, renews.certificate_id) if renews.certificate_id else None
        in_place = row is not None and bool(row.crt) and not row.revoked
        old_serial = row.serial_number if in_place else None
        from utils.datetime_utils import utc_now
        now = utc_now()
        if in_place:
            try:
                client_certificates.write_renewed(row, cert_pem, key_pem, now)
            except ValueError as exc:
                db.session.rollback()
                self._record_finalize_failure(order, str(exc))
                return False, str(exc), None
            cert_id = row.id
        else:
            # Gone or revoked: a revoked row keeps its revocation, the certificate gets a new one
            cert_id = self._import_certificate(cert_pem=cert_pem, key_pem=key_pem,
                                               domains=order.domains_list, source='acme_client')
            if not cert_id:
                message = "Certificate obtained but import failed"
                self._record_finalize_failure(order, message)
                return False, message, None

        renews.certificate_id = cert_id
        renews.order_url = order.order_url
        renews.certificate_url = cert_url
        # Renewed from whatever status: the order that fetched the certificate has nothing
        # of its own left and goes, or it would renew these names again
        renews.status = 'issued'
        renews.last_renewal_at = now
        renews.renewal_failures = 0
        renews.error_message = None
        renews.last_error_at = None
        not_after = self._not_after(cert_pem, order)
        if not_after is not None:
            renews.expires_at = not_after
        db.session.delete(order)
        try:
            db.session.commit()
        except SQLAlchemyError as exc:
            logger.error(f"Renewed certificate not saved: {exc}")
            self._record_finalize_failure(order, 'Database error during finalization')
            return False, 'Database error during finalization', None

        if in_place:
            client_certificates.after_renewal_commit(row, cert_pem, key_pem, old_serial)
        logger.info(f"Certificate renewed for {renews.domains_list}, ID: {cert_id}")
        return True, "Certificate renewed and imported successfully", cert_id

    @staticmethod
    def _record_finalize_failure(order, message: str) -> None:
        """Keep the failure on the order; a failed flush refuses every statement until rollback.

        What the CA last said outlives a failure here: only a valid order can be renewed.
        """
        try:
            db.session.rollback()
            values = {'error_message': message}
            if order.status not in ('valid', 'invalid'):
                values['status'] = 'error'
            # A failure that lost to an import is no longer the order's
            AcmeClientOrder.query.filter(
                AcmeClientOrder.id == order.id, AcmeClientOrder.status != 'issued',
            ).update(values, synchronize_session=False)
            db.session.commit()
        except Exception as commit_err:
            db.session.rollback()
            logger.error(f"Failed to save order error state: {commit_err}")

    def _import_certificate(
        self, 
        cert_pem: str, 
        key_pem: str, 
        domains: List[str],
        source: str = 'acme_client'
    ) -> Optional[int]:
        """Import a certificate the CA issued into a new row; its id, None on failure.

        The chain goes with the end-entity certificate. A row of the same ``source`` already
        holding this certificate is returned as it is: a resumed finalization may follow an
        import whose order update was never saved.
        """
        try:
            from services.cert_service import CertificateService
            from services.acme.client_certificates import check_key, load_leaf, split_chain

            end_entity_pem, chain_pem = split_chain(cert_pem)
            if end_entity_pem is None:
                logger.error("No PEM certificates found in ACME response")
                return None
            leaf = load_leaf(cert_pem)
            check_key(leaf, key_pem)
            existing = Certificate.query.filter_by(
                serial_number=str(leaf.serial_number), issuer=leaf.issuer.rfc4514_string(),
                source=source).first()
            if existing is not None:
                return existing.id

            cert_record = CertificateService.import_certificate(
                descr=domains[0],
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
    
    @staticmethod
    def _get_default_key_type() -> str:
        """The certificate key type setting, RSA-2048 when unset; ValueError when this
        instance cannot generate the configured type, FIPS mode included (never another
        type in its place)."""
        cfg = SystemConfig.query.filter_by(key='acme.client.key_type').first()
        kt = (cfg.value or '').strip() if cfg else ''
        if not kt:
            return 'RSA-2048'
        if kt not in CERT_KEY_TYPES:
            raise ValueError(f'Configured ACME certificate key type {kt} is not supported here '
                             f'(one of {", ".join(CERT_KEY_TYPES)})')
        refusal = fips_key_type_refusal(kt)
        if refusal:
            raise ValueError(refusal)
        return kt

    def _generate_cert_key(self, order):
        """A new key of the order's type: ``(key, None)``, or ``(None, error)`` when unsupported."""
        try:
            key_type = getattr(order, 'key_type', None) or self._get_default_key_type()
        except ValueError as exc:
            return None, str(exc)
        generator = CERT_KEY_TYPES.get(key_type)
        if generator is None:
            return None, f'Unsupported certificate key type on order: {key_type}'
        refusal = fips_key_type_refusal(key_type)
        if refusal:
            return None, refusal
        return generator(), None

    @staticmethod
    def _build_csr_b64(cert_key, domains: List[str], primary_domain: str) -> str:
        """Build a CSR for the given domains and return base64url DER."""
        # Curve-matched digest for EC, SHA-256 for RSA, none for Ed25519/Ed448.
        requested = None
        if isinstance(cert_key, ec.EllipticCurvePrivateKey):
            requested = HASH_BY_NAME[default_digest_for_key_type(cert_key.curve.name)]()
        hash_alg = signing_hash_for(cert_key, requested)

        # A CN holds 64 characters (RFC 5280), a DNS name 253: the SAN carries the names anyway
        has_cn = len(primary_domain) <= 64
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, primary_domain)] if has_cn else [])
        san_list = []
        for identifier in domains:
            normalized_ip = normalize_ip_for_identifier(identifier)
            if normalized_ip is not None:
                san_list.append(x509.IPAddress(ipaddress.ip_address(normalized_ip)))
            else:
                san_list.append(x509.DNSName(identifier))
        csr = x509.CertificateSigningRequestBuilder().subject_name(
            subject
        ).add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=not has_cn,
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
        
        dns_provider_model = db.session.get(DnsProvider, order.dns_provider_id)
        if not dns_provider_model or dns_provider_model.provider_type == 'manual':
            return True, "Manual cleanup required"
        
        try:
            credentials = json.loads(dns_provider_model.credentials) if dns_provider_model.credentials else {}
            provider = create_provider(dns_provider_model.provider_type, credentials)
            
            challenges = order.challenges_dict
            for domain, challenge in challenges.items():
                with txt_record_lock(challenge['dns_txt_name']):
                    provider.delete_txt_record(
                        domain=strip_wildcard(domain),
                        record_name=challenge['dns_txt_name']
                    )
            
            return True, "DNS records cleaned up"
            
        except Exception as e:
            logger.warning(f"DNS cleanup error: {e}")
            return False, str(e)
