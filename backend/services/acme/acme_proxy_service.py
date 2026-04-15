
"""
ACME Proxy Service
Acts as a gateway between internal ACME clients and upstream ACME providers (Let's Encrypt)
"""
import json
import base64
import time
import requests
import secrets
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, Union

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import josepy as jose

from models import db, SystemConfig, DnsProvider

logger = logging.getLogger(__name__)

class AcmeProxyService:
    # Default upstream (Let's Encrypt Staging for safety by default, user can change)
    DEFAULT_UPSTREAM = "https://acme-staging-v02.api.letsencrypt.org/directory"
    # Production: https://acme-v02.api.letsencrypt.org/directory
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.upstream_directory_url = self._get_upstream_url()
        self.directory = None
        self.nonces = []
        
        # Load or create upstream account key
        self.private_key, self.account_key = self._load_or_create_account_key()
        self.account_url = self._get_upstream_account_url()

    def _get_upstream_url(self) -> str:
        """Get configured upstream URL"""
        config = SystemConfig.query.filter_by(key='acme.proxy.upstream_url').first()
        return config.value if config else self.DEFAULT_UPSTREAM

    def _load_or_create_account_key(self):
        """Load upstream account private key"""
        config = SystemConfig.query.filter_by(key='acme.proxy.account_key').first()
        if config:
            # Load from DB
            private_key = serialization.load_pem_private_key(
                config.value.encode(),
                password=None,
                backend=default_backend()
            )
        else:
            # Generate new key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            # Save to DB
            pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode()
            
            db.session.add(SystemConfig(
                key='acme.proxy.account_key',
                value=pem,
                description="Private key for ACME Proxy upstream account"
            ))
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to save ACME proxy account key: {e}")
                raise
            
        return private_key, jose.JWKRSA(key=private_key.public_key())

    def _get_upstream_account_url(self):
        """Get or register account URL"""
        url_config = SystemConfig.query.filter_by(key='acme.proxy.account_url').first()
        if url_config:
            return url_config.value
        
        # Register if not exists
        return self._register_upstream_account()

    def _register_upstream_account(self):
        """Register account with upstream, with optional EAB support"""
        self._ensure_directory()
        new_account_url = self.directory['newAccount']
        
        from config.settings import get_config
        conf = get_config()
        fqdn = conf.FQDN or "ucm.local"
        
        payload = {
            "termsOfServiceAgreed": True,
            "contact": [f"mailto:admin@{fqdn}"] 
        }
        
        # Add External Account Binding if configured (required by HARICA, etc.)
        eab_kid_config = SystemConfig.query.filter_by(key='acme.proxy.eab_kid').first()
        eab_hmac_config = SystemConfig.query.filter_by(key='acme.proxy.eab_hmac_key').first()
        if eab_kid_config and eab_hmac_config:
            eab_kid = eab_kid_config.value
            eab_hmac_key = eab_hmac_config.value
            payload["externalAccountBinding"] = self._build_eab(
                eab_kid, eab_hmac_key, new_account_url
            )
            logger.info(f"Registering upstream account with EAB (kid={eab_kid})")
        else:
            # Check if upstream requires EAB
            meta = self.directory.get('meta', {})
            if meta.get('externalAccountRequired'):
                raise RuntimeError(
                    "Upstream CA requires External Account Binding (EAB). "
                    "Configure acme.proxy.eab_kid and acme.proxy.eab_hmac_key in Settings > ACME."
                )
        
        resp = self._post_jws(new_account_url, payload)
        
        if resp.status_code in [200, 201]:
            loc = resp.headers['Location']
            
            # Check if exists
            config = SystemConfig.query.filter_by(key='acme.proxy.account_url').first()
            if config:
                config.value = loc
            else:
                db.session.add(SystemConfig(
                    key='acme.proxy.account_url',
                    value=loc,
                    description="Upstream ACME Account URL"
                ))
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to save upstream ACME account URL: {e}")
                raise
            return loc
        else:
            raise RuntimeError(f"Failed to register upstream account: {resp.text}")

    def _ensure_directory(self):
        """Fetch upstream directory"""
        if not self.directory:
            resp = requests.get(self.upstream_directory_url)
            resp.raise_for_status()
            self.directory = resp.json()

    def _get_nonce(self):
        """Get nonce from upstream"""
        self._ensure_directory()
        resp = requests.head(self.directory['newNonce'])
        return resp.headers['Replay-Nonce']

    def _post_jws(self, url: str, payload: Union[Dict, str], kid: str = None) -> requests.Response:
        """Sign and post JWS to upstream"""
        nonce = self._get_nonce()
        
        # Prepare JWS header
        if kid:
            protected = {"alg": "RS256", "kid": kid, "nonce": nonce, "url": url}
        else:
            # New account uses JWK
            protected = {"alg": "RS256", "jwk": self.account_key.to_json(), "nonce": nonce, "url": url}
            
        if payload == "":
            payload_json = b""
        else:
            payload_json = json.dumps(payload).encode('utf-8')
            
        protected_json = json.dumps(protected).encode('utf-8')
        
        # Sign
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        
        payload_b64 = base64.urlsafe_b64encode(payload_json).rstrip(b'=').decode('utf-8')
        protected_b64 = base64.urlsafe_b64encode(protected_json).rstrip(b'=').decode('utf-8')
        
        signing_input = f"{protected_b64}.{payload_b64}".encode('utf-8')
        
        sig = self.private_key.sign(
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        
        data = {
            "protected": protected_b64,
            "payload": payload_b64,
            "signature": base64.urlsafe_b64encode(sig).rstrip(b'=').decode('utf-8')
        }
        
        headers = {"Content-Type": "application/jose+json"}
        return requests.post(url, json=data, headers=headers)

    # --- Proxy Methods ---

    def get_directory(self):
        """Return proxy directory"""
        self._ensure_directory()
        # Map upstream keys to proxy URLs
        return {
            "newNonce": f"{self.base_url}/acme/proxy/new-nonce",
            "newAccount": f"{self.base_url}/acme/proxy/new-account",
            "newOrder": f"{self.base_url}/acme/proxy/new-order",
            "revokeCert": f"{self.base_url}/acme/proxy/revoke-cert",
            "keyChange": f"{self.base_url}/acme/proxy/key-change",
            "meta": self.directory.get('meta', {})
        }

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
            # Remove wildcard prefix for lookup
            lookup_domain = domain.lstrip('*.')
            provider = find_provider_for_domain(lookup_domain)
            if not provider:
                raise Exception(f"No DNS provider configured for domain: {domain}. Configure it in ACME > Domains.")
            domain_providers[domain] = provider
        
        # Forward to upstream Let's Encrypt
        payload = {
            "identifiers": identifiers,
            "notBefore": not_before.isoformat() + 'Z' if not_before else None,
            "notAfter": not_after.isoformat() + 'Z' if not_after else None
        }
        # Filter None
        payload = {k: v for k, v in payload.items() if v is not None}
        
        resp = self._post_jws(self.directory['newOrder'], payload, kid=self.account_url)
        
        if resp.status_code != 201:
            raise Exception(f"Upstream error: {resp.text}")
            
        upstream_order = resp.json()
        upstream_location = resp.headers['Location']
        
        # Get upstream authz URLs for later matching
        upstream_authz_urls = upstream_order.get('authorizations', [])
        
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
            proxy_authzs.append(f"{self.base_url}/acme/proxy/authz/{authz_id}")
            
        upstream_order['authorizations'] = proxy_authzs
        upstream_order['finalize'] = f"{self.base_url}/acme/proxy/order/{order_id}/finalize"
        
        return upstream_order, order_id

    def get_authz(self, authz_id_b64):
        """Proxy authz fetch — only exposes dns-01 challenges.
        
        The proxy can only handle dns-01 validation (via DNS provider).
        http-01 and tls-alpn-01 require the upstream CA to reach the client
        directly, which doesn't work through a proxy.
        """
        # Fix padding
        authz_id_b64 += '=' * (4 - len(authz_id_b64) % 4)
        authz_url = base64.urlsafe_b64decode(authz_id_b64).decode()
        
        resp = self._post_jws(authz_url, "", kid=self.account_url)
        
        if resp.status_code != 200:
            logger.error(f"Upstream authz fetch failed: {resp.status_code} {resp.text}")
            return None
             
        authz = resp.json()
        
        # Extract identifier (domain)
        identifier = authz.get('identifier', {})
        
        # Filter to dns-01 only — the proxy handles DNS record creation
        # automatically. http-01/tls-alpn-01 cannot work through a proxy
        # because the upstream CA needs direct access to the client.
        proxy_challenges = []
        for chall in authz.get('challenges', []):
            if chall.get('type') != 'dns-01':
                continue
            chall_url = chall['url']
            chall_id = base64.urlsafe_b64encode(chall_url.encode()).rstrip(b'=').decode()
            chall['url'] = f"{self.base_url}/acme/proxy/challenge/{chall_id}"
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
        """Proxy challenge response with asynchronous automatic DNS setup"""
        import hashlib
        from api.v2.acme_domains import find_provider_for_domain
        from models import AcmeClientOrder
        
        chall_id_b64_padded = chall_id_b64 + '=' * (4 - len(chall_id_b64) % 4)
        chall_url = base64.urlsafe_b64decode(chall_id_b64_padded).decode()
        
        # Fetch the challenge to get token and type
        resp = self._post_jws(chall_url, "", kid=self.account_url)
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch challenge: {resp.text}")
        
        challenge_data = resp.json()
        token = challenge_data.get('token')
        challenge_type = challenge_data.get('type')
        
        if challenge_type != 'dns-01':
            raise RuntimeError(
                f"Unsupported challenge type: {challenge_type}. "
                "The ACME proxy only supports dns-01 validation."
            )
        
        if not token:
            raise RuntimeError("Challenge has no token")
        
        # Calculate key authorization using PROXY's account thumbprint
        # (the proxy's account is what the upstream CA knows about)
        jwk_thumbprint = self._get_account_thumbprint()
        key_authz = f"{token}.{jwk_thumbprint}"
        
        # Find the proxy order that contains this challenge's authz URL
        order = self._find_order_for_challenge(chall_url, AcmeClientOrder)
        if not order:
            raise RuntimeError("No pending proxy order found for this challenge.")

        domain = order.domains_list[0].lstrip('*.')
        
        # Verify DNS provider exists BEFORE going background
        provider_info = find_provider_for_domain(domain)
        if not provider_info:
            raise RuntimeError(f"No DNS provider configured for domain: {domain}")

        # Move blocking DNS setup and upstream validation to background thread
        import threading
        from flask import current_app
        # We need to pass required info to the background thread
        app = current_app._get_current_object()
        
        thread = threading.Thread(
            target=self._bg_respond_challenge,
            args=(app, chall_url, key_authz, domain, order.id)
        )
        thread.name = f"ACMEProxy-DNS-{domain}"
        thread.daemon = True
        thread.start()
        
        # Return immediate "processing" status (RFC 8555 allows returning the challenge 
        # as it is while it's being processed)
        challenge_data['status'] = 'processing'
        challenge_data['url'] = f"{self.base_url}/acme/proxy/challenge/{chall_id_b64}"
        
        # Build Link header for the response
        link_header = None
        upstream_link = resp.headers.get('Link')
        if upstream_link:
            import re
            match = re.search(r'<([^>]+)>', upstream_link)
            if match:
                authz_url = match.group(1)
                authz_id = base64.urlsafe_b64encode(authz_url.encode()).rstrip(b'=').decode()
                link_header = f'<{self.base_url}/acme/proxy/authz/{authz_id}>;rel="up"'
        
        return challenge_data, link_header

    def _bg_respond_challenge(self, app, chall_url, key_authz, domain, order_id):
        """Background task for DNS setup and upstream validation trigger"""
        import hashlib
        import time
        from api.v2.acme_domains import find_provider_for_domain
        from services.acme.dns_providers import create_provider
        from models import AcmeClientOrder
        
        with app.app_context():
            try:
                # Calculate TXT value
                digest = hashlib.sha256(key_authz.encode()).digest()
                txt_value = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
                
                # Get fresh order and provider
                order = AcmeClientOrder.query.get(order_id)
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
                
                # Wait for DNS propagation
                logger.info(f"[ACME Proxy BG] Waiting 30s for propagation for {domain}...")
                time.sleep(30)
                
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
                resp = self._post_jws(chall_url, payload, kid=self.account_url)
                
                if resp.status_code != 200:
                    logger.error(f"[ACME Proxy BG] Upstream challenge validation error: {resp.text}")
                else:
                    logger.info(f"[ACME Proxy BG] Upstream challenge validation triggered successfully for {domain}")
                    
            except Exception as e:
                logger.error(f"[ACME Proxy BG] Error in background challenge setup: {e}", exc_info=True)
                db.session.rollback()
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
    
    @staticmethod
    def _urls_share_ca(url1, url2):
        """Check if two URLs belong to the same CA (same host)."""
        from urllib.parse import urlparse
        return urlparse(url1).netloc == urlparse(url2).netloc
    
    def _get_account_thumbprint(self):
        """Get JWK thumbprint of our upstream account key"""
        import hashlib
        # The thumbprint is SHA-256 of the canonical JWK
        jwk = self.account_key.to_json()
        # Canonical form for RSA: {"e":"...","kty":"RSA","n":"..."}
        canonical = json.dumps({
            "e": jwk["e"],
            "kty": jwk["kty"],
            "n": jwk["n"]
        }, separators=(',', ':'), sort_keys=True)
        digest = hashlib.sha256(canonical.encode()).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b'=').decode()

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
        jwk_json = json.dumps(self.account_key.to_json(), separators=(',', ':'), sort_keys=True)
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
        order_id_b64_padded = order_id_b64 + '=' * (4 - len(order_id_b64) % 4)
        order_url = base64.urlsafe_b64decode(order_id_b64_padded).decode()
        
        resp = self._post_jws(order_url, "", kid=self.account_url)
        if resp.status_code != 200:
            raise Exception(f"Upstream error: {resp.text}")
            
        order = resp.json()
        
        # Rewrite URLs
        order['finalize'] = f"{self.base_url}/acme/proxy/order/{order_id_b64}/finalize"
        if 'certificate' in order:
            cert_url = order['certificate']
            cert_id = base64.urlsafe_b64encode(cert_url.encode()).rstrip(b'=').decode()
            order['certificate'] = f"{self.base_url}/acme/proxy/cert/{cert_id}"

        return order

    def finalize_order(self, order_id_b64, csr_pem):
        """Proxy finalize"""
        order_id_b64 += '=' * (4 - len(order_id_b64) % 4)
        order_url = base64.urlsafe_b64decode(order_id_b64).decode()
        
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
        
        order_resp = self._post_jws(order_url, "", kid=self.account_url)
        order_data = order_resp.json()
        finalize_url = order_data['finalize']
        
        # Call finalize
        resp = self._post_jws(finalize_url, payload, kid=self.account_url)
        
        if resp.status_code != 200:
             raise Exception(f"Upstream finalize error: {resp.text}")
             
        order = resp.json()
        
        # Rewrite URLs
        order['finalize'] = f"{self.base_url}/acme/proxy/order/{order_id_b64}/finalize"
        if 'certificate' in order:
            cert_url = order['certificate']
            cert_id = base64.urlsafe_b64encode(cert_url.encode()).rstrip(b'=').decode()
            order['certificate'] = f"{self.base_url}/acme/proxy/cert/{cert_id}"
            
        return order

    def get_certificate(self, cert_id_b64):
        """Proxy certificate download with DNS cleanup and storage"""
        from models import AcmeClientOrder, Certificate
        from services.acme.dns_providers import create_provider
        from services.cert_service import CertificateService
        
        cert_id_b64_padded = cert_id_b64 + '=' * (4 - len(cert_id_b64) % 4)
        cert_url = base64.urlsafe_b64decode(cert_id_b64_padded).decode()
        
        resp = self._post_jws(cert_url, "", kid=self.account_url)
        
        # Extract Link header from upstream (contains issuer cert URL)
        link_header = resp.headers.get('Link')
        
        if resp.status_code == 200:
            # Certificate obtained successfully
            cert_pem = resp.content.decode('utf-8') if isinstance(resp.content, bytes) else resp.content
            
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
            
            # Cleanup DNS records and link certificate to order
            from models import AcmeClientOrder, DnsProvider
            order = AcmeClientOrder.query.filter(
                AcmeClientOrder.is_proxy_order == True,
                AcmeClientOrder.status == 'pending'
            ).order_by(AcmeClientOrder.created_at.desc()).first()
            
            if order:
                try:
                    # Link certificate to order
                    if stored_cert:
                        order.certificate_id = stored_cert.id
                    
                    # Cleanup DNS records
                    if order.dns_records_created:
                        records = json.loads(order.dns_records_created)
                        for record in records:
                            provider_model = DnsProvider.query.get(record['provider_id'])
                            if provider_model:
                                credentials = json.loads(provider_model.credentials) if provider_model.credentials else {}
                                provider = create_provider(provider_model.provider_type, credentials)
                                try:
                                    logger.info(f"[ACME Proxy] Cleaning up DNS record: {record['record_name']} in zone {record['domain']}")
                                    provider.delete_txt_record(record['domain'], record['record_name'])
                                except Exception as e:
                                    logger.warning(f"Failed to cleanup DNS record {record.get('record_name')}: {e}")
                    
                    # Update order status
                    order.status = 'valid'
                    order.dns_records_created = None  # Clear after cleanup
                    try:
                        db.session.commit()
                    except Exception as e:
                        db.session.rollback()
                        logger.error(f"Failed to update order status: {e}")
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Failed during certificate cleanup: {e}")
        
        # Cert response is PEM stream usually
        return resp.content, resp.headers.get('Content-Type', 'application/pem-certificate-chain'), link_header
