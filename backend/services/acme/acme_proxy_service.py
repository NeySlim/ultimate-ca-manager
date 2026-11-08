"""
ACME Proxy Service
Acts as a gateway between internal ACME clients and upstream ACME providers (Let's Encrypt)
"""
import base64
import copy
import json
import logging
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, Union
from urllib.parse import urlsplit

import requests

from flask import current_app
from sqlalchemy import and_, or_, inspect as sa_inspect
from sqlalchemy.exc import NoInspectionAvailable
from utils.datetime_utils import utc_now
from utils.san_parse import strip_wildcard
from services.acme.dns_txt_lock import txt_record_lock as _txt_record_lock
from services.acme.single_txt_value import (apex_and_wildcard_refusal, holds_one_value, keep_for_another_order,
                                            txt_lock_name)

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding, utils as asym_utils
from cryptography.hazmat.backends import default_backend

from models import db, SystemConfig, DnsProvider
from security.encryption import encrypt_text, decrypt_text
from utils.datetime_utils import utc_isoformat
from services.acme.acme_client_service import AcmeClientService
from services.acme import outbound
from services.acme.link_header import link_values as _link_values
from services.acme.upstream_problem import UpstreamProblem, retry_after_of
from services.acme.acme_proxy_account import (
    resolve_proxy_account,
    legacy_upstream_directory_url,
)
from services.acme.dns_selfcheck import (
    acme_allow_loopback_upstream,
    dns_propagation_timeout,
    wait_for_txt,
)
from utils.acme_debug import acme_log
from utils import ssrf_protection

logger = logging.getLogger(__name__)

# How many parent paths of a challenge URL are compared with recorded authz URLs.
_CHALLENGE_PARENT_LEVELS = 2
# Bound on the certificate fallback scan, one signed upstream call per candidate.
_CERT_FALLBACK_SCAN_LIMIT = 25
# Seconds the TXT of a challenge already submitted outlives a local failure of its order:
# the upstream CA may still be reading it. The order lists it, flagged, until deleted; a
# restart during the wait leaves it published, and siblings stop counting it one delay later.
_SUBMITTED_RECORD_LINGER = 120
# The dns-01 threads of one order run in the worker that started them: one lock per
# order id (striped) orders their writes to the row, a row lock covers PostgreSQL too.
_ORDER_ROW_LOCKS = tuple(threading.RLock() for _ in range(64))
# Upstream authz reads for one challenge request the local cache cannot place:
# each costs a request on the shared upstream account.
_CHALLENGE_SCAN_LIMIT = 3


class ProxyDns01OnlyError(ValueError):
    """The ACME proxy deliberately supports DNS identifiers/DNS-01 only."""


class ProxySingleTxtValueError(ValueError):
    """The DNS provider cannot hold the values these identifiers need under one name."""


class ProxyResourceNotFoundError(LookupError):
    """No local proxy order tracks the requested upstream resource."""


class ProxyAuthzStateError(ValueError):
    """The authorization's status does not allow the request (RFC 8555 §7.5.2)."""


class ProxyOrderNotReadyError(ValueError):
    """The order cannot be finalized: one of its authorizations was deactivated."""


class ProxyInvalidProfileError(ValueError):
    """The requested profile is not one the upstream directory offers."""


class ProxyBadCsrError(ValueError):
    """The CSR does not name exactly the identifiers of the order (RFC 8555 §7.4)."""


