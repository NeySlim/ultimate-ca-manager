
"""
ACME Proxy Service
Acts as a gateway between internal ACME clients and upstream ACME providers (Let's Encrypt)
"""
import json
import base64
import time
import requests
import secrets
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, Union

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
import josepy as jose

from models import db, SystemConfig, DnsProvider

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
            db.session.commit()
            
        return private_key, jose.JWKRSA(key=private_key.public_key())

    def _get_upstream_account_url(self):
        """Get or register account URL"""
        url_config = SystemConfig.query.filter_by(key='acme.proxy.account_url').first()
        if url_config:
            return url_config.value
        
        # Register if not exists
        return self._register_upstream_account()

    def _register_upstream_account(self):
        """Register account with upstream"""
        self._ensure_directory()
        new_account_url = self.directory['newAccount']
        
        # Use a dummy email that passes validation
        # In production, this should be configurable
        # We try to use the system FQDN to look legitimate
        from config.settings import get_config
        conf = get_config()
        fqdn = conf.FQDN or "ucm.local"
        
        payload = {
            "termsOfServiceAgreed": True,
            "contact": [f"mailto:admin@{fqdn}"] 
        }
        
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
            db.session.commit()
            return loc
        else:
            raise Exception(f"Failed to register upstream account: {resp.text}")

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
        
        # Store order in database for tracking
        order = AcmeClientOrder(
            domains=json.dumps(domains),
            email='proxy@ucm.local',
            environment='staging' if 'staging' in self.upstream_directory_url else 'production',
            challenge_type='dns-01',
            status='pending',
            order_url=upstream_location,
            upstream_order_url=upstream_location,
            is_proxy_order=True,
            client_jwk_thumbprint=client_thumbprint,
            # Use first domain's provider
            dns_provider_id=list(domain_providers.values())[0].id if domain_providers else None
        )
        db.session.add(order)
        db.session.commit()
        
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
        """Proxy authz fetch"""
        # Fix padding
        authz_id_b64 += '=' * (4 - len(authz_id_b64) % 4)
        authz_url = base64.urlsafe_b64decode(authz_id_b64).decode()
        
        # Authz fetch is usually a GET (POST-as-GET in ACME v2)
        # RFC 8555: "Clients MUST NOT send a JWS body ... for GET requests" -> Wait, ACME uses POST-as-GET
        resp = self._post_jws(authz_url, "", kid=self.account_url)
        
        if resp.status_code != 200:
             return None
             
        authz = resp.json()
        
        # Extract identifier (domain)
        identifier = authz.get('identifier', {})
        
        # Rewrite challenges
        proxy_challenges = []
        for chall in authz['challenges']:
            chall_url = chall['url']
            chall_id = base64.urlsafe_b64encode(chall_url.encode()).rstrip(b'=').decode()
            
            chall['url'] = f"{self.base_url}/acme/proxy/challenge/{chall_id}"
            # TOKEN IS PRESERVED! Crucial for passthrough.
            proxy_challenges.append(chall)
            
        authz['challenges'] = proxy_challenges
        return authz, identifier

    def respond_challenge(self, chall_id_b64, authz_id_b64=None):
        """Proxy challenge response with automatic DNS setup"""
        import hashlib
        from api.v2.acme_domains import find_provider_for_domain
        from services.acme.dns_providers import create_provider
        from models import DnsProvider, AcmeClientOrder
        
        chall_id_b64_padded = chall_id_b64 + '=' * (4 - len(chall_id_b64) % 4)
        chall_url = base64.urlsafe_b64decode(chall_id_b64_padded).decode()
        
        # First, fetch the challenge to get token and type
        # We need to find the authz to get the domain
        # The challenge URL contains hints about the authz
        
        # Extract token from upstream challenge
        # Fetch current challenge state
        resp = self._post_jws(chall_url, "", kid=self.account_url)
        if resp.status_code != 200:
            raise Exception(f"Failed to fetch challenge: {resp.text}")
        
        challenge_data = resp.json()
        token = challenge_data.get('token')
        challenge_type = challenge_data.get('type')
        
        # Only handle dns-01 challenges
        if challenge_type == 'dns-01' and token:
            # Calculate key authorization
            # key_authz = token + "." + base64url(sha256(JWK_thumbprint))
            # The thumbprint is of OUR upstream account key
            jwk_thumbprint = self._get_account_thumbprint()
            key_authz = f"{token}.{jwk_thumbprint}"
            
            # TXT record value = base64url(sha256(key_authz))
            digest = hashlib.sha256(key_authz.encode()).digest()
            txt_value = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
            
            # Find the domain from the authz URL pattern
            # The authz URL is typically: .../acme/authz-v3/{authz_id}
            # We stored order info, find matching order by challenge URL prefix
            # For now, extract domain from challenge URL pattern or use order lookup
            
            # Get domain from DB order (we stored it in new_order)
            # Find order by upstream URL pattern
            order = AcmeClientOrder.query.filter(
                AcmeClientOrder.is_proxy_order == True,
                AcmeClientOrder.status == 'pending'
            ).order_by(AcmeClientOrder.created_at.desc()).first()
            
            if order and order.domains_list:
                domain = order.domains_list[0].lstrip('*.')
                
                # Find DNS provider for this domain
                provider_model = find_provider_for_domain(domain)
                if provider_model:
                    try:
                        # Create DNS provider instance
                        credentials = json.loads(provider_model.credentials) if provider_model.credentials else {}
                        provider = create_provider(provider_model.provider_type, credentials)
                        
                        # Create TXT record
                        record_name = f"_acme-challenge.{domain}"
                        provider.create_txt_record(domain, record_name, txt_value)
                        
                        # Store record info for cleanup
                        records = json.loads(order.dns_records_created) if order.dns_records_created else []
                        records.append({
                            'domain': domain,
                            'record_name': record_name,
                            'value': txt_value,
                            'provider_id': provider_model.id
                        })
                        order.dns_records_created = json.dumps(records)
                        db.session.commit()
                        
                        # Wait for DNS propagation (configurable, default 10s)
                        time.sleep(10)
                        
                    except Exception as e:
                        raise Exception(f"Failed to create DNS record: {e}")
        
        # Now trigger upstream validation
        resp = self._post_jws(chall_url, {}, kid=self.account_url)
        
        if resp.status_code != 200:
            raise Exception(f"Upstream challenge error: {resp.text}")
             
        chall = resp.json()
        chall['url'] = f"{self.base_url}/acme/proxy/challenge/{chall_id_b64}"
        return chall
    
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
        """Proxy certificate download with DNS cleanup"""
        from models import AcmeClientOrder
        from services.acme.dns_providers import create_provider
        
        cert_id_b64_padded = cert_id_b64 + '=' * (4 - len(cert_id_b64) % 4)
        cert_url = base64.urlsafe_b64decode(cert_id_b64_padded).decode()
        
        resp = self._post_jws(cert_url, "", kid=self.account_url)
        
        if resp.status_code == 200:
            # Certificate obtained successfully - cleanup DNS records
            # Find the order and cleanup
            order = AcmeClientOrder.query.filter(
                AcmeClientOrder.is_proxy_order == True,
                AcmeClientOrder.status == 'pending'
            ).order_by(AcmeClientOrder.created_at.desc()).first()
            
            if order and order.dns_records_created:
                try:
                    records = json.loads(order.dns_records_created)
                    for record in records:
                        provider_model = DnsProvider.query.get(record['provider_id'])
                        if provider_model:
                            credentials = json.loads(provider_model.credentials) if provider_model.credentials else {}
                            provider = create_provider(provider_model.provider_type, credentials)
                            try:
                                provider.delete_txt_record(record['domain'], record['record_name'], record['value'])
                            except Exception as e:
                                # Log but don't fail - record might already be deleted
                                pass
                    
                    # Update order status
                    order.status = 'valid'
                    order.dns_records_created = None  # Clear after cleanup
                    db.session.commit()
                except Exception as e:
                    # Log cleanup error but still return cert
                    pass
        
        # Cert response is PEM stream usually
        return resp.content, resp.headers.get('Content-Type', 'application/pem-certificate-chain')
