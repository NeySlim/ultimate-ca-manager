
"""
ACME Proxy Service
Acts as a gateway between internal ACME clients and upstream ACME providers (Let's Encrypt)
"""
import json
import base64
import requests
import secrets
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, Union

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding, utils as asym_utils
from cryptography.hazmat.backends import default_backend

from models import db, SystemConfig, DnsProvider
from security.encryption import encrypt_text, decrypt_text
from utils.datetime_utils import utc_isoformat
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
        self.nonces = []
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

    def _refresh_account_session(self) -> None:
        """Re-bind the linked AcmeClientAccount to the current SQLAlchemy session.

        Background threads push their own app context (and therefore their own
        session). ORM objects loaded on the request thread are detached here;
        signing upstream JWS in _bg_respond_challenge would raise DetachedInstanceError
        without this refresh.
        """
        from models.acme_client_account import AcmeClientAccount

        account_id = self.account.id
        self._account = db.session.get(AcmeClientAccount, account_id)
        if not self._account:
            raise RuntimeError(f"ACME proxy account {account_id} not found")
        if self._account_url is None:
            self._account_url = self._account.account_url

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
        try:
            ssrf_protection.validate_url_not_cloud_metadata(url, allow_loopback=acme_allow_loopback_upstream())
        except ValueError as exc:
            raise ValueError(f'ACME outbound URL blocked: {exc}') from exc

    def _http_timeout(self) -> int:
        if self.account:
            return self.account.get_http_timeout_sec()
        from models.acme_client_account import AcmeClientAccount
        return AcmeClientAccount.DEFAULT_HTTP_TIMEOUT_SEC

    def _ensure_directory(self):
        """Fetch upstream directory"""
        if not self.directory:
            self._validate_outbound_acme_url(self.upstream_directory_url)
            try:
                resp = ssrf_protection.safe_request_get(
                    self.upstream_directory_url,
                    allow_loopback=acme_allow_loopback_upstream(),
                    timeout=15,
                    verify=self.verify_ssl,
                )
                resp.raise_for_status()
                self.directory = resp.json()
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
        """Get nonce from upstream"""
        self._ensure_directory()
        nonce_url = self.directory['newNonce']
        self._validate_outbound_acme_url(nonce_url)
        resp = ssrf_protection.safe_request_head(
            nonce_url,
            allow_loopback=acme_allow_loopback_upstream(),
            timeout=15,
            verify=self.verify_ssl,
        )
        return resp.headers['Replay-Nonce']

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

        headers = {"Content-Type": "application/jose+json"}
        self._validate_outbound_acme_url(url)
        return ssrf_protection.safe_request_post(
            url,
            allow_loopback=acme_allow_loopback_upstream(),
            json=data,
            headers=headers,
            timeout=self._http_timeout(),
            verify=self.verify_ssl
        )

    def _post_jws(self, url: str, payload: Union[Dict, str], kid: str = None) -> requests.Response:
        """Sign and post JWS to upstream, with automatic badNonce retry (RFC 8555 §6.5).

        Some upstream CAs (Pebble, HARICA, strict implementations) reject
        nonces that LE staging would accept. On badNonce, the server MUST
        return a fresh nonce in Replay-Nonce and the client MUST retry.
        """
        nonce = self._get_nonce()
        resp = self._sign_and_post(url, payload, nonce, kid=kid)

        # RFC 8555 §6.5: retry once on badNonce using the fresh nonce
        # returned in the error response's Replay-Nonce header.
        if resp.status_code == 400:
            try:
                err = resp.json()
                if err.get('type') == 'urn:ietf:params:acme:error:badNonce':
                    fresh_nonce = resp.headers.get('Replay-Nonce')
                    if fresh_nonce:
                        logger.warning(f"Upstream rejected nonce on {url}, retrying with fresh nonce")
                        resp = self._sign_and_post(url, payload, fresh_nonce, kid=kid)
            except (json.JSONDecodeError, ValueError):
                pass

        return resp

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
            "keyChange": f"{self.base_url}/key-change",
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

    def new_order(self, identifiers, not_before=None, not_after=None, client_thumbprint=None):
        """Proxy new-order with domain validation"""
        from api.v2.acme_domains import find_provider_for_domain
        from models import AcmeClientOrder
        
        if not identifiers:
            raise ValueError("identifiers must be a non-empty list")
        
        self._ensure_directory()
        
        # Extract domains from identifiers
        domains = []
        for ident in identifiers:
            if ident.get('type') == 'dns':
                domains.append(ident.get('value'))
        
        # Verify each domain has a DNS provider configured
        domain_providers = {}
        for domain in domains:
            # Remove wildcard prefix for lookup (removeprefix not lstrip — chars vs prefix)
            lookup_domain = domain[2:] if domain.startswith('*.') else domain
            provider = find_provider_for_domain(lookup_domain)
            if not provider:
                raise Exception(f"No DNS provider configured for domain: {domain}. Configure it in ACME > Domains.")
            domain_providers[domain] = provider
        
        # Forward to upstream Let's Encrypt
        payload = {
            "identifiers": identifiers,
            "notBefore": utc_isoformat(not_before),
            "notAfter": utc_isoformat(not_after)
        }
        # Filter None
        payload = {k: v for k, v in payload.items() if v is not None}
        
        resp = self._post_with_account(self.directory['newOrder'], payload)
        
        if resp.status_code != 201:
            raise Exception(f"Upstream error: {resp.text}")
            
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
        
        # Rewrite URLs in response to point to Proxy
        # We encode upstream URLs into base64 IDs
        order_id = base64.urlsafe_b64encode(upstream_location.encode()).rstrip(b'=').decode()
        
        proxy_authzs = []
        for authz_url in upstream_order['authorizations']:
            authz_id = base64.urlsafe_b64encode(authz_url.encode()).rstrip(b'=').decode()
            proxy_authzs.append(f"{self.base_url}/authz/{authz_id}")
            
        upstream_order['authorizations'] = proxy_authzs
        upstream_order['finalize'] = f"{self.base_url}/order/{order_id}/finalize"
        
        return upstream_order, order_id

    def get_authz(self, authz_id_b64):
        """Proxy authz fetch — only exposes dns-01 challenges and triggers automation.
        
        The proxy can only handle dns-01 validation (via DNS provider).
        http-01 and tls-alpn-01 require the upstream CA to reach the client
        directly, which doesn't work through a proxy.
        """
        from api.v2.acme_domains import find_provider_for_domain
        from models import AcmeClientOrder
        
        # Fix padding + validate upstream host (anti-SSRF)
        authz_url = self._decode_proxy_id(authz_id_b64)
        
        resp = self._post_with_account(authz_url, "")
        
        if resp.status_code != 200:
            logger.error(f"Upstream authz fetch failed: {resp.status_code} {resp.text}")
            return None
             
        authz = resp.json()
        
        # Extract identifier (domain)
        identifier = authz.get('identifier', {})
        domain = identifier.get('value', '').lstrip('*.')
        
        # Find the proxy order that contains this authz URL
        order = AcmeClientOrder.query.filter(
            AcmeClientOrder.is_proxy_order == True,
            AcmeClientOrder.upstream_authz_urls.contains(authz_url)
        ).first()
        
        # Filter to dns-01 only — the proxy handles DNS record creation
        # automatically. http-01/tls-alpn-01 cannot work through a proxy
        # because the upstream CA needs direct access to the client.
        proxy_challenges = []
        for chall in authz.get('challenges', []):
            if chall.get('type') != 'dns-01':
                continue
            
            chall_url = chall['url']
            chall_id = base64.urlsafe_b64encode(chall_url.encode()).rstrip(b'=').decode()
            
            # Check if we should trigger automation for this challenge
            # We trigger it as soon as the client fetches the authorization
            if order and chall.get('status') == 'pending':
                challenges_data = order.challenges_dict
                if chall_url not in challenges_data or challenges_data[chall_url].get('status') != 'initiated':
                    # Trigger automation in background
                    token = chall.get('token')
                    jwk_thumbprint = self._get_account_thumbprint()
                    key_authz = f"{token}.{jwk_thumbprint}"
                    
                    # Ensure DNS provider exists
                    provider_info = find_provider_for_domain(domain)
                    if provider_info:
                        import threading
                        from flask import current_app
                        app = current_app._get_current_object()
                        
                        thread = threading.Thread(
                            target=self._bg_respond_challenge,
                            args=(app, chall_url, key_authz, domain, order.id)
                        )
                        thread.name = f"ACMEProxy-AutoDNS-{domain}"
                        thread.daemon = True
                        
                        # Mark as initiated to avoid redundant threads
                        challenges_data[chall_url] = {'status': 'initiated', 'started_at': datetime.now().isoformat()}
                        order.set_challenges_dict(challenges_data)
                        try:
                            db.session.commit()
                            thread.start()
                            logger.info(f"[ACME Proxy] Triggered auto-DNS for {domain} via authz fetch")
                        except Exception as e:
                            db.session.rollback()
                            logger.error(f"Failed to start auto-DNS thread: {e}")
            
            chall['url'] = f"{self.base_url}/challenge/{chall_id}"
            proxy_challenges.append(chall)
        
        if not proxy_challenges:
            logger.error(
                f"Upstream authz for {identifier.get('value', '?')} has no dns-01 challenge. "
                f"Available types: {[c.get('type') for c in authz.get('challenges', [])]}"
            )
            raise RuntimeError(
                f"Upstream CA does not offer dns-01 challenge for {identifier.get('value', '?')}. "
                "The ACME proxy only supports dns-01 validation."
            )
            
        authz['challenges'] = proxy_challenges
        return authz, identifier

    def respond_challenge(self, chall_id_b64):
        """Proxy challenge response. If automation is already running/done, just return status."""
        from api.v2.acme_domains import find_provider_for_domain
        from models import AcmeClientOrder
        
        chall_url = self._decode_proxy_id(chall_id_b64)
        
        # Fetch the challenge to get token and status
        resp = self._post_with_account(chall_url, "")
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch challenge: {resp.text}")
        
        challenge_data = resp.json()
        token = challenge_data.get('token')
        challenge_type = challenge_data.get('type')
        status = challenge_data.get('status')
        
        if challenge_type != 'dns-01':
            raise RuntimeError(
                f"Unsupported challenge type: {challenge_type}. "
                "The ACME proxy only supports dns-01 validation."
            )
        
        if status != 'pending':
            # Already processing or finished
            challenge_data['url'] = f"{self.base_url}/challenge/{chall_id_b64}"
            return challenge_data, self._get_authz_link(resp.headers.get('Link'))

        # If still pending, check if we already triggered automation in get_authz
        order = self._find_order_for_challenge(chall_url, AcmeClientOrder)
        if order:
            challenges_data = order.challenges_dict
            if chall_url in challenges_data and challenges_data[chall_url].get('status') == 'initiated':
                # Already triggered, just return 'processing'
                challenge_data['status'] = 'processing'
                challenge_data['url'] = f"{self.base_url}/challenge/{chall_id_b64}"
                return challenge_data, self._get_authz_link(resp.headers.get('Link'))

        # Fallback: Trigger if not already triggered (should be rare now)
        if not token:
            raise RuntimeError("Challenge has no token")
        
        domain = order.domains_list[0].lstrip('*.') if order else "unknown"
        provider_info = find_provider_for_domain(domain)
        if not provider_info:
            raise RuntimeError(f"No DNS provider configured for domain: {domain}")

        jwk_thumbprint = self._get_account_thumbprint()
        key_authz = f"{token}.{jwk_thumbprint}"
        
        import threading
        from flask import current_app
        app = current_app._get_current_object()
        
        thread = threading.Thread(
            target=self._bg_respond_challenge,
            args=(app, chall_url, key_authz, domain, order.id if order else None)
        )
        thread.name = f"ACMEProxy-DNS-{domain}"
        thread.daemon = True
        thread.start()
        
        challenge_data['status'] = 'processing'
        challenge_data['url'] = f"{self.base_url}/challenge/{chall_id_b64}"
        
        return challenge_data, self._get_authz_link(resp.headers.get('Link'))

    def _get_authz_link(self, upstream_link):
        """Extract and rewrite authz Link header from upstream response"""
        if not upstream_link:
            return None
        import re
        match = re.search(r'<([^>]+)>;\s*rel="up"', upstream_link)
        if not match:
            # Try without rel="up" just in case
            match = re.search(r'<([^>]+)>', upstream_link)
            
        if match:
            authz_url = match.group(1)
            authz_id = base64.urlsafe_b64encode(authz_url.encode()).rstrip(b'=').decode()
            return f'<{self.base_url}/authz/{authz_id}>;rel="up"'
        return None

    def _bg_respond_challenge(self, app, chall_url, key_authz, domain, order_id):
        """Background task for DNS setup and upstream validation trigger"""
        import hashlib
        from api.v2.acme_domains import find_provider_for_domain
        from services.acme.dns_providers import create_provider
        from models import AcmeClientOrder
        
        with app.app_context():
            try:
                self._refresh_account_session()

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
                
                # Find the best zone for this domain
                zone = provider.get_zone_for_domain(domain)
                full_record_name = provider.get_acme_challenge_name(domain)
                
                logger.info(f"[ACME Proxy BG] Creating DNS TXT record for {domain} in zone {zone}: {full_record_name}")
                provider.create_txt_record(zone, full_record_name, txt_value)

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
                    # TXT record in place, and submit upstream — the CA is authoritative.
                    logger.warning(
                        "[ACME Proxy BG] DNS TXT not visible locally after %ss for %s (%s) — "
                        "submitting upstream anyway",
                        timeout, domain, full_record_name,
                    )
                else:
                    logger.info("[ACME Proxy BG] DNS TXT confirmed after %ss for %s", check['waited'], domain)
                
                # Store record info for cleanup
                records = json.loads(order.dns_records_created) if order.dns_records_created else []
                records.append({
                    'domain': zone,
                    'record_name': full_record_name,
                    'value': txt_value,
                    'provider_id': provider_model.id
                })
                order.dns_records_created = json.dumps(records)
                db.session.commit()
                
                # Trigger upstream validation
                logger.info(f"[ACME Proxy BG] Triggering upstream validation for {domain}")
                payload = {}
                resp = self._post_with_account(chall_url, payload)
                
                if resp.status_code != 200:
                    logger.error(f"[ACME Proxy BG] Upstream challenge validation error: {resp.text}")
                else:
                    logger.info(f"[ACME Proxy BG] Upstream challenge validation triggered successfully for {domain}")
                    challenges_data = order.challenges_dict
                    entry = challenges_data.get(chall_url, {})
                    entry['status'] = 'submitted'
                    entry['submitted_at'] = datetime.now().isoformat()
                    challenges_data[chall_url] = entry
                    order.set_challenges_dict(challenges_data)
                    db.session.commit()
                    
            except Exception as e:
                logger.error(f"[ACME Proxy BG] Error in background challenge setup: {e}", exc_info=True)
                db.session.rollback()
            finally:
                db.session.remove()

    @staticmethod
    def _delete_dns_record(provider, zone: str, record_name: str) -> None:
        """Best-effort TXT cleanup helper."""
        try:
            provider.delete_txt_record(zone, record_name)
        except Exception as e:
            logger.warning("Failed to cleanup DNS record %s (%s): %s", record_name, zone, e)

    def _bg_cleanup_dns_records(self, app, records):
        """Background task: delete DNS-01 TXT records after cert issuance (#218)."""
        from models import DnsProvider
        from services.acme.dns_providers import create_provider

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
                        self._delete_dns_record(provider, record['domain'], record['record_name'])
                    except Exception as e:
                        logger.warning(f"Failed to cleanup DNS record {record.get('record_name')}: {e}")
            finally:
                db.session.remove()

    def _find_order_for_challenge(self, chall_url, AcmeClientOrder):
        """Find the proxy order associated with a challenge URL."""
        # Strategy: fetch the challenge to get its authz URL from Link header,
        # then match against stored upstream authz URLs
        pending_orders = AcmeClientOrder.query.filter(
            AcmeClientOrder.is_proxy_order == True,
            AcmeClientOrder.status == 'pending'
        ).order_by(AcmeClientOrder.created_at.desc()).all()
        
        for order in pending_orders:
            if order.upstream_authz_urls:
                try:
                    authz_urls = json.loads(order.upstream_authz_urls)
                    # Challenge URLs are under the authz URL path on most CAs
                    for authz_url in authz_urls:
                        # Match by common URL prefix (same CA host/path structure)
                        if self._urls_share_ca(chall_url, authz_url):
                            return order
                except (json.JSONDecodeError, TypeError):
                    pass
        
        # Fallback: most recent pending proxy order
        if pending_orders:
            logger.warning("Could not match challenge to specific order, using most recent")
            return pending_orders[0]
        return None
    
    def _persist_certificate_url(self, order_url: str, cert_url: str):
        """Persist the upstream certificate URL on the local proxy order row.

        Lets _find_order_for_certificate resolve the order with an indexed
        query instead of a live upstream scan (#219).
        """
        from models import AcmeClientOrder
        try:
            row = AcmeClientOrder.query.filter_by(
                is_proxy_order=True, upstream_order_url=order_url
            ).first()
            if row and row.certificate_url != cert_url:
                row.certificate_url = cert_url
                db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.warning(f"ACME proxy: failed to persist certificate URL: {exc}")

    def _find_order_for_certificate(self, cert_url: str):
        """Match a proxy order to the upstream certificate download URL.

        Fast path: indexed lookup on the persisted certificate_url. The
        upstream scan only remains as a fallback for orders that predate the
        persistence (#219) and skips rows that already carry a URL.
        """
        from models import AcmeClientOrder

        order = AcmeClientOrder.query.filter_by(
            is_proxy_order=True, certificate_url=cert_url
        ).first()
        if order:
            return order

        pending_orders = AcmeClientOrder.query.filter(
            AcmeClientOrder.is_proxy_order == True,
            AcmeClientOrder.status == 'pending',
            AcmeClientOrder.certificate_url.is_(None),
        ).all()
        for order in pending_orders:
            if not order.upstream_order_url:
                continue
            try:
                resp = self._post_with_account(order.upstream_order_url, "")
                if resp.status_code != 200:
                    continue
                upstream_cert = resp.json().get('certificate')
                if upstream_cert == cert_url:
                    return order
            except Exception as exc:
                logger.warning(
                    "ACME proxy: failed to resolve order for cert URL: %s", exc
                )
        return None

    @staticmethod
    def _urls_share_ca(url1, url2):
        """Check if two URLs belong to the same CA (same host)."""
        from urllib.parse import urlparse
        return urlparse(url1).netloc == urlparse(url2).netloc
    
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

    def get_order(self, order_id_b64):
        """Get order status (POST-as-GET)"""
        order_url = self._decode_proxy_id(order_id_b64)
        
        resp = self._post_with_account(order_url, "")
        if resp.status_code != 200:
            raise Exception(f"Upstream error: {resp.text}")
            
        order = resp.json()
        
        # Rewrite URLs
        order['finalize'] = f"{self.base_url}/order/{order_id_b64}/finalize"
        if 'certificate' in order:
            cert_url = order['certificate']
            self._persist_certificate_url(order_url, cert_url)
            cert_id = base64.urlsafe_b64encode(cert_url.encode()).rstrip(b'=').decode()
            order['certificate'] = f"{self.base_url}/cert/{cert_id}"

        # Rewrite authorization URLs
        if 'authorizations' in order:
            proxy_authzs = []
            for authz_url in order['authorizations']:
                authz_id = base64.urlsafe_b64encode(authz_url.encode()).rstrip(b'=').decode()
                proxy_authzs.append(f"{self.base_url}/authz/{authz_id}")
            order['authorizations'] = proxy_authzs
            
        return order

    def finalize_order(self, order_id_b64, csr_pem, requester_account_id=None,
                       requester_thumbprint=None):
        """Proxy finalize.

        If requester_account_id is provided, verify it matches the local
        AcmeClientOrder.account_id (set when the order was created from this
        same client's JWK thumbprint). Mismatch → PermissionError → ACME 403.
        When client_jwk_thumbprint is stored on the order, the finalize JWK
        must match even if no local account was registered.
        """
        from models import AcmeClientOrder

        order_url = self._decode_proxy_id(order_id_b64)

        local_order = AcmeClientOrder.query.filter_by(
            upstream_order_url=order_url, is_proxy_order=True
        ).first()
        if local_order:
            # Fail closed: an order bound to an owner must never finalize when
            # the requester identity could not be established at all.
            owner_bound = bool(local_order.account_id or local_order.client_jwk_thumbprint)
            if owner_bound and not requester_account_id and not requester_thumbprint:
                logger.warning(
                    "ACME proxy finalize: no requester identity for owned order %s",
                    local_order.id,
                )
                raise PermissionError("Order does not belong to this account")
            if requester_account_id and local_order.account_id and \
                    local_order.account_id != requester_account_id:
                logger.warning(
                    "ACME proxy finalize: account %s tried to finalize order owned by %s",
                    requester_account_id, local_order.account_id
                )
                raise PermissionError("Order does not belong to this account")
            if local_order.client_jwk_thumbprint and requester_thumbprint and \
                    local_order.client_jwk_thumbprint != requester_thumbprint:
                logger.warning(
                    "ACME proxy finalize: JWK thumbprint mismatch for order %s",
                    local_order.id,
                )
                raise PermissionError("Order does not belong to this account")
        
        # ACME expects CSR in base64url-encoded DER (without headers) inside JSON
        # We assume csr_pem comes from our API handler which decoded the client's JWS
        # Client sends base64url(DER). API handler decodes to PEM?
        # Wait, standard ACME API handler usually extracts payload. payload['csr'] is base64url string.
        # We can just pass that string along!
        
        # Actually our API handler parses everything. We should pass the raw CSR string if possible.
        # But let's assume we get PEM and need to convert back to DER B64URL for upstream.
        
        # Convert PEM to DER
        from cryptography import x509
        csr = x509.load_pem_x509_csr(csr_pem.encode(), default_backend())
        csr_der = csr.public_bytes(serialization.Encoding.DER)
        csr_b64 = base64.urlsafe_b64encode(csr_der).rstrip(b'=').decode()
        
        payload = {"csr": csr_b64}
        
        # The finalize URL is usually order_url/finalize, but we should look it up from the order object
        # But here we just use the ID which IS the order URL (from previous steps)
        # Wait, the finalize endpoint on upstream is provided in the order object.
        # We need to fetch the order first to get the REAL upstream finalize URL?
        # Or we assume standard ACME URL structure?
        # Better: Fetch order, get finalize URL.
        
        order_resp = self._post_with_account(order_url, "")
        order_data = order_resp.json()
        finalize_url = order_data['finalize']
        
        # Call finalize
        resp = self._post_with_account(finalize_url, payload)
        
        if resp.status_code != 200:
             raise Exception(f"Upstream finalize error: {resp.text}")
             
        order = resp.json()
        
        # Rewrite URLs
        order['finalize'] = f"{self.base_url}/order/{order_id_b64}/finalize"
        if 'certificate' in order:
            cert_url = order['certificate']
            self._persist_certificate_url(order_url, cert_url)
            cert_id = base64.urlsafe_b64encode(cert_url.encode()).rstrip(b'=').decode()
            order['certificate'] = f"{self.base_url}/cert/{cert_id}"

        # Rewrite authorization URLs
        if 'authorizations' in order:
            proxy_authzs = []
            for authz_url in order['authorizations']:
                authz_id = base64.urlsafe_b64encode(authz_url.encode()).rstrip(b'=').decode()
                proxy_authzs.append(f"{self.base_url}/authz/{authz_id}")
            order['authorizations'] = proxy_authzs

        return order

    def get_certificate(self, cert_id_b64):
        """Proxy certificate download with DNS cleanup and storage"""
        from models import AcmeClientOrder, Certificate
        from services.acme.dns_providers import create_provider
        from services.cert_service import CertificateService
        
        cert_url = self._decode_proxy_id(cert_id_b64)
        
        resp = self._post_with_account(cert_url, "")

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
                    descr = cn[0].value if cn else "Let's Encrypt Certificate"
                    
                    logger.info(f"[ACME Proxy] Storing LE certificate: {descr}")
                    
                    # Import the certificate with source='letsencrypt'
                    stored_cert = CertificateService.import_certificate(
                        descr=descr,
                        cert_pem=first_cert,
                        chain_pem=chain,
                        source='letsencrypt',
                        username='acme_proxy'
                    )
                    logger.info(f"[ACME Proxy] Certificate stored with ID: {stored_cert.id}")
            except Exception as e:
                # Log but don't fail - cert was obtained
                logger.error(f"[ACME Proxy] Error storing certificate: {e}")
            
            # Link certificate to order; DNS cleanup runs in the background so
            # the client is not blocked on DNS-provider API latency (#218).
            order = self._find_order_for_certificate(cert_url)

            if order:
                records_to_cleanup = []
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
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Failed during certificate cleanup: {e}")

                if records_to_cleanup:
                    import threading
                    from flask import current_app
                    app = current_app._get_current_object()

                    thread = threading.Thread(
                        target=self._bg_cleanup_dns_records,
                        args=(app, records_to_cleanup)
                    )
                    thread.name = "ACMEProxy-DNS-Cleanup"
                    thread.daemon = True
                    thread.start()
        
        # Cert response is PEM stream usually
        return response_body, resp.headers.get('Content-Type', 'application/pem-certificate-chain'), link_header
