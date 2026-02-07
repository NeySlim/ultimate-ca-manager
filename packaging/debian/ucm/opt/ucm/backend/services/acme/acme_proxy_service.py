
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

from models import db, SystemConfig

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

    def new_order(self, identifiers, not_before=None, not_after=None):
        """Proxy new-order"""
        self._ensure_directory()
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
        
        # Rewrite challenges
        proxy_challenges = []
        for chall in authz['challenges']:
            chall_url = chall['url']
            chall_id = base64.urlsafe_b64encode(chall_url.encode()).rstrip(b'=').decode()
            
            chall['url'] = f"{self.base_url}/acme/proxy/challenge/{chall_id}"
            # TOKEN IS PRESERVED! Crucial for passthrough.
            proxy_challenges.append(chall)
            
        authz['challenges'] = proxy_challenges
        return authz

    def respond_challenge(self, chall_id_b64):
        """Proxy challenge response"""
        chall_id_b64 += '=' * (4 - len(chall_id_b64) % 4)
        chall_url = base64.urlsafe_b64decode(chall_id_b64).decode()
        
        # Trigger upstream validation
        # Payload is usually empty {}
        resp = self._post_jws(chall_url, {}, kid=self.account_url)
        
        if resp.status_code != 200:
             raise Exception(f"Upstream challenge error: {resp.text}")
             
        chall = resp.json()
        chall['url'] = f"{self.base_url}/acme/proxy/challenge/{chall_id_b64}"
        return chall

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
        """Proxy certificate download"""
        cert_id_b64 += '=' * (4 - len(cert_id_b64) % 4)
        cert_url = base64.urlsafe_b64decode(cert_id_b64).decode()
        
        resp = self._post_jws(cert_url, "", kid=self.account_url)
        # Cert response is PEM stream usually
        return resp.content, resp.headers['Content-Type']