def _dns01_txt_value(key_authorization: str) -> str:
    """RFC 8555 section 8.4: TXT value = b64url(SHA-256(key authorization))."""
    import base64
    import hashlib
    digest = hashlib.sha256(key_authorization.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode()


def _dns_rows_hook(action, *args):
    """Run a DNS UPDATE expected-value hook (``records.<action>``). The rows
    are a side channel: a failure is logged and never changes the outcome of
    the proxy request."""
    try:
        from services.acme.dns_update import records
        return getattr(records, action)(*args)
    except Exception as exc:
        logger.warning("[ACME Proxy] DNS UPDATE hook %s failed: %s",
                       action, type(exc).__name__)
        return None


# What the client reads on an order or challenge whose TXT record the DNS provider refused
_DNS_REFUSED_PROBLEM = {
    'type': 'urn:ietf:params:acme:error:serverInternal',
    'detail': 'The proxy could not publish a dns-01 TXT record of this order: the DNS provider refused it',
}


def _problem_text(problem):
    """Detail of a problem document, else its type: RFC 7807 makes detail optional."""
    return (problem or {}).get('detail') or (problem or {}).get('type') or 'upstream error'


def _txt_written(provider, zone, record_name, value):
    """(ok, message) of a TXT write; an exception is a refusal like a False result."""
    try:
        result = provider.create_txt_record(zone, record_name, value)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if isinstance(result, tuple) and result:
        return bool(result[0]), str(result[1]) if len(result) > 1 else ''
    return bool(result), ''


def _same_instant(requested, upstream_value) -> bool:
    """True when no date was requested or the upstream RFC 3339 date is that instant."""
    if requested is None:
        return True
    try:
        upstream = datetime.fromisoformat(str(upstream_value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return False
    upstream, requested = (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
                           for dt in (upstream, requested))
    return upstream == requested


def _dns_failed_state(status) -> bool:
    """True for an RFC 8555 final state in which validation failed."""
    from services.acme.dns_update.records import is_failed_state
    return is_failed_state(status)


class ProxyChallengeIdentifierError(RuntimeError):
    """The identifier a challenge validates could not be determined, so no
    DNS record may be written for it."""


class _TtlCache:
    """Thread-safe process cache with a per-entry lifetime and a size bound.

    Entries are a shortcut only: a miss always falls back to the source."""

    def __init__(self, ttl_seconds: float, max_entries: int):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._lock = threading.Lock()
        self._entries: Dict[Any, Tuple[float, Any]] = {}

    def get(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= time.monotonic():
                del self._entries[key]
                return None
            return copy.deepcopy(value)

    def put(self, key, value) -> None:
        if key is None or value is None:
            return
        with self._lock:
            now = time.monotonic()
            self._entries.pop(key, None)
            if len(self._entries) >= self._max:
                for stale in [k for k, (exp, _v) in self._entries.items() if exp <= now]:
                    del self._entries[stale]
            while len(self._entries) >= self._max:
                # Dicts keep insertion order: the first key is the oldest entry.
                del self._entries[next(iter(self._entries))]
            self._entries[key] = (now + self._ttl, copy.deepcopy(value))

    def pop(self, key) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# Upstream directory, keyed by directory URL.
_directory_cache = _TtlCache(ttl_seconds=3600, max_entries=64)
# Upstream finalize URL, keyed by upstream order URL.
_finalize_url_cache = _TtlCache(ttl_seconds=24 * 3600, max_entries=4096)
# (order id, identifier, authz URL) keyed by _challenge_cache_key().
_challenge_order_cache = _TtlCache(ttl_seconds=24 * 3600, max_entries=8192)


def reset_proxy_caches():
    """Empty every proxy process cache and the upstream nonce pool."""
    for cache in (_directory_cache, _finalize_url_cache, _challenge_order_cache):
        cache.clear()
    outbound.reset_nonce_pool()


def _update_order_row(order, change):
    """Apply ``change(order)`` to the order row as stored now, commit, return its result.

    Each writer merges its own keys onto a fresh read: a copy read before another
    thread's commit would overwrite it."""
    try:
        db.session.commit()  # no transaction held while waiting for the lock
        with _ORDER_ROW_LOCKS[order.id % len(_ORDER_ROW_LOCKS)]:
            db.session.refresh(order, with_for_update=True)
            result = change(order)
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return result


def _owner_fields(order):
    """(account_id, thumbprint) recorded on an order, empty values as None."""
    return (getattr(order, 'account_id', None) or None,
            getattr(order, 'client_jwk_thumbprint', None) or None)


def _direct_owner_match(order, requester_account_id, requester_thumbprint) -> bool:
    owner_account_id, owner_thumbprint = _owner_fields(order)
    return bool(
        (owner_account_id and owner_account_id == requester_account_id)
        or (owner_thumbprint and owner_thumbprint == requester_thumbprint)
    )


def _reconciled_owner_match(order, requester_account_id, requester_thumbprint) -> bool:
    """Half-bound order: the AcmeAccount table links the recorded field to the
    requester's other field. Orders with both fields or none never reconcile."""
    from models import AcmeAccount

    owner_account_id, owner_thumbprint = _owner_fields(order)
    if bool(owner_account_id) == bool(owner_thumbprint):
        return False
    if owner_thumbprint and requester_account_id:
        account = AcmeAccount.query.filter_by(jwk_thumbprint=owner_thumbprint).first()
        return account is not None and account.account_id == requester_account_id
    if owner_account_id and requester_thumbprint:
        account = AcmeAccount.query.filter_by(jwk_thumbprint=requester_thumbprint).first()
        return account is not None and account.account_id == owner_account_id
    return False


def _normalized_identifier(value) -> str:
    """DNS identifier compared without wildcard prefix, root dot or case."""
    return strip_wildcard(value or '').strip().rstrip('.').lower()


def _order_covers_identifier(order, identifier) -> bool:
    wanted = _normalized_identifier(identifier)
    if not wanted:
        return False
    return any(_normalized_identifier(d) == wanted for d in order.domains_list or [])


def _csr_identifiers(csr):
    """(type, value) pairs a CSR requests: CN and SAN names, IPs apart (RFC 8555 §7.4, RFC 8738)."""
    import ipaddress
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from utils.csr_extensions import csr_extensions

    def _named(value):
        try:
            return 'ip', str(ipaddress.ip_address(value))
        except ValueError:
            return 'dns', value.strip().rstrip('.').lower()

    found = {_named(attr.value) for attr in csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
             if isinstance(attr.value, str)}
    try:
        san = csr_extensions(csr).get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        san = []
    except Exception as exc:  # DuplicateExtension, UnsupportedGeneralNameType: not ValueError
        raise ProxyBadCsrError(f'CSR extensions cannot be read: {exc}') from exc
    for name in san:
        if isinstance(name, x509.DNSName):
            found.add(_named(name.value))
        elif isinstance(name, x509.IPAddress):
            found.add(('ip', str(name.value)))
    return found


def _require_csr_matches_order(csr, order):
    """RFC 8555 §7.4: the CSR names exactly the order identifiers (wildcards kept)."""
    wanted = {('dns', d.strip().rstrip('.').lower())
              for d in order.domains_list or [] if isinstance(d, str)}
    requested = _csr_identifiers(csr)
    if requested != wanted:
        raise ProxyBadCsrError(
            f"CSR identifiers {sorted(v for _t, v in requested)} do not match "
            f"the order identifiers {sorted(v for _t, v in wanted)}")


def _single_domain(order) -> Optional[str]:
    """The identifier of a one-domain order (wildcard prefix removed), else None."""
    domains = order.domains_list or []
    if len(domains) == 1 and isinstance(domains[0], str) and domains[0]:
        return strip_wildcard(domains[0])
    return None


class AcmeProxyService:
    # Default upstream (Let's Encrypt Staging for safety by default, user can change)
    DEFAULT_UPSTREAM = "https://acme-staging-v02.api.letsencrypt.org/directory"
    # Production: https://acme-v02.api.letsencrypt.org/directory

    def __init__(self, base_url: str, account_id: int = None):
        self.base_url = base_url.rstrip('/')
        self._account_id = account_id
        self._account = None
        self._key_loaded = False
        self._private_key = None
        self._account_jwk = None
        self.verify_ssl = self._get_verify_ssl()
        self.directory = None
        # Retry-After of the last upstream order/authz read, relayed to the client (RFC 8555 §7.1.3)
        self.retry_after = None
        if not self.verify_ssl:
            logger.warning(
                "ACME proxy upstream SSL verification disabled by settings "
                "(acme.proxy.verify_ssl=false)."
            )
        # Resolve the upstream directory URL eagerly (cheap: config read or one
        # DB lookup). For an explicit account_id (slug routes) the row MUST
        # exist. For the legacy default route we fall back to the configured /
        # Let's Encrypt staging URL when no account is configured yet, so that
        # /directory and /new-nonce keep working on a fresh install (regression
        # v2.185: resolving the account in __init__ broke /directory with a 500
        # before any CA account was added).
        try:
            self.upstream_directory_url = self.account.directory_url
        except RuntimeError:
            if account_id is not None:
                raise  # explicit/slug request must reference a real account
            self.upstream_directory_url = legacy_upstream_directory_url()
        # Lazy-load account URL — don't register in constructor
        # This prevents /directory from failing when upstream is unreachable
        self._account_url = None

    @property
    def account(self):
        """Linked AcmeClientAccount, resolved lazily.

        Resolved on first access so that /directory and /new-nonce (which only
        need ``upstream_directory_url``) work even when no CA account is
        configured. Key-bearing operations (new-account, new-order, signing)
        trigger the resolution and will raise the helpful "No external ACME CA
        account configured" error if none exists.
        """
        if self._account is None:
            self._account = resolve_proxy_account(self._account_id)
        return self._account

    @account.setter
    def account(self, value):
        self._account = value

    @property
    def private_key(self):
        self._ensure_account_key()
        return self._private_key

    @private_key.setter
    def private_key(self, value):
        self._private_key = value

    @property
    def account_jwk(self):
        self._ensure_account_key()
        return self._account_jwk

    @account_jwk.setter
    def account_jwk(self, value):
        self._account_jwk = value

    def _ensure_account_key(self):
        """Load the upstream account private key on first use (requires the
        linked AcmeClientAccount to be configured)."""
        if self._key_loaded:
            return
        self._private_key, self._account_jwk = self._load_or_create_account_key()
        self._key_loaded = True

    @property
    def account_url(self):
        """Lazy-load account URL — only register when actually needed"""
        if self._account_url is None:
            self._account_url = self._get_upstream_account_url()
        return self._account_url

    @account_url.setter
    def account_url(self, value):
        self._account_url = value

    def _decode_proxy_id(self, id_b64: str) -> str:
        """Decode a client-supplied proxy ID (base64url of upstream URL) and
        validate that the URL targets the configured upstream ACME host.

        This prevents SSRF / credential-relay attacks where a malicious client
        crafts an ID that decodes to an arbitrary URL — `_post_with_account`
        would otherwise sign a JWS with the upstream account key and POST it
        to that URL, leaking credentials.
        """
        from urllib.parse import urlparse
        try:
            id_b64_padded = id_b64 + '=' * (-len(id_b64) % 4)
            url = base64.urlsafe_b64decode(id_b64_padded).decode('utf-8', errors='strict')
        except Exception:
            raise ValueError("Invalid proxy ID encoding")
        parsed = urlparse(url)
        if parsed.scheme not in ('https',):
            raise ValueError("Proxy ID does not target https")
        upstream_host = urlparse(self.upstream_directory_url).hostname
        if not upstream_host or parsed.hostname != upstream_host:
            logger.warning(
                "ACME proxy: rejected ID with foreign host %s (expected %s)",
                parsed.hostname, upstream_host
            )
            raise ValueError("Proxy ID host does not match upstream ACME server")
        return url

    @staticmethod
    def _proxy_id(url: str) -> str:
        """Proxy ID of an upstream URL: unpadded base64url of its UTF-8 bytes,
        the exact inverse of _decode_proxy_id."""
        return base64.urlsafe_b64encode(url.encode('utf-8')).rstrip(b'=').decode('ascii')

    _strip_wildcard = staticmethod(strip_wildcard)

    @staticmethod
    def _get_verify_ssl() -> bool:
        """Get proxy upstream TLS verification setting (default: True)."""
        cfg = SystemConfig.query.filter_by(key='acme.proxy.verify_ssl').first()
        if not cfg or cfg.value is None:
            return True
        parsed = str(cfg.value).strip().lower()
        if parsed in ('true', '1', 'yes', 'on'):
            return True
        if parsed in ('false', '0', 'no', 'off'):
            return False
        logger.warning(
            "Invalid acme.proxy.verify_ssl value '%s'; falling back to secure default (True).",
            cfg.value
        )
        return True

    @staticmethod
    def _prune_replaced_certificates_enabled() -> bool:
        """Opt-in purge of superseded proxy-imported certificates (#240).

        Default: disabled — proxy-issued certificates are inventoried forever
        unless the operator opts in.
        """
        cfg = SystemConfig.query.filter_by(
            key='acme.proxy.prune_replaced_certificates').first()
        if not cfg or cfg.value is None:
            return False
        parsed = str(cfg.value).strip().lower()
        if parsed in ('true', '1', 'yes', 'on'):
            return True
        if parsed in ('false', '0', 'no', 'off'):
            return False
        logger.warning(
            "Invalid acme.proxy.prune_replaced_certificates value '%s'; "
            "falling back to disabled.", cfg.value
        )
        return False

    def _prune_replaced_certificates(self, order, new_certificate_id: int) -> int:
        """Delete proxy-imported certificates superseded by this renewal (#240).

        Opt-in via ``acme.proxy.prune_replaced_certificates``. Only certificates
        imported through an *older proxy order with the exact same domain set*
        (``source='acme_client'``) are removed; revoked certificates are always
        kept (inventory/revocation history), and certificates not issued through
        the proxy are never touched. Best-effort: never raises, failures are
        logged.
        """
        if not self._prune_replaced_certificates_enabled():
            return 0

        from models import AcmeClientOrder, Certificate
        from services.cert_service import CertificateService

        old_orders = AcmeClientOrder.query.filter(
            AcmeClientOrder.is_proxy_order.is_(True),
            AcmeClientOrder.domains == order.domains,
            AcmeClientOrder.id != order.id,
            AcmeClientOrder.certificate_id.isnot(None),
        ).all()

        pruned = 0
        for old_order in old_orders:
            cert = db.session.get(Certificate, old_order.certificate_id)
            if cert is None or cert.id == new_certificate_id:
                continue
            if cert.revoked or cert.source != 'acme_client':
                # Revoked: keep for CRL/history. Non-proxy origin: never touch.
                continue
            # Detach every order still pointing at this certificate (FK safety)
            for ref in AcmeClientOrder.query.filter_by(certificate_id=cert.id).all():
                ref.certificate_id = None
            try:
                db.session.flush()
            except Exception as e:
                db.session.rollback()
                logger.error(
                    f"[ACME Proxy] Prune: failed to detach orders from "
                    f"certificate {cert.id}: {e}"
                )
                continue
            if CertificateService.delete_certificate(cert.id, username='acme_proxy'):
                pruned += 1
            else:
                logger.error(
                    f"[ACME Proxy] Prune: failed to delete certificate {cert.id}"
                )
        if pruned:
            logger.info(
                "[ACME Proxy] Pruned %d superseded certificate(s) for domains %s",
                pruned, order.domains,
            )
        return pruned

    def _load_or_create_account_key(self):
        """Load upstream account private key from the linked AcmeClientAccount."""
        from services.acme.acme_client_service import AcmeClientService

        client = AcmeClientService(account=self.account)
        private_key = client._get_account_key()
        jwk_dict = client._build_jwk(private_key)
        return private_key, jwk_dict

    def _detect_key_algorithm(self) -> str:
        from services.acme.acme_client_service import AcmeClientService
        return AcmeClientService(account=self.account)._detect_key_algorithm(self.private_key)

    def _sign_data(self, data: bytes) -> bytes:
        from services.acme.acme_client_service import AcmeClientService
        return AcmeClientService(account=self.account)._sign_data(self.private_key, data)

    def _jwk_thumbprint(self) -> str:
        from services.acme.acme_client_service import AcmeClientService
        return AcmeClientService(account=self.account)._jwk_thumbprint(self.private_key)

    def _get_upstream_account_url(self):
        """Get or register account URL on the linked AcmeClientAccount row."""
        if self.account.account_url:
            return self.account.account_url
        return self._register_upstream_account()

    @staticmethod
    def _is_public_email_domain(email: str) -> bool:
        """Best-effort check: reject obviously non-public TLDs that will be rejected by
        Let's Encrypt's Public Suffix List check. Not a full PSL — rejects common
        internal/dev TLDs. Real PSL validation happens upstream anyway."""
        if not email or '@' not in email:
            return False
        domain = email.rsplit('@', 1)[-1].strip().lower()
        if '.' not in domain:
            return False
        private_tlds = {'local', 'lan', 'home', 'internal', 'intranet',
                        'corp', 'localdomain', 'localhost', 'example', 'test',
                        'invalid', 'onion'}
        tld = domain.rsplit('.', 1)[-1]
        return tld not in private_tlds

    def _resolve_contact_email(self) -> Optional[str]:
        """Resolve the contact email to use for upstream account registration.
        Priority:
          1. Email on the linked AcmeClientAccount row
          2. Legacy acme.proxy_email (validated)
          3. None — caller must handle (LE accepts registration without contact)
        """
        if self.account.email:
            email = self.account.email.strip()
            if self._is_public_email_domain(email):
                return email
            logger.warning(
                "Account email '%s' has non-public TLD; trying legacy proxy_email.",
                email,
            )
        cfg = SystemConfig.query.filter_by(key='acme.proxy_email').first()
        if cfg and cfg.value:
            email = cfg.value.strip()
            if self._is_public_email_domain(email):
                return email
            logger.warning(
                "Configured acme.proxy_email '%s' has non-public TLD; "
                "registering without contact email.", email
            )
        return None

    def _register_upstream_account(self):
        """Register the linked AcmeClientAccount with the upstream CA."""
        from services.acme.acme_client_service import AcmeClientService

        contact_email = self._resolve_contact_email()
        if not contact_email:
            # RFC 8555 makes `contact` optional and Let's Encrypt accepts
            # contact-less registrations — don't block issuance when the only
            # available email has a non-public TLD (.lan/.local).
            logger.warning(
                "No public contact email available for the proxy upstream "
                "account; registering without a contact."
            )

        client = AcmeClientService(account=self.account)
        success, message, account_url = client.register_account(contact_email)
        if not success:
            raise RuntimeError(message)

        self._account_url = account_url
        return account_url

    @staticmethod
    def _validate_outbound_acme_url(url: str) -> None:
        """Block loopback/cloud-metadata targets for upstream ACME sub-URLs.

        Loopback is allowed only when the operator opts in for a colocated
        upstream (see acme_allow_loopback_upstream); metadata stays blocked."""
        outbound.validate_outbound_acme_url(url)

    def _http_timeout(self) -> int:
        """The configured upstream HTTP timeout, without demanding an account.

        ``self.account`` resolves lazily and raises when no CA account is
        configured, and /directory and /new-nonce answer without one — so this
        reads the already-resolved account and falls back to the default
        rather than forcing the resolution and turning those into a 500.
        """
        from models.acme_client_account import AcmeClientAccount
        account = self._account
        if account is not None:
            return account.get_http_timeout_sec()
        return AcmeClientAccount.DEFAULT_HTTP_TIMEOUT_SEC

    def _ensure_directory(self):
        """Fetch upstream directory, through the process cache."""
        if not self.directory:
            cached = _directory_cache.get(self.upstream_directory_url)
            if cached:
                self.directory = cached
                return
            self._validate_outbound_acme_url(self.upstream_directory_url)
            try:
                resp = ssrf_protection.safe_request_get(
                    self.upstream_directory_url,
                    allow_loopback=acme_allow_loopback_upstream(),
                    timeout=self._http_timeout(),
                    verify=self.verify_ssl,
                    headers={'User-Agent': outbound.USER_AGENT},
                )
                resp.raise_for_status()
                self.directory = resp.json()
                if isinstance(self.directory, dict):
                    _directory_cache.put(self.upstream_directory_url, self.directory)
            except requests.exceptions.ConnectionError as e:
                raise RuntimeError(
                    f"Cannot connect to upstream ACME server at {self.upstream_directory_url}: {e}"
                )
            except requests.exceptions.Timeout:
                raise RuntimeError(
                    f"Timeout connecting to upstream ACME server at {self.upstream_directory_url}"
                )
            except requests.exceptions.HTTPError as e:
                raise RuntimeError(
                    f"Upstream ACME server returned error: {e.response.status_code} {e.response.reason}"
                )

    def _get_nonce(self):
        """Upstream nonce: a pooled one first, a fresh one otherwise."""
        self._ensure_directory()
        pooled = outbound.nonce_pool_pop(self.upstream_directory_url)
        if pooled:
            return pooled
        return outbound.fetch_nonce(
            self.directory['newNonce'],
            timeout=self._http_timeout(),
            verify=self.verify_ssl,
            headers={'User-Agent': outbound.USER_AGENT},
        )

    def _sign_and_post(self, url: str, payload, nonce: str, kid: str = None) -> requests.Response:
        """Build a JWS with the given nonce and POST it once."""
        alg = self._detect_key_algorithm()
        if kid:
            protected = {"alg": alg, "kid": kid, "nonce": nonce, "url": url}
        else:
            protected = {"alg": alg, "jwk": self.account_jwk, "nonce": nonce, "url": url}

        if payload == "":
            payload_json = b""
        else:
            payload_json = json.dumps(payload).encode('utf-8')

        protected_json = json.dumps(protected).encode('utf-8')

        payload_b64 = base64.urlsafe_b64encode(payload_json).rstrip(b'=').decode('utf-8')
        protected_b64 = base64.urlsafe_b64encode(protected_json).rstrip(b'=').decode('utf-8')

        signing_input = f"{protected_b64}.{payload_b64}".encode('utf-8')
        sig = self._sign_data(signing_input)

        data = {
            "protected": protected_b64,
            "payload": payload_b64,
            "signature": base64.urlsafe_b64encode(sig).rstrip(b'=').decode('utf-8')
        }

        headers = {"Content-Type": "application/jose+json", "User-Agent": outbound.USER_AGENT}
        self._validate_outbound_acme_url(url)
        resp = ssrf_protection.safe_request_post(
            url,
            allow_loopback=acme_allow_loopback_upstream(),
            json=data,
            headers=headers,
            timeout=self._http_timeout(),
            verify=self.verify_ssl
        )
        # A 400 keeps its nonce: _post_jws spends it on the badNonce retry.
        if resp.status_code != 400:
            fresh_nonce = (getattr(resp, 'headers', None) or {}).get('Replay-Nonce')
            if fresh_nonce:
                outbound.nonce_pool_push(self.upstream_directory_url, fresh_nonce)
        return resp

    def _post_jws(self, url: str, payload: Union[Dict, str], kid: str = None) -> requests.Response:
        """Sign and post JWS to upstream, with automatic badNonce retry (RFC 8555 §6.5).

        Some upstream CAs (Pebble, HARICA, strict implementations) reject
        nonces that LE staging would accept. On badNonce, the server MUST
        return a fresh nonce in Replay-Nonce and the client SHOULD retry.
        """
        return outbound.post_with_bad_nonce_retries(
            lambda nonce: self._sign_and_post(url, payload, nonce, kid=kid), url, self._get_nonce())

    def _post_with_account(self, url: str, payload) -> requests.Response:
        """Post JWS with account KID, auto-re-registering if account is stale.

        Upstream CAs (especially LE staging) may invalidate accounts.
        This detects 401/403 "Account is not valid" and re-registers automatically.
        """
        resp = self._post_jws(url, payload, kid=self.account_url)

        if resp.status_code in [401, 403]:
            try:
                error_data = resp.json()
                detail = error_data.get('detail', '')
                if 'not valid' in detail.lower() or 'deactivated' in detail.lower():
                    logger.warning(f"Upstream account invalid ({detail}), re-registering...")

                    # Clear stale account URL on the linked row
                    self.account.account_url = None
                    self._account_url = None
                    try:
                        db.session.commit()
                    except Exception as e:
                        db.session.rollback()
                        logger.error(f"Failed to clear stale account URL: {e}")
                        return resp

                    # Re-register with upstream
                    self.account_url = self._register_upstream_account()
                    logger.info(f"Re-registered upstream account: {self.account_url}")

                    # Retry original request with new account
                    resp = self._post_jws(url, payload, kid=self.account_url)
            except (json.JSONDecodeError, KeyError):
                pass
            except Exception as e:
                logger.error(f"Account re-registration failed: {e}")

        return resp

    # --- Proxy Methods ---

    def revoke_certificate(self, certificate, reason: int = 0) -> requests.Response:
        """Revoke a proxy-issued certificate with the linked upstream account."""
        client = AcmeClientService(account=self.account)
        if self.directory is not None:
            client.directory = self.directory
        return client.revoke_certificate(certificate, reason)

    def get_directory(self):
        """Return proxy directory.

        Override upstream meta.externalAccountRequired with local UCM EAB
        policy so clients (win-acme, certbot, acme.sh) know they MUST send
        an externalAccountBinding when registering against this proxy.
        Issue #112: previously the proxy passed upstream's meta as-is, which
        for Let's Encrypt does not require EAB, so clients sent registrations
        without EAB and were accepted.
        """
        from models import SystemConfig
        self._ensure_directory()
        meta = dict(self.directory.get('meta', {}))
        eab_cfg = SystemConfig.query.filter_by(key='acme_eab_required').first()
        eab_required = (eab_cfg.value if eab_cfg else 'false').lower() == 'true'
        meta['externalAccountRequired'] = eab_required
        directory = {
            "newNonce": f"{self.base_url}/new-nonce",
            "newAccount": f"{self.base_url}/new-account",
            "newOrder": f"{self.base_url}/new-order",
            "revokeCert": f"{self.base_url}/revoke-cert",
            # No keyChange: the proxy refuses key rollover (501), so it is not advertised
            "meta": meta,
        }
        # Advertise ARI (RFC 9773) when the upstream does. Served locally
        # from the UCM database — proxy-issued certs are stored on import,
        # so no upstream round-trip and no upstream host leak.
        #
        # RFC 9773 §3/§4.1: the directory entry is the BASE URL; clients
        # append "/<certID>" to form the full request URL. Publishing the
        # literal "<certID>" placeholder here would double the path segment.
        if 'renewalInfo' in self.directory:
            directory['renewalInfo'] = f"{self.base_url}/renewal-info"
        return directory

    def new_nonce(self):
        """Proxy new-nonce"""
        self._ensure_directory()
        # Just return a local nonce or fetch upstream?
        # ACME clients expect a nonce they can use for the next request.
        # But the next request will go to US. So we should issue OUR nonce.
        # And when we forward to upstream, we fetch an UPSTREAM nonce.
        # So: Standard local nonce logic.
        from services.acme import AcmeService
        svc = AcmeService(self.base_url)
        return svc.generate_nonce()

    def new_order(
        self,
        identifiers,
        not_before=None,
        not_after=None,
        client_thumbprint=None,
        replaces=None,
        profile=None,
    ):
        """Proxy new-order with domain validation and RFC 9773 replacement."""
        from api.v2.acme_domains import find_provider_for_domain
        from models import AcmeClientOrder
        from services.acme.dns_providers import get_provider_class

        if not identifiers:
            raise ValueError("identifiers must be a non-empty list")

        self._ensure_directory()
        # ACME profiles: only a profile the upstream directory offers is passed on
        if profile is not None:
            offered = (self.directory.get('meta') or {}).get('profiles')
            if not isinstance(profile, str) or not isinstance(offered, dict) or profile not in offered:
                raise ProxyInvalidProfileError(
                    'The requested certificate profile is not offered by the upstream CA')

        # The proxy performs validation itself through configured DNS providers.
        # Never forward IP identifiers: RFC 8738 requires HTTP-01/TLS-ALPN-01,
        # neither of which can be fulfilled by this DNS-01-only gateway.
        domains = []
        for ident in identifiers:
            if not isinstance(ident, dict) or not ident.get('value'):
                raise ValueError('Each identifier must contain type and value')
            if ident.get('type') != 'dns':
                raise ProxyDns01OnlyError(
                    'The ACME proxy supports DNS identifiers with dns-01 only; '
                    'IP identifiers are not supported.'
                )
            domains.append(ident['value'])

        # Verify each domain has a DNS provider configured
        domain_providers = {}
        for domain in domains:
            # Remove wildcard prefix for lookup (removeprefix not lstrip — chars vs prefix)
            lookup_domain = strip_wildcard(domain)
            provider = find_provider_for_domain(lookup_domain)
            if not provider:
                raise Exception(f"No DNS provider configured for domain: {domain}. Configure it in ACME > Domains.")
            domain_providers[domain] = provider

        # Refused before upstream opens the order: the CA would see one value and fail the other
        served = {}
        for domain, info in domain_providers.items():
            model = info['provider']
            served.setdefault((getattr(model, 'id', None), getattr(model, 'provider_type', None)), []).append(domain)
        for (_provider_id, provider_type), served_domains in served.items():
            refusal = apex_and_wildcard_refusal(served_domains, get_provider_class(provider_type))
            if refusal:
                raise ProxySingleTxtValueError(refusal)

        # Same-account dedupe (#303 minor 4): a client that retries new-order
        # for the same identifiers (Traefik does) must get its still-pending
        # order back, like upstream CAs do, instead of opening a new upstream
        # order every time. Cross-account sharing is #310's job — the match is
        # strictly on this requester's own orders.
        forwarded_replaces = replaces if self.directory.get('renewalInfo') else None
        existing = self._find_reusable_pending_order(
            domains, client_thumbprint, profile, not_before=not_before,
            not_after=not_after, replaces=forwarded_replaces)
        if existing is not None:
            return existing

        # Forward to upstream Let's Encrypt
        payload = {
            "identifiers": identifiers,
            "notBefore": utc_isoformat(not_before),
            "notAfter": utc_isoformat(not_after),
            "profile": profile,
        }
        # Filter None and forward RFC 9773 `replaces` only when supported.
        payload = {k: v for k, v in payload.items() if v is not None}
        if forwarded_replaces:
            payload['replaces'] = forwarded_replaces

        resp = self._post_with_account(self.directory['newOrder'], payload)

        if resp.status_code != 201:
            raise UpstreamProblem.from_response(resp)

        upstream_order = resp.json()
        upstream_location = resp.headers['Location']

        # Get upstream authz URLs for later matching
        upstream_authz_urls = upstream_order.get('authorizations', [])

        # Resolve linked local AcmeAccount from the client JWK thumbprint.
        # The proxy's /new-account handler already created (or upserted) an
        # AcmeAccount with this thumbprint, so the lookup should always hit
        # for compliant clients. If it misses, we leave account_id NULL —
        # the order still works, it just won't show in the account detail.
        linked_account_id = None
        if client_thumbprint:
            try:
                from models import AcmeAccount
                acct = AcmeAccount.query.filter_by(
                    jwk_thumbprint=client_thumbprint
                ).first()
                if acct is not None:
                    linked_account_id = acct.account_id
            except Exception as e:
                logger.warning(
                    "ACME proxy: failed to resolve local account for "
                    "thumbprint=%s: %s", client_thumbprint[:12] if client_thumbprint else None, e
                )

        # Store order in database for tracking
        order = AcmeClientOrder(
            domains=json.dumps(domains),
            environment='staging' if 'staging' in self.upstream_directory_url else 'production',
            challenge_type='dns-01',
            status='pending',
            order_url=upstream_location,
            upstream_order_url=upstream_location,
            upstream_authz_urls=json.dumps(upstream_authz_urls),
            is_proxy_order=True,
            client_jwk_thumbprint=client_thumbprint,
            account_id=linked_account_id,
            acme_client_account_id=self.account.id,
            # Use first domain's provider (provider dict contains 'provider' key with model)
            dns_provider_id=list(domain_providers.values())[0]['provider'].id if domain_providers else None
        )
        db.session.add(order)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to save ACME proxy order: {e}")
            raise

        _finalize_url_cache.put(upstream_location, upstream_order.get('finalize'))
        # Rewrite URLs in response to point to Proxy
        return self._rewrite_order_response(upstream_order, upstream_location, order)

    def _rewrite_order_response(self, upstream_order, upstream_location, local_order=None):
        """Rewrite upstream URLs (authorizations, finalize) to proxy URLs."""
        order_id = self._proxy_id(upstream_location)
        return self._rewrite_order_urls(
            upstream_order, upstream_location, order_id, local_order), order_id

    def _proxy_url(self, kind: str, upstream_url: str) -> str:
        """Proxy URL of an upstream resource of the given kind (authz, cert...)."""
        return f"{self.base_url}/{kind}/{self._proxy_id(upstream_url)}"

    def _rewrite_order_urls(self, order, upstream_order_url, order_id, local_order=None):
        """Point finalize, certificate and authorizations of an upstream order
        at the proxy; a certificate URL is persisted on the local order served."""
        order['finalize'] = f"{self.base_url}/order/{order_id}/finalize"
        if 'certificate' in order:
            if local_order is not None:
                self._persist_certificate_url(local_order, order['certificate'])
            order['certificate'] = self._proxy_url('cert', order['certificate'])
        if 'authorizations' in order:
            order['authorizations'] = [
                self._proxy_url('authz', url) for url in order['authorizations']]
        return order

    def _client_txt_values(self, order, key_authz, upstream_value,
                           authz_url=None):
        """dns-01 TXT values computed with the CLIENT thumbprints of every
        sibling order sharing the current upstream authz (#306/#307), so
        client-side propagation pre-checks can succeed. The upstream value is
        excluded; failures return an empty list (publishing the client values
        is best-effort)."""
        values = []
        try:
            token = key_authz.split('.', 1)[0]
            siblings = [order]
            urls = json.loads(order.upstream_authz_urls) if order.upstream_authz_urls else []
            current_authz_url = authz_url or (urls[0] if urls else None)
            if current_authz_url:
                siblings = self._orders_by_authz_url(current_authz_url) or [order]
            seen = set()
            for sibling in siblings:
                thumb = getattr(sibling, 'client_jwk_thumbprint', None)
                if not thumb or thumb in seen:
                    continue
                seen.add(thumb)
                value = _dns01_txt_value(f"{token}.{thumb}")
                if value != upstream_value:
                    values.append(value)
        except Exception as exc:
            logger.warning(f"Could not compute client TXT values: {exc}")
            return []
        return values

    def _find_reusable_pending_order(self, domains, client_thumbprint, profile=None,
                                     not_before=None, not_after=None, replaces=None):
        """Return the rewritten still-pending order of this requester for the
        exact same identifier set, or None (#303 minor 4).

        The upstream order is re-fetched to confirm it is still ``pending``;
        any doubt (fetch failure, other status, missing thumbprint) falls
        through to creating a fresh order."""
        from models import AcmeClientOrder

        if not client_thumbprint:
            return None
        wanted = sorted(domains)
        candidates = (AcmeClientOrder.query
                      .filter_by(is_proxy_order=True, status='pending',
                                 client_jwk_thumbprint=client_thumbprint)
                      .order_by(AcmeClientOrder.id.desc())
                      .limit(20).all())
        for order in list(candidates):
            if sorted(order.domains_list or []) != wanted:
                continue
            upstream_url = order.upstream_order_url or order.order_url
            if not upstream_url:
                continue
            try:
                resp = self._post_with_account(upstream_url, "")
                if resp.status_code != 200:
                    continue
                upstream_order = resp.json()
            except Exception as exc:
                logger.debug(f"Pending-order reuse: upstream fetch failed: {exc}")
                continue
            if upstream_order.get('status') != 'pending':
                continue
            if profile is not None and upstream_order.get('profile') != profile:
                continue
            # RFC 8555 §7.4: an order without the requested dates would not honour them
            if not (_same_instant(not_before, upstream_order.get('notBefore'))
                    and _same_instant(not_after, upstream_order.get('notAfter'))):
                continue
            # Servers echo replaces only when it was sent: a plain retry must not inherit one
            if (replaces or None) != (upstream_order.get('replaces') or None):
                continue
            logger.info(
                "[ACME Proxy] Reusing pending order %s for %s (same account, "
                "same identifiers)", order.id, ', '.join(wanted),
            )
            _finalize_url_cache.put(upstream_url, upstream_order.get('finalize'))
            return self._rewrite_order_response(upstream_order, upstream_url, order)
        return None

    @staticmethod
    def _require_owner(order, requester_account_id, requester_thumbprint,
                       resource='Order'):
        """Raise unless the requester owns this tracked proxy order.

        Unbound legacy rows stay open; a bound order needs a positive match,
        direct or reconciled through the AcmeAccount table."""
        if order is None or not getattr(order, 'is_proxy_order', False):
            raise ProxyResourceNotFoundError(f"{resource} not found")
        owner_account_id, owner_thumbprint = _owner_fields(order)
        if not owner_account_id and not owner_thumbprint:
            return
        if not (requester_account_id or requester_thumbprint):
            raise PermissionError(
                f"{resource} belongs to an account and the request carries no "
                "verifiable account identity")
        if _direct_owner_match(order, requester_account_id, requester_thumbprint):
            return
        if _reconciled_owner_match(order, requester_account_id, requester_thumbprint):
            return
        raise PermissionError(f"{resource} belongs to another account")

    def _orders_by_authz_url(self, authz_url: str):
        """Every proxy order that recorded this exact upstream authz URL.

        The proxy signs upstream with one shared account, so Let's Encrypt
        reuses a single authorization across every downstream account that
        ordered the same domain — the URL then maps to more than one local
        order (#307)."""
        from models import AcmeClientOrder

        if not authz_url:
            return []
        # LIKE is only a prefilter; the exact comparison below decides.
        rows = (AcmeClientOrder.query
                .filter(AcmeClientOrder.is_proxy_order.is_(True),
                        AcmeClientOrder.upstream_authz_urls.contains(
                            authz_url, autoescape=True))
                .order_by(AcmeClientOrder.id.asc())
                .all())
        return [row for row in rows if authz_url in self._recorded_authz_urls(row)]

    @staticmethod
    def _recorded_authz_urls(order):
        """Upstream authz URLs recorded on an order, as a list of strings."""
        try:
            urls = json.loads(order.upstream_authz_urls or '[]')
        except (TypeError, ValueError):
            return []
        if not isinstance(urls, list):
            return []
        return list(filter(lambda entry: isinstance(entry, str), urls))

    def _find_order_by_authz_url(self, authz_url: str, requester_account_id=None,
                                 requester_thumbprint=None):
        """Proxy order owning an upstream authz URL, resolved for the requester.

        When one upstream authz is shared by several local orders (#307), the
        order owned by the requester is returned so its ownership check passes;
        with no owner match the lowest-id candidate is handed back and
        the ownership check issues the denial, so #260 still holds.
        """
        return self._select_owning_order(
            self._orders_by_authz_url(authz_url),
            requester_account_id, requester_thumbprint, authz_url=authz_url,
        )

    @staticmethod
    def _select_owning_order(candidates, requester_account_id=None,
                             requester_thumbprint=None, authz_url=None):
        """Pick the candidate order that belongs to the requester.

        Two passes keep the AcmeAccount reconciliation off the common path: a
        direct match on either owner field first, the half-populated-binding
        reconciliation only if that finds nothing. A single candidate, legacy
        unbound rows, or no positive match all fall through to the first
        candidate unchanged, for the ownership check to rule on.
        """
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # The CA hands a still-pending authz or order to the client's next order
        # after a deactivation (#422) or a refused TXT record: the live order wins.
        # A locally failed order loses to one that did not fail: invalid is final for it only.
        # Without an authz URL (order lookup), any deactivated authz ranks the order last.
        candidates = sorted(candidates, key=lambda c: (
            authz_url in c.deactivated_authz_list if authz_url else bool(c.deactivated_authz_list),
            bool(AcmeProxyService._local_failure(c)),
            c.status != 'pending'))
        for candidate in candidates:
            if ((candidate.account_id
                 and candidate.account_id == requester_account_id)
                    or (candidate.client_jwk_thumbprint
                        and candidate.client_jwk_thumbprint == requester_thumbprint)):
                return candidate
        for candidate in candidates:
            if _reconciled_owner_match(candidate, requester_account_id,
                                       requester_thumbprint):
                return candidate
        return candidates[0]

    @staticmethod
    def _challenge_cache_key(chall_url, requester_account_id=None,
                             requester_thumbprint=None):
        """Per-requester key for the challenge-to-order cache.

        One upstream challenge URL resolves to a different local order per
        downstream account when the upstream authorization is shared (#307), so
        the cached (order id, identifier, authz URL) triplet is scoped to the
        requester identity. Both
        identity fields come from the same verified JWS, so an absent and an
        empty value are equivalent here and collapse to the same key.
        """
        if not chall_url:
            return ''
        return '\x1f'.join((
            chall_url,
            str(requester_account_id or ''),
            requester_thumbprint or '',
        ))

    @staticmethod
    def _challenge_automation_started(chall_url, sibling_orders):
        """True when dns-01 automation for this upstream challenge already ran.

        The challenge is one upstream resource even when several local orders
        point at it (#307); its DNS automation must fire once, so the initiated
        flag is read across every sibling order, not only the one being served.
        """
        for order in sibling_orders or ():
            state = (order.challenges_dict or {}).get(chall_url)
            if state and state.get('status') in ('initiated', 'submitted'):
                return True
        return False

    def get_authz(self, authz_id_b64, requester_account_id=None, requester_thumbprint=None):
        """Proxy authz fetch — only exposes dns-01 challenges and triggers automation.

        The proxy can only handle dns-01 validation (via DNS provider).
        http-01 and tls-alpn-01 require the upstream CA to reach the client
        directly, which doesn't work through a proxy.
        Ownership is enforced before the upstream round-trip: the authz must
        belong to a tracked proxy order owned by the requester (#260).
        """
        from api.v2.acme_domains import find_provider_for_domain

        # Fix padding + validate upstream host (anti-SSRF)
        authz_url = self._decode_proxy_id(authz_id_b64)

        # Find the proxy order that contains this authz URL — every proxy
        # order records its upstream authz URLs at creation, so an untracked
        # URL is either foreign or no longer served. One upstream authz can be
        # shared by several local orders (#307), so resolve to the requester's.
        candidates = self._orders_by_authz_url(authz_url)
        if not candidates:
            raise ProxyResourceNotFoundError("Authorization not found")
        order = self._select_owning_order(
            candidates, requester_account_id, requester_thumbprint,
            authz_url=authz_url,
        )
        self._require_owner(
            order, requester_account_id, requester_thumbprint,
            resource='Authorization')
        resp = self._post_with_account(authz_url, "")

        if resp.status_code != 200:
            logger.error(f"Upstream authz fetch failed: {resp.status_code} {resp.text}")
            raise UpstreamProblem.from_response(resp)
        self.retry_after = retry_after_of(resp)

        authz = resp.json()

        # Extract identifier (domain)
        identifier = authz.get('identifier', {})
        domain = strip_wildcard(identifier.get('value', ''))
        if not _order_covers_identifier(order, domain):
            logger.warning(
                "[ACME Proxy] Upstream authorization identifier %r is not part of "
                "order %s", identifier.get('value'), order.id,
            )
            raise ProxyResourceNotFoundError(
                "Authorization identifier is not part of the order")

        if authz_url in order.deactivated_authz_list:
            return self._deactivated_view(authz), identifier

        # An authorization the upstream CA has already validated (pre-validated
        # or onboarded domain, typically on an EAB-bound account) carries no
        # pending challenge and often no dns-01 at all. Nothing is left to
        # validate, so it is exposed as-is and the client goes straight to
        # finalize (#325). Otherwise only dns-01 is exposed: the proxy creates
        # the DNS record itself, while http-01/tls-alpn-01 need the upstream CA
        # to reach the client directly, which cannot work through a proxy.
        already_valid = authz.get('status') == 'valid'
        if _dns_failed_state(authz.get('status')):
            # RFC 8555 §7.1.6: every order using a failed authorization is invalid
            self._mark_invalid(o for o in candidates if o.status == 'pending')
            self._release_order_records(order)
        # RFC 8555 §7.1.6: invalid is final, even when the upstream CA validates it later.
        # The DNS UPDATE rows follow the upstream state: they are shared with other orders.
        upstream_authz_status = authz.get('status')
        failure = self._local_failure(order)
        if failure:
            authz['status'] = 'invalid'
        proxy_challenges = []
        closed_chall_urls = []
        for chall in authz.get('challenges', []):
            if chall.get('type') != 'dns-01' and not already_valid:
                continue
            chall_url = chall.get('url')
            if not chall_url:
                continue
            if (_dns_failed_state(upstream_authz_status)
                    or _dns_failed_state(chall.get('status'))):
                closed_chall_urls.append(chall_url)
            upstream_chall_status = chall.get('status')
            if failure:
                chall.update(status='invalid', error=failure)
            chall_id = self._proxy_id(chall_url)
            _challenge_order_cache.put(
                self._challenge_cache_key(chall_url, requester_account_id,
                                          requester_thumbprint),
                (order.id, domain, authz_url),
            )

            # Expected TXT values for the DNS UPDATE listener: one row per
            # order sharing this authz, whether or not automation started.
            # Written while the authz is pending and the challenge is pending
            # or processing (RFC 8555 section 7.1.6: not final yet), so a
            # sibling order that fetches the authz after the automation
            # started still gets its row.
            if (upstream_authz_status == 'pending'
                    and upstream_chall_status in ('pending', 'processing')
                    and not already_valid):
                live = [o for o in candidates if o.status == 'pending'
                        and authz_url not in o.deactivated_authz_list]
                _dns_rows_hook('persist_expected_values', live, domain,
                               chall.get('token'), chall_url,
                               authz.get('expires'), utc_now())

            # Check if we should trigger automation for this challenge
            # We trigger it as soon as the client fetches the authorization
            if chall.get('status') == 'pending' and not already_valid:
                if not self._challenge_automation_started(chall_url, candidates):
                    # Trigger automation in background
                    token = chall.get('token')
                    jwk_thumbprint = self._get_account_thumbprint()
                    key_authz = f"{token}.{jwk_thumbprint}"

                    # Ensure DNS provider exists
                    provider_info = find_provider_for_domain(domain)
                    if provider_info:
                        app = current_app._get_current_object()
                        thread = threading.Thread(
                            target=self._bg_respond_challenge,
                            args=(app, chall_url, key_authz, domain, order.id,
                                  authz_url)
                        )
                        thread.name = f"ACMEProxy-AutoDNS-{domain}"
                        thread.daemon = True

                        # Mark as initiated to avoid redundant threads
                        try:
                            if self._mark_initiated(order, chall_url):
                                thread.start()
                                logger.info(f"[ACME Proxy] Triggered auto-DNS for {domain} via authz fetch")
                        except Exception as e:
                            logger.error(f"Failed to start auto-DNS thread: {e}")


            chall['url'] = f"{self.base_url}/challenge/{chall_id}"
            proxy_challenges.append(chall)

        if closed_chall_urls:
            _dns_rows_hook('close_for_challenge_urls', closed_chall_urls)

        if not proxy_challenges and not already_valid:
            logger.error(
                f"Upstream authz for {identifier.get('value', '?')} has no dns-01 challenge. "
                f"Available types: {[c.get('type') for c in authz.get('challenges', [])]}"
            )
            raise ProxyDns01OnlyError(
                f"Upstream CA does not offer dns-01 challenge for {identifier.get('value', '?')}. "
                "The ACME proxy only supports dns-01 validation; tls-alpn-01 is not supported."
            )
        if already_valid and not failure:
            logger.info(
                "[ACME Proxy] Upstream authorization for %s is already valid; "
                "passed through without validation", domain,
            )

        authz['challenges'] = proxy_challenges
        return authz, identifier

    def deactivate_authz(self, authz_id_b64, requester_account_id=None,
                         requester_thumbprint=None):
        """RFC 8555 §7.5.2: the client relinquishes a pending or valid authorization.

        The upstream authz may be shared with other clients' orders (#307), so it
        is deactivated upstream only when no other pending local order uses it;
        otherwise only this client's order sees it deactivated (#422). Either way
        a pending order is invalid from then on."""
        authz_url = self._decode_proxy_id(authz_id_b64)
        candidates = self._orders_by_authz_url(authz_url)
        if not candidates:
            raise ProxyResourceNotFoundError("Authorization not found")
        order = self._select_owning_order(
            candidates, requester_account_id, requester_thumbprint,
            authz_url=authz_url,
        )
        self._require_owner(
            order, requester_account_id, requester_thumbprint,
            resource='Authorization')

        resp = self._post_with_account(authz_url, "")
        if resp.status_code != 200:
            raise UpstreamProblem.from_response(resp)
        authz = resp.json()
        identifier = authz.get('identifier', {})
        if not _order_covers_identifier(order, strip_wildcard(identifier.get('value', ''))):
            raise ProxyResourceNotFoundError(
                "Authorization identifier is not part of the order")

        if authz_url in order.deactivated_authz_list:
            return self._deactivated_view(authz), identifier
        status = authz.get('status')
        if status not in ('pending', 'valid', 'deactivated'):
            raise ProxyAuthzStateError(
                f"Authorization is {status}; only a pending or valid "
                "authorization can be deactivated")

        shared = [o for o in candidates
                  if o.id != order.id and o.status == 'pending'
                  and authz_url not in o.deactivated_authz_list]
        if status != 'deactivated' and not shared:
            resp = self._post_with_account(authz_url, {"status": "deactivated"})
            if resp.status_code != 200:
                raise UpstreamProblem.from_response(resp)
            authz = resp.json()
            logger.info("[ACME Proxy] Authorization for %s deactivated upstream (order %s)",
                        identifier.get('value'), order.id)
        else:
            logger.info("[ACME Proxy] Authorization for %s deactivated for order %s only: "
                        "%d other order(s) share it", identifier.get('value'), order.id,
                        len(shared))

        order.mark_authz_deactivated(authz_url)
        if order.status == 'pending':
            order.status = 'invalid'
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        _dns_rows_hook('close_for_order', order.id)
        self._release_order_records(order)
        return self._deactivated_view(authz), identifier

    def _deactivated_view(self, authz):
        """An authz as its deactivating client sees it: no automation, proxy URLs."""
        view = copy.deepcopy(authz)
        view['status'] = 'deactivated'
        view['challenges'] = [
            {**chall, 'url': f"{self.base_url}/challenge/{self._proxy_id(chall['url'])}"}
            for chall in authz.get('challenges', [])
            if chall.get('url') and (chall.get('type') == 'dns-01'
                                     or chall.get('status') == 'valid')
        ]
        return view

    def respond_challenge(self, chall_id_b64, requester_account_id=None, requester_thumbprint=None):
        """Proxy challenge response, or its status once automation runs.
        Ownership is enforced before any challenge data is returned or
        automation is triggered (#260)."""
        from api.v2.acme_domains import find_provider_for_domain

        chall_url = self._decode_proxy_id(chall_id_b64)

        order, _domain, authz_url = self._resolve_challenge_order(
            chall_url, requester_account_id, requester_thumbprint,
        )
        if order is not None and order.status != 'pending' and authz_url:
            # The cache may name a sibling that failed since: a live order on the authz wins
            order = self._find_order_by_authz_url(
                authz_url, requester_account_id, requester_thumbprint) or order
        if order:
            self._require_owner(
                order, requester_account_id, requester_thumbprint,
                resource='Challenge',
            )
            if authz_url and authz_url in order.deactivated_authz_list:
                raise ProxyAuthzStateError("Authorization is deactivated, not pending")

        # Read through the authorization: a POST-as-GET on the challenge starts
        # its validation on some servers, before the TXT record exists.
        authz_url, authz, challenge_data = self._read_challenge(
            chall_url, authz_url, [order] if order else self._requester_orders(
                requester_account_id, requester_thumbprint))
        if order is None:
            order = self._find_order_by_authz_url(
                authz_url, requester_account_id, requester_thumbprint)
            if order is None:
                raise ProxyResourceNotFoundError("Challenge not found")
            self._require_owner(
                order, requester_account_id, requester_thumbprint,
                resource='Challenge',
            )
            if authz_url in order.deactivated_authz_list:
                raise ProxyAuthzStateError("Authorization is deactivated, not pending")
        domain = self._authz_identifier(order, authz)
        _challenge_order_cache.put(
            self._challenge_cache_key(chall_url, requester_account_id,
                                      requester_thumbprint),
            (order.id, domain, authz_url),
        )
        token = challenge_data.get('token')
        challenge_type = challenge_data.get('type')
        status = challenge_data.get('status')
        up_link = self._get_authz_link(None, authz_url)

        # The shared DNS UPDATE rows close on the upstream state, before the local failure
        if _dns_failed_state(status):
            _dns_rows_hook('close_for_challenge_urls', [chall_url])
        failure = self._local_failure(order)  # final, whatever the upstream state (RFC 8555 §7.1.6)
        if failure:
            challenge_data.update(status='invalid', error=failure)
            status = 'invalid'

        if status != 'pending':
            # Already processing or finished: read-only pass-through whatever
            # the challenge type. A pre-validated authorization (#325) exposes
            # its already valid http-01/tls-alpn-01 challenge and a client may
            # poll it; nothing is triggered here.
            challenge_data['url'] = f"{self.base_url}/challenge/{chall_id_b64}"
            return challenge_data, up_link

        if challenge_type != 'dns-01':
            raise ProxyDns01OnlyError(
                f"Unsupported challenge type: {challenge_type}. "
                "The ACME proxy only supports dns-01 validation."
            )

        # If still pending, check if automation already started — for this order
        # in get_authz, or for a sibling order sharing this upstream challenge
        # when the authz is reused across downstream accounts (#307).
        siblings = self._orders_by_authz_url(authz_url) if authz_url else [order]
        if self._challenge_automation_started(chall_url, siblings or [order]):
            # Already triggered, just return 'processing'
            challenge_data['status'] = 'processing'
            challenge_data['url'] = f"{self.base_url}/challenge/{chall_id_b64}"
            return challenge_data, up_link

        # Fallback: Trigger if not already triggered (should be rare now)
        if not token:
            raise RuntimeError("Challenge has no token")

        provider_info = find_provider_for_domain(domain)
        if not provider_info:
            raise RuntimeError(f"No DNS provider configured for domain: {domain}")

        jwk_thumbprint = self._get_account_thumbprint()
        key_authz = f"{token}.{jwk_thumbprint}"

        app = current_app._get_current_object()
        thread = threading.Thread(
            target=self._bg_respond_challenge,
            args=(app, chall_url, key_authz, domain, order.id, authz_url)
        )
        thread.name = f"ACMEProxy-DNS-{domain}"
        thread.daemon = True

        # Persist the initiated flag before the thread starts so a sibling order
        # sharing this upstream challenge (#307) does not launch a second one.
        # Mirror get_authz: only start the thread once the flag is committed.
        try:
            if self._mark_initiated(order, chall_url):
                thread.start()
        except Exception as exc:
            logger.error(f"Failed to start dns-01 automation: {exc}")

        challenge_data['status'] = 'processing'
        challenge_data['url'] = f"{self.base_url}/challenge/{chall_id_b64}"

        return challenge_data, up_link

    def _requester_orders(self, requester_account_id=None, requester_thumbprint=None):
        """Recent unfinished proxy orders of the requester, and unbound ones."""
        from models import AcmeClientOrder

        unbound = and_(
            or_(AcmeClientOrder.account_id.is_(None), AcmeClientOrder.account_id == ''),
            or_(AcmeClientOrder.client_jwk_thumbprint.is_(None),
                AcmeClientOrder.client_jwk_thumbprint == ''),
        )
        identity = ((AcmeClientOrder.account_id, requester_account_id),
                    (AcmeClientOrder.client_jwk_thumbprint, requester_thumbprint))
        owned = [column == value for column, value in identity if value]
        return (AcmeClientOrder.query
                .filter(AcmeClientOrder.is_proxy_order.is_(True),
                        AcmeClientOrder.status.in_(('pending', 'invalid')),
                        or_(unbound, *owned))
                .order_by(AcmeClientOrder.id.desc())
                .limit(_CERT_FALLBACK_SCAN_LIMIT)
                .all())

    def _read_challenge(self, chall_url, authz_url, candidate_orders):
        """(authz URL, authz, challenge) read with POST-as-GET on the authorization.

        Without a known authz URL, the authorizations recorded on the candidate
        orders are read until one lists this exact challenge URL (bounded)."""
        if authz_url:
            urls = [authz_url]
        else:
            urls = []
            for candidate in candidate_orders:
                urls.extend(url for url in self._recorded_authz_urls(candidate)
                            if url not in urls and url not in candidate.deactivated_authz_list)
            # Let's Encrypt nests a challenge under its authorization id: read only that one
            parent_id = (urlsplit(chall_url).path.rstrip('/').split('/')[-2:-1] or [None])[0]
            named = [url for url in urls
                     if urlsplit(url).path.rstrip('/').rsplit('/', 1)[-1] == parent_id]
            urls = (named or urls)[:_CHALLENGE_SCAN_LIMIT]
        for url in urls:
            resp = self._post_with_account(url, "")
            if resp.status_code != 200:
                if authz_url:
                    raise UpstreamProblem.from_response(resp)
                continue
            authz = resp.json()
            for chall in (authz.get('challenges') or []) if isinstance(authz, dict) else []:
                if isinstance(chall, dict) and chall.get('url') == chall_url:
                    self.retry_after = retry_after_of(resp)
                    return url, authz, dict(chall)
        raise ProxyResourceNotFoundError("Challenge not found")

    @staticmethod
    def _authz_identifier(order, authz):
        """Identifier the authorization validates, refused when the order does not cover it."""
        value = (authz.get('identifier') or {}).get('value')
        if not value:
            raise ProxyChallengeIdentifierError(
                "Cannot determine which identifier this challenge validates: "
                "the upstream authorization carries no identifier")
        if not _order_covers_identifier(order, value):
            raise ProxyResourceNotFoundError(
                "Authorization identifier is not part of the order")
        return strip_wildcard(value)

    def _resolve_challenge_order(self, chall_url, requester_account_id=None,
                                 requester_thumbprint=None):
        """(order, identifier, authz URL) of a challenge, resolved locally.

        The authz fetch of the same requester is remembered first; then, for
        CAs nesting challenges under their authorization, parent paths of the
        challenge URL are compared exactly with recorded authz URLs. Returns
        (None, None, None) when nothing local matches; nothing is guessed.
        """
        from models import AcmeClientOrder

        cache_key = self._challenge_cache_key(
            chall_url, requester_account_id, requester_thumbprint)
        cached = _challenge_order_cache.get(cache_key)
        if cached:
            order_id, domain, authz_url = cached
            order = db.session.get(AcmeClientOrder, order_id)
            if order is not None and order.is_proxy_order:
                return order, domain, authz_url
            _challenge_order_cache.pop(cache_key)

        parent = chall_url
        for _level in range(_CHALLENGE_PARENT_LEVELS):
            parent = parent.rstrip('/').rsplit('/', 1)[0]
            if urlsplit(parent).path in ('', '/'):
                break
            order = self._find_order_by_authz_url(
                parent, requester_account_id, requester_thumbprint)
            if order is not None:
                return order, _single_domain(order), parent
        return None, None, None

    @staticmethod
    def _upstream_authz_url_from_link(upstream_link):
        """URL of the Link value whose rel is "up" (RFC 8288, RFC 8555 §7.5.1)."""
        if not upstream_link:
            return None
        for url, params in _link_values(upstream_link):
            relations = (params.get('rel') or '').lower().split()
            if url and 'up' in relations:
                return url
        return None

    def _get_authz_link(self, upstream_link, fallback_authz_url=None):
        """Rewrite the upstream Link rel="up"; without one (Pebble), point at the
        authorization the proxy already knows (RFC 8555 §7.5.1)."""
        authz_url = self._upstream_authz_url_from_link(upstream_link) or fallback_authz_url
        if authz_url:
            return f'<{self._proxy_url("authz", authz_url)}>;rel="up"'
        return None

    def _upstream_account_id(self):
        """Primary key of the linked CA account, read without loading the row
        (it may be detached from the request session)."""
        account = self._account
        if account is None:
            return self._account_id
        try:
            identity = sa_inspect(account).identity
        except NoInspectionAvailable:
            identity = None
        if identity:
            return identity[0]
        return getattr(account, 'id', self._account_id)

    def _make_thread_service(self, account_id):
        """Service instance owned by the dns-01 thread (substituted in tests)."""
        return AcmeProxyService(self.base_url, account_id=account_id)

    def _bg_respond_challenge(self, app, chall_url, key_authz, domain, order_id,
                              authz_url=None):
        """Thread body: publish the dns-01 record, then ask upstream to validate.

        Runs on its own service instance in its own app context: only the CA
        account id crosses from the request thread, never its ORM state."""
        account_id = self._upstream_account_id()
        with app.app_context():
            try:
                worker = self._make_thread_service(account_id)
                worker._run_dns01_automation(
                    chall_url, key_authz, domain, order_id, authz_url)
            except Exception as e:
                logger.error(f"[ACME Proxy BG] Error in background challenge setup: {e}", exc_info=True)
                db.session.rollback()
            finally:
                db.session.remove()

    def _run_dns01_automation(self, chall_url, key_authz, domain, order_id,
                              authz_url=None):
        """Publish the dns-01 TXT record, wait for it, then submit upstream."""
        import hashlib
        from api.v2.acme_domains import find_provider_for_domain
        from services.acme.dns_providers import create_provider
        from models import AcmeClientOrder

        # Calculate TXT value
        digest = hashlib.sha256(key_authz.encode()).digest()
        txt_value = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()

        # Get fresh order and provider
        order = db.session.get(AcmeClientOrder, order_id)
        provider_info = find_provider_for_domain(domain)
        if not order or not provider_info:
            logger.error(f"[ACME Proxy BG] Order {order_id} or provider for {domain} not found")
            return

        provider_model = provider_info['provider']
        credentials = json.loads(provider_model.credentials) if provider_model.credentials else {}
        provider = create_provider(provider_model.provider_type, credentials)

        # Hand the provider the name being validated and let it
        # resolve its own zone, which is what the ACME client path
        # already does. Guessing the zone here took it away from the
        # providers that can ask their API: a delegated child zone
        # was invisible to them, and the record landed in the parent
        # where the resolver never serves it.
        zone_name = self._strip_wildcard(domain)
        full_record_name = provider.get_acme_challenge_name(domain)

        logger.info(f"[ACME Proxy BG] Creating DNS TXT record for {domain}: {full_record_name}")
        # Both authorizations of a domain and its wildcard merge into one record set,
        # possibly from two workers: read-merge-write must not interleave.
        db.session.commit()  # no transaction held while waiting for the lock
        with _txt_record_lock(txt_lock_name(provider, full_record_name)):
            # A value a sibling order already published is live: some providers refuse a duplicate
            by_sibling = self._sibling_records(order, authz_url)

            def _write(value):
                if (full_record_name, value) in by_sibling:
                    return True, 'already published for a sibling order'
                return _txt_written(provider, zone_name, full_record_name, value)

            ok, message = _write(txt_value)
            if not ok:
                # Submitting anyway would fail the validation on the shared upstream account
                self._fail_dns_automation(order, chall_url, domain, message)
                return
            published = [txt_value]

            # Client-side pre-check support (#306/#307): lego/Caddy compute
            # the expected TXT value from THEIR account key, not from the
            # proxy's upstream account, so their propagation check could
            # never see the value published above. The client thumbprints
            # are known: publish their values too (extra TXT records on
            # the same name are ignored by the upstream CA validator).
            # A second value would replace the one the CA validates
            extra_values = [] if holds_one_value(provider) else self._client_txt_values(
                order, key_authz, txt_value, authz_url=authz_url)
            for extra_value in extra_values:
                ok, message = _write(extra_value)
                if ok:
                    published.append(extra_value)
                else:
                    logger.warning(f"[ACME Proxy BG] Client TXT value not published: {message}")

            # Store record info for cleanup, merged: another authorization of the order may have added its own
            added = [{'domain': zone_name, 'record_name': full_record_name,
                      'value': value, 'provider_id': provider_model.id} for value in published]

            def _add_records(row):
                records = json.loads(row.dns_records_created) if row.dns_records_created else []
                row.dns_records_created = json.dumps(records + added)

            _update_order_row(order, _add_records)

        # Active DNS self-check instead of fixed sleep.
        timeout = dns_propagation_timeout('acme.client.dns_propagation_timeout')
        acme_log(
            logger,
            '[ACME Proxy BG] DNS propagation wait for %s: timeout=%ss, record=%s',
            domain, timeout, full_record_name,
        )
        if timeout <= 0:
            logger.info("[ACME Proxy BG] DNS propagation wait skipped (timeout=0)")
            check = {'ok': True, 'missing': [], 'waited': 0}
        else:
            check = wait_for_txt(full_record_name, txt_value, timeout)
        if not check['ok']:
            # Soft-fail: our local resolver may miss the record (split-horizon,
            # filtered egress DNS) while the CA still sees it. Warn, keep the
            # TXT record in place and submit upstream: the CA is authoritative.
            logger.warning(
                "[ACME Proxy BG] DNS TXT not visible locally after %ss for %s (%s), "
                "submitting upstream anyway",
                timeout, domain, full_record_name,
            )
        else:
            logger.info("[ACME Proxy BG] DNS TXT confirmed after %ss for %s", check['waited'], domain)

        # A refusal on another authorization may have failed the order meanwhile;
        # submit only while a pending order still uses this authorization
        db.session.refresh(order)
        users = self._orders_by_authz_url(authz_url) if authz_url else [order]
        if not any(o.status == 'pending' and authz_url not in o.deactivated_authz_list
                   for o in users or [order]):
            logger.info("[ACME Proxy BG] Order %s failed meanwhile: %s not submitted", order.id, domain)
            self._abandon_challenge(order, chall_url)
            self._release_order_records(order)
            return

        # Trigger upstream validation
        logger.info(f"[ACME Proxy BG] Triggering upstream validation for {domain}")
        records = [[full_record_name, value] for value in published]
        try:
            resp = self._post_with_account(chall_url, {})
        except Exception as exc:
            logger.error("[ACME Proxy BG] Upstream challenge POST for %s failed: %s", domain, exc)
            resp, refused = None, isinstance(exc, requests.exceptions.ConnectTimeout)
        else:
            refused = 400 <= resp.status_code < 500
        if resp is not None and resp.status_code == 200:
            logger.info(f"[ACME Proxy BG] Upstream challenge validation triggered successfully for {domain}")
            self._mark_submitted(order, chall_url, records)
            return
        if resp is not None:
            logger.error(f"[ACME Proxy BG] Upstream challenge validation error: {resp.text}")
        # No answer or a 5xx may hide a POST the CA received: its authorization tells
        taken = None if refused else self._challenge_taken_upstream(chall_url, authz_url, order)
        if taken:
            logger.info("[ACME Proxy BG] Upstream took the challenge of %s despite the error", domain)
            self._mark_submitted(order, chall_url, records)
            return
        # Unknown (authorization unread): the CA may be reading the record, it goes later
        self._fail_challenge_submission(
            order, chall_url, domain, None if resp is None else UpstreamProblem.from_response(resp),
            linger=records if taken is None and not refused else ())

    @staticmethod
    def _mark_initiated(order, chall_url):
        """Flag a challenge's automation as started; False when it already was."""
        def _flag(row):
            challenges_data = row.challenges_dict
            if (challenges_data.get(chall_url) or {}).get('status') in ('initiated', 'submitted'):
                return False
            challenges_data[chall_url] = {'status': 'initiated',
                                          'started_at': datetime.now().isoformat()}
            row.set_challenges_dict(challenges_data)
            return True

        return _update_order_row(order, _flag)

    @staticmethod
    def _mark_submitted(order, chall_url, records):
        """Record a challenge the upstream CA took, with the TXT records it reads."""
        def _submitted(row):
            challenges_data = row.challenges_dict
            entry = challenges_data.get(chall_url, {})
            entry.update(status='submitted', submitted_at=datetime.now().isoformat(), records=records)
            challenges_data[chall_url] = entry
            row.set_challenges_dict(challenges_data)

        _update_order_row(order, _submitted)

    def _challenge_taken_upstream(self, chall_url, authz_url, order):
        """Whether the upstream authorization shows the challenge past pending
        (RFC 8555 §7.1.6), i.e. the CA received its POST; None when it cannot be read."""
        try:
            _url, authz, chall = self._read_challenge(chall_url, authz_url, [order])
        except Exception as exc:
            logger.warning("[ACME Proxy BG] Challenge state not read after a failed POST: %s", exc)
            return None
        return (chall.get('status') in ('processing', 'valid', 'invalid')
                or authz.get('status') in ('valid', 'invalid'))

    def _sibling_records(self, order, authz_url):
        """(record name, value) pairs other orders on this authorization still hold,
        those waiting for their deferred deletion included."""
        found = set()
        stale = time.time() - _SUBMITTED_RECORD_LINGER
        for other in self._orders_by_authz_url(authz_url) if authz_url else []:
            if other.id == order.id:
                continue
            try:
                records = json.loads(other.dns_records_created or '[]')
            except (TypeError, ValueError):
                continue
            found.update((r.get('record_name'), r.get('value'))
                         for r in records if isinstance(r, dict)
                         and (r.get('release_at') or stale) >= stale)
        return found

    @staticmethod
    def _abandon_challenge(order, chall_url):
        """Clear the initiated flag of a challenge left unsubmitted: a later order
        reusing the still-pending authorization must start its own automation."""
        def _abandon(row):
            challenges_data = row.challenges_dict
            if (challenges_data.get(chall_url) or {}).get('status') != 'initiated':
                return
            challenges_data[chall_url] = {'status': 'abandoned',
                                          'abandoned_at': datetime.now().isoformat()}
            row.set_challenges_dict(challenges_data)

        _update_order_row(order, _abandon)

    def _fail_dns_automation(self, order, chall_url, domain, message):
        """Fail the order locally after a refused TXT write; the upstream challenge is left alone."""
        logger.error("[ACME Proxy BG] DNS provider refused the TXT record for %s: %s", domain, message)
        self._fail_locally(order, chall_url, message,
                           f"DNS provider refused the TXT record for {domain}: {message}")

    def _fail_challenge_submission(self, order, chall_url, domain, upstream, linger=()):
        """Fail the order whose challenge POST the upstream CA refused (4xx), or did not
        take (its authorization still pending or unreadable): a later order starts its own.
        The ``linger`` records are removed later, like those of a submitted challenge."""
        if upstream is None:
            problem = {'type': 'urn:ietf:params:acme:error:serverInternal',
                       'detail': f'The upstream CA did not answer the validation request for {domain}'}
        else:
            problem = upstream.client_problem()[0]
        detail = _problem_text(problem)
        self._fail_locally(order, chall_url, detail,
                           f"Upstream challenge submission failed for {domain}: {detail}", problem,
                           linger=linger)

    def _fail_locally(self, order, chall_url, error, message, problem=None, linger=()):
        """Record a challenge that will never be submitted, fail the order and release its TXT records."""
        state = {'status': 'failed', 'error': error, 'failed_at': datetime.now().isoformat()}
        if problem:
            state['problem'] = problem

        def _fail(row):
            challenges_data = row.challenges_dict
            challenges_data[chall_url] = state
            row.set_challenges_dict(challenges_data)
            row.status = 'invalid'
            row.error_message = message
            row.last_error_at = utc_now()

        _update_order_row(order, _fail)
        _dns_rows_hook('close_for_order', order.id)
        self._release_order_records(order, linger={tuple(r) for r in linger})

    @staticmethod
    def _local_failure(order):
        """Problem of a challenge this order failed locally (TXT refused, POST failed), else None."""
        for state in (order.challenges_dict or {}).values():
            if (state or {}).get('status') == 'failed':
                return dict(state.get('problem') or _DNS_REFUSED_PROBLEM)
        return None

    @staticmethod
    def _mark_invalid(orders):
        """Record locally that these orders were read invalid upstream."""
        changed = False
        for order in orders:
            order.status = 'invalid'
            changed = True
        if not changed:
            return
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.warning("[ACME Proxy] Invalid order state not recorded: %s", exc)

    def _release_order_records(self, order, linger=()):
        """Remove in the background the TXT records of an order that can no longer issue.

        Kept while another pending order shares one of its authorizations: the
        record may be the value that order's validation reads. The records of
        submitted challenges and the ``linger`` (record name, value) pairs go later."""
        def _take(row):
            try:
                records = json.loads(row.dns_records_created or '[]')
            except (TypeError, ValueError):
                return [], []
            waiting = [r for r in records if isinstance(r, dict) and r.get('release_at')]
            records = [r for r in records if r not in waiting]
            if not records:
                return [], []
            for authz_url in self._recorded_authz_urls(row):
                if any(o.id != row.id and o.status == 'pending'
                       for o in self._orders_by_authz_url(authz_url)):
                    return [], []
            states = [state or {} for state in row.challenges_dict.values()]
            # Read under the row lock: a challenge still initiated may have its POST in flight
            if any(state.get('status') == 'initiated' for state in states):
                deferred = None
            else:
                deferred = set(linger) | {tuple(record) for state in states
                                          if state.get('status') == 'submitted'
                                          for record in state.get('records') or []}
            waits = [deferred is None or (r.get('record_name'), r.get('value')) in deferred
                     for r in records]
            release_at = time.time() + _SUBMITTED_RECORD_LINGER
            now = [r for r, wait in zip(records, waits) if not wait]
            later = [dict(r, release_at=release_at) for r, wait in zip(records, waits) if wait]
            # Deferred records stay listed until deleted: a retry within the delay sees them live
            row.dns_records_created = json.dumps(waiting + later) if waiting or later else None
            return now, later

        order_id = order.id
        try:
            now, later = _update_order_row(order, _take)
        except Exception as exc:
            logger.warning("[ACME Proxy] TXT cleanup of order %s not recorded: %s", order_id, exc)
            return
        if not now and not later:
            return
        app = current_app._get_current_object()
        for batch, args in ((now, (app, now, order_id)),
                            (later, (app, later, order_id, _SUBMITTED_RECORD_LINGER))):
            if not batch:
                continue
            thread = threading.Thread(target=self._bg_cleanup_dns_records, args=args)
            thread.name = "ACMEProxy-DNS-Cleanup"
            thread.daemon = True
            thread.start()

    @staticmethod
    def _value_still_needed(record_name, value, order_id):
        """Whether another pending order lists this (name, value) pair while the order
        cleaning it up did not issue: the authorization they share is still pending."""
        from models import AcmeClientOrder

        own = db.session.get(AcmeClientOrder, order_id)
        if own is not None and own.status == 'valid':
            return False
        rows = (AcmeClientOrder.query
                .filter(AcmeClientOrder.is_proxy_order.is_(True),
                        AcmeClientOrder.status == 'pending',
                        AcmeClientOrder.id != order_id,
                        AcmeClientOrder.dns_records_created.contains(value, autoescape=True))
                .all())
        for row in rows:
            try:
                records = json.loads(row.dns_records_created or '[]')
            except (TypeError, ValueError):
                continue
            if any(isinstance(r, dict) and not r.get('release_at')
                   and (r.get('record_name'), r.get('value')) == (record_name, value)
                   for r in records):
                return True
        return False

    @staticmethod
    def _forget_released_record(order_id, record_name, value):
        """Drop a deferred record from its order once its cleanup has run."""
        from models import AcmeClientOrder

        row = db.session.get(AcmeClientOrder, order_id)
        if row is None or value not in (row.dns_records_created or ''):
            return

        def _drop(fresh):
            try:
                records = json.loads(fresh.dns_records_created or '[]')
            except (TypeError, ValueError):
                return
            kept = [r for r in records if not (
                isinstance(r, dict) and r.get('release_at')
                and (r.get('record_name'), r.get('value')) == (record_name, value))]
            fresh.dns_records_created = json.dumps(kept) if kept else None

        _update_order_row(row, _drop)

    @staticmethod
    def _delete_dns_record(provider, zone: str, record_name: str, value, order_id=None) -> None:
        """Best-effort TXT cleanup helper; ``order_id`` is the order the record was published for."""
        if not value:
            logger.warning("DNS cleanup skipped for %s: no TXT value recorded", record_name)
            return
        try:
            with _txt_record_lock(txt_lock_name(provider, record_name)):
                # Under the name's lock: a sibling publishing the same value lists it first
                try:
                    if order_id is not None and AcmeProxyService._value_still_needed(
                            record_name, value, order_id):
                        logger.info("DNS cleanup of %s left to another order still validating it",
                                    record_name)
                        return
                    if keep_for_another_order(provider, record_name, order_id):
                        return
                    result = provider.delete_txt_record(zone, record_name, value)
                finally:
                    if order_id is not None:
                        AcmeProxyService._forget_released_record(order_id, record_name, value)
            if isinstance(result, tuple) and not result[0]:
                logger.warning("Failed to cleanup DNS record %s (%s): %s", record_name, zone, result[1])
        except Exception as e:
            logger.warning("Failed to cleanup DNS record %s (%s): %s", record_name, zone, e)

    def _bg_cleanup_dns_records(self, app, records, order_id=None, delay=0):
        """Background task: delete DNS-01 TXT records after cert issuance (#218), after ``delay`` seconds."""
        from models import DnsProvider
        from services.acme.dns_providers import create_provider

        if delay:
            time.sleep(delay)
        with app.app_context():
            try:
                for record in records:
                    try:
                        provider_model = db.session.get(DnsProvider, record['provider_id'])
                        if not provider_model:
                            continue
                        credentials = json.loads(provider_model.credentials) if provider_model.credentials else {}
                        provider = create_provider(provider_model.provider_type, credentials)
                        logger.info(f"[ACME Proxy] Cleaning up DNS record: {record['record_name']} in zone {record['domain']}")
                        self._delete_dns_record(provider, record['domain'], record['record_name'],
                                                record.get('value'), order_id)
                    except Exception as e:
                        logger.warning("[ACME Proxy] DNS record cleanup failed: %s", e)
            finally:
                db.session.remove()

    def _persist_certificate_url(self, row, cert_url: str):
        """Persist the upstream certificate URL on the local order served, not on
        a dead row sharing its upstream URL, so _find_order_for_certificate finds
        it with an indexed query (#219)."""
        try:
            if row.certificate_url != cert_url:
                row.certificate_url = cert_url
                db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.warning(f"ACME proxy: failed to persist certificate URL: {exc}")

    def _find_order_for_certificate(self, cert_url, requester_account_id=None, requester_thumbprint=None):
        """Match a proxy order to the upstream certificate download URL.

        Fast path: indexed lookup on the persisted certificate_url (#219).
        Fallback for older rows: the most recent pending orders without a
        persisted URL, limited to the requester's and unbound ones, each
        re-read upstream and kept only on an exact certificate URL match.
        """
        from models import AcmeClientOrder

        order = AcmeClientOrder.query.filter_by(
            is_proxy_order=True, certificate_url=cert_url
        ).first()
        if order:
            return order

        unbound = and_(
            or_(AcmeClientOrder.account_id.is_(None), AcmeClientOrder.account_id == ''),
            or_(AcmeClientOrder.client_jwk_thumbprint.is_(None),
                AcmeClientOrder.client_jwk_thumbprint == ''),
        )
        identity = ((AcmeClientOrder.account_id, requester_account_id),
                    (AcmeClientOrder.client_jwk_thumbprint, requester_thumbprint))
        owned = [column == value for column, value in identity if value]
        candidates = (AcmeClientOrder.query
                      .filter(AcmeClientOrder.is_proxy_order.is_(True),
                              AcmeClientOrder.status == 'pending',
                              or_(AcmeClientOrder.certificate_url.is_(None),
                                  AcmeClientOrder.certificate_url == ''),
                              AcmeClientOrder.upstream_order_url.isnot(None),
                              or_(unbound, *owned))
                      .order_by(AcmeClientOrder.id.desc())
                      .limit(_CERT_FALLBACK_SCAN_LIMIT)
                      .all())
        for candidate in candidates:
            try:
                resp = self._post_with_account(candidate.upstream_order_url, "")
                if resp.status_code != 200:
                    continue
                upstream_order = resp.json()
            except Exception as exc:
                logger.debug(f"Certificate lookup: upstream order fetch failed: {exc}")
                continue
            if isinstance(upstream_order, dict) and upstream_order.get('certificate') == cert_url:
                self._persist_certificate_url(candidate, cert_url)
                return candidate
        return None

    def _get_account_thumbprint(self):
        """Get JWK thumbprint of our upstream account key"""
        return self._jwk_thumbprint()

    def _build_eab(self, kid, hmac_key_b64, account_url):
        """Build External Account Binding JWS (RFC 8555 §7.3.4)"""
        import hashlib
        import hmac as hmac_mod

        # Decode HMAC key (base64url-encoded)
        hmac_key_padded = hmac_key_b64 + '=' * (4 - len(hmac_key_b64) % 4)
        hmac_key = base64.urlsafe_b64decode(hmac_key_padded)

        # Protected header for EAB
        protected = {
            "alg": "HS256",
            "kid": kid,
            "url": account_url
        }
        protected_b64 = base64.urlsafe_b64encode(
            json.dumps(protected).encode()
        ).rstrip(b'=').decode()

        # Payload is the account key JWK
        jwk_json = json.dumps(self.account_jwk, separators=(',', ':'), sort_keys=True)
        payload_b64 = base64.urlsafe_b64encode(jwk_json.encode()).rstrip(b'=').decode()

        # HMAC-SHA256 signature
        signing_input = f"{protected_b64}.{payload_b64}".encode()
        sig = hmac_mod.new(hmac_key, signing_input, hashlib.sha256).digest()
        sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b'=').decode()

        return {
            "protected": protected_b64,
            "payload": payload_b64,
            "signature": sig_b64
        }

    def _order_by_upstream_url(self, order_url, requester_account_id=None,
                               requester_thumbprint=None):
        """The requester's local order for an upstream order URL.

        A CA may hand the same pending order back to the proxy's one account, so
        several local rows can share the URL; one without a deactivated authz
        (#422) wins over an older one of the same client."""
        from models import AcmeClientOrder

        rows = (AcmeClientOrder.query
                .filter_by(upstream_order_url=order_url, is_proxy_order=True)
                .order_by(AcmeClientOrder.id.asc()).all())
        return self._select_owning_order(rows, requester_account_id, requester_thumbprint)

    def get_order(self, order_id_b64, requester_account_id=None, requester_thumbprint=None):
        """Get order status (POST-as-GET) — the order must be a tracked proxy
        order owned by the requester (#260)."""
        from models import AcmeClientOrder

        order_url = self._decode_proxy_id(order_id_b64)

        local_order = self._order_by_upstream_url(
            order_url, requester_account_id, requester_thumbprint)
        if local_order is None:
            raise ProxyResourceNotFoundError("Order not found")
        self._require_owner(local_order, requester_account_id, requester_thumbprint)
        resp = self._post_with_account(order_url, "")
        if resp.status_code != 200:
            raise UpstreamProblem.from_response(resp)
        self.retry_after = retry_after_of(resp)

        order = resp.json()
        _finalize_url_cache.put(order_url, order.get('finalize'))
        if (local_order.deactivated_authz_list
                and order.get('status') in ('pending', 'ready')):
            order['status'] = 'invalid'
        # RFC 8555 §7.1.6: invalid is final, even when the upstream CA validates the order later
        failure = self._local_failure(local_order)
        if failure:
            order['status'] = 'invalid'
            order.setdefault('error', failure)
            order.pop('certificate', None)
        if order.get('status') == 'invalid':
            self._mark_invalid([local_order] if local_order.status == 'pending' else [])
            self._release_order_records(local_order)
        return self._rewrite_order_urls(order, order_url, order_id_b64, local_order)

    def finalize_order(self, order_id_b64, csr_pem, requester_account_id=None,
                       requester_thumbprint=None):
        """Proxy finalize.

        The order must be a tracked proxy order owned by the requester —
        same binding as every other order-scoped proxy endpoint (#260):
        account_id and/or client_jwk_thumbprint recorded at new-order must
        match the verified requester identity, failing closed when an
        owner-bound order gets no derivable identity at all.
        """
        from models import AcmeClientOrder

        order_url = self._decode_proxy_id(order_id_b64)

        local_order = self._order_by_upstream_url(
            order_url, requester_account_id, requester_thumbprint)
        if local_order is None:
            raise ProxyResourceNotFoundError("Order not found")
        self._require_owner(
            local_order, requester_account_id, requester_thumbprint,
        )
        if local_order.deactivated_authz_list:
            raise ProxyOrderNotReadyError(
                "Order is invalid: one of its authorizations was deactivated")
        failure = self._local_failure(local_order)
        if failure:
            raise ProxyOrderNotReadyError(f"Order is invalid: {_problem_text(failure)}")

        from cryptography import x509
        csr = x509.load_pem_x509_csr(csr_pem.encode(), default_backend())
        # Checked here: the upstream CA may answer a mismatch with unauthorized, the proxy's own fault
        _require_csr_matches_order(csr, local_order)
        csr_der = csr.public_bytes(serialization.Encoding.DER)
        csr_b64 = base64.urlsafe_b64encode(csr_der).rstrip(b'=').decode()

        payload = {"csr": csr_b64}

        finalize_url = _finalize_url_cache.get(order_url)
        if not finalize_url:
            order_resp = self._post_with_account(order_url, "")
            if order_resp.status_code != 200:
                raise UpstreamProblem.from_response(order_resp)
            finalize_url = order_resp.json().get('finalize')
            if not finalize_url:
                raise Exception("Upstream order carries no finalize URL")
            _finalize_url_cache.put(order_url, finalize_url)

        # Call finalize
        resp = self._post_with_account(finalize_url, payload)

        if resp.status_code != 200:
            raise UpstreamProblem.from_response(resp)
        self.retry_after = retry_after_of(resp)

        order = resp.json()
        _finalize_url_cache.put(order_url, order.get('finalize'))
        return self._rewrite_order_urls(order, order_url, order_id_b64, local_order)

    def get_certificate(self, cert_id_b64, requester_account_id=None, requester_thumbprint=None):
        """Proxy certificate download with DNS cleanup and storage.
        The certificate must belong to a tracked proxy order owned by the
        requester (#260); the order is resolved before the upstream fetch."""
        from models import AcmeClientOrder, Certificate
        from services.acme.dns_providers import create_provider
        from services.cert_service import CertificateService

        cert_url = self._decode_proxy_id(cert_id_b64)

        order = self._find_order_for_certificate(
            cert_url,
            requester_account_id=requester_account_id,
            requester_thumbprint=requester_thumbprint,
        )
        if order is None:
            raise ProxyResourceNotFoundError("Certificate not found")
        self._require_owner(
            order, requester_account_id, requester_thumbprint,
            resource='Certificate')
        resp = self._post_with_account(cert_url, "")
        if resp.status_code != 200:
            raise UpstreamProblem.from_response(resp)

        # Never forward the upstream Link header: its rel="alternate" entries
        # point directly at the real CA and can only be authenticated with our
        # upstream account key — a downstream client following them signs with
        # a proxy-scoped kid and gets rejected by the CA (#220). The preferred
        # chain is already resolved server-side below and served in the body.
        link_header = None

        # Body served to the client — replaced by the selected chain below on 200.
        response_body = resp.content

        if resp.status_code == 200:
            # Certificate obtained successfully
            from services.acme.acme_chain_selection import select_acme_certificate_chain

            def _fetch_alternate(url: str) -> str:
                alt_resp = self._post_with_account(url, "")
                if alt_resp.status_code != 200:
                    raise RuntimeError(
                        f'Alternate chain fetch failed: HTTP {alt_resp.status_code}'
                    )
                content = alt_resp.content
                return content.decode('utf-8') if isinstance(content, bytes) else content

            preferred = None
            if self.account:
                preferred = (self.account.preferred_chain or '').strip() or None

            cert_pem = select_acme_certificate_chain(
                resp.content.decode('utf-8') if isinstance(resp.content, bytes) else resp.content,
                resp.headers,
                preferred,
                _fetch_alternate,
            )
            # Serve the selected (preferred) chain to the client, not just store it.
            response_body = cert_pem

            stored_cert = None
            # Store the certificate in the database
            try:
                # The response usually contains full chain, extract first cert
                certs = cert_pem.split('-----END CERTIFICATE-----')
                if certs and certs[0].strip():
                    first_cert = certs[0].strip() + '\n-----END CERTIFICATE-----\n'
                    # Build chain from remaining certs
                    remaining = [c.strip() + '\n-----END CERTIFICATE-----\n' for c in certs[1:] if c.strip()]
                    chain = ''.join(remaining) if remaining else None

                    # Extract CN for description
                    from cryptography import x509
                    cert_obj = x509.load_pem_x509_certificate(first_cert.encode(), default_backend())
                    cn = cert_obj.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
                    descr = cn[0].value if cn else "External ACME Certificate"

                    # self.account may be a stub without a label in some
                    # legacy/proxy paths — stay defensive here.
                    logger.info(
                        "[ACME Proxy] Storing certificate issued by %s: %s",
                        getattr(self.account, 'label', None) or 'External ACME CA',
                        descr,
                    )

                    stored_cert = CertificateService.import_certificate(
                        descr=descr,
                        cert_pem=first_cert,
                        chain_pem=chain,
                        source='acme_client',
                        username='acme_proxy'
                    )
                    logger.info(f"[ACME Proxy] Certificate stored with ID: {stored_cert.id}")
            except Exception as e:
                # Log but don't fail - cert was obtained
                logger.error(f"[ACME Proxy] Error storing certificate: {e}")

            # Link certificate to order (resolved before the upstream fetch);
            # DNS cleanup runs in the background so the client is not blocked
            # on DNS-provider API latency (#218).
            records_to_cleanup = []
            order_id = order.id  # read before a rollback expires the row
            try:
                # Link certificate to order
                if stored_cert:
                    order.certificate_id = stored_cert.id

                # Snapshot DNS records, then commit the order state before
                # any provider round-trip.
                if order.dns_records_created:
                    records_to_cleanup = json.loads(order.dns_records_created)

                order.status = 'valid'
                order.dns_records_created = None  # Cleanup dispatched below
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Failed to update order status: {e}")
                else:
                    _dns_rows_hook('close_for_order', order.id)
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed during certificate cleanup: {e}")

            # Opt-in: purge certificates superseded by this renewal (#240)
            if stored_cert:
                try:
                    self._prune_replaced_certificates(order, stored_cert.id)
                except Exception as e:
                    logger.error(f"[ACME Proxy] Prune of replaced certificates failed: {e}")

            if records_to_cleanup:
                app = current_app._get_current_object()

                thread = threading.Thread(
                    target=self._bg_cleanup_dns_records,
                    args=(app, records_to_cleanup, order_id)
                )
                thread.name = "ACMEProxy-DNS-Cleanup"
                thread.daemon = True
                thread.start()

        # Cert response is PEM stream usually
        return response_body, resp.headers.get('Content-Type', 'application/pem-certificate-chain'), link_header
