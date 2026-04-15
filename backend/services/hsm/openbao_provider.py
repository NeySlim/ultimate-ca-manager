"""
OpenBao / HashiCorp Vault Transit Secrets Engine HSM Provider

Uses the Transit Secrets Engine API for key management and cryptographic operations.
Compatible with both OpenBao and HashiCorp Vault.

Docs: https://openbao.org/docs/secrets/transit/
"""

import base64
import hashlib
import logging
from typing import Dict, List, Optional, Any

import requests

from services.hsm.base_provider import (
    BaseHsmProvider, HsmKeyInfo,
    HsmConnectionError, HsmOperationError, HsmKeyNotFoundError, HsmConfigError
)

logger = logging.getLogger(__name__)

# UCM algorithm -> OpenBao Transit key type
ALGORITHM_TO_TRANSIT = {
    'RSA-2048': ('rsa-2048', 'asymmetric'),
    'RSA-3072': ('rsa-3072', 'asymmetric'),
    'RSA-4096': ('rsa-4096', 'asymmetric'),
    'EC-P256': ('ecdsa-p256', 'asymmetric'),
    'EC-P384': ('ecdsa-p384', 'asymmetric'),
    'EC-P521': ('ecdsa-p521', 'asymmetric'),
    'AES-256': ('aes256-gcm96', 'symmetric'),
}

# OpenBao Transit key type -> UCM algorithm (reverse mapping)
TRANSIT_TO_ALGORITHM = {
    'rsa-2048': 'RSA-2048',
    'rsa-3072': 'RSA-3072',
    'rsa-4096': 'RSA-4096',
    'ecdsa-p256': 'EC-P256',
    'ecdsa-p384': 'EC-P384',
    'ecdsa-p521': 'EC-P521',
    'aes256-gcm96': 'AES-256',
    'aes128-gcm96': 'AES-128',
    'ed25519': 'Ed25519',
    'chacha20-poly1305': 'ChaCha20',
}

# Hash algorithm for signing based on key type
SIGN_HASH_ALGORITHM = {
    'RSA-2048': 'sha2-256',
    'RSA-3072': 'sha2-384',
    'RSA-4096': 'sha2-512',
    'EC-P256': 'sha2-256',
    'EC-P384': 'sha2-384',
    'EC-P521': 'sha2-512',
}

# Signature algorithm name for Transit API
SIGN_ALGORITHM = {
    'RSA-2048': 'pkcs1v15',
    'RSA-3072': 'pkcs1v15',
    'RSA-4096': 'pkcs1v15',
}


def is_available() -> bool:
    """OpenBao provider uses requests — always available"""
    return True


class OpenBaoProvider(BaseHsmProvider):
    """
    OpenBao / Vault Transit Secrets Engine provider.

    Config:
        url:             OpenBao server URL (e.g. https://openbao.example.com:8200)
        token:           Authentication token
        mount_path:      Transit engine mount path (default: transit)
        namespace:       Optional namespace (enterprise / OpenBao namespaces)
        tls_skip_verify: Skip TLS certificate verification (default: False)
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._url = config.get('url', '').rstrip('/')
        self._token = config.get('token', '')
        self._mount = config.get('mount_path', 'transit').strip('/')
        self._namespace = config.get('namespace', '')
        self._verify_tls = not config.get('tls_skip_verify', False)
        self._session: Optional[requests.Session] = None

        if not self._url:
            raise HsmConfigError('OpenBao URL is required')
        if not self._token:
            raise HsmConfigError('OpenBao token is required')

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _api(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """Make an API call to OpenBao/Vault"""
        if not self._session:
            raise HsmConnectionError('Not connected')

        url = f'{self._url}/v1/{self._mount}/{path}'
        try:
            resp = self._session.request(method, url, **kwargs)
            if resp.status_code == 404:
                return {}
            resp.raise_for_status()
            if resp.status_code == 204:
                return {}
            return resp.json()
        except requests.ConnectionError as e:
            raise HsmConnectionError(f'Connection failed: {e}')
        except requests.HTTPError as e:
            body = ''
            try:
                body = e.response.json().get('errors', [e.response.text])
            except Exception:
                body = e.response.text
            raise HsmOperationError(f'API error ({e.response.status_code}): {body}')

    def _sys_api(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """Make a sys API call (outside transit mount)"""
        if not self._session:
            raise HsmConnectionError('Not connected')

        url = f'{self._url}/v1/{path}'
        try:
            resp = self._session.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except requests.ConnectionError as e:
            raise HsmConnectionError(f'Connection failed: {e}')
        except requests.HTTPError as e:
            raise HsmOperationError(f'Sys API error: {e}')

    # ------------------------------------------------------------------
    # BaseHsmProvider implementation
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        self._session = requests.Session()
        self._session.headers.update({
            'X-Vault-Token': self._token,
        })
        if self._namespace:
            self._session.headers['X-Vault-Namespace'] = self._namespace
        self._session.verify = self._verify_tls

        # Verify connection with health check
        try:
            resp = self._session.get(f'{self._url}/v1/sys/health', verify=self._verify_tls)
            if resp.status_code not in (200, 429, 472, 473, 501, 503):
                raise HsmConnectionError(f'Unexpected health status: {resp.status_code}')
            self._connected = True
            return True
        except requests.ConnectionError as e:
            self._session = None
            raise HsmConnectionError(f'Cannot reach OpenBao at {self._url}: {e}')

    def disconnect(self) -> None:
        if self._session:
            self._session.close()
            self._session = None
        self._connected = False

    def test_connection(self) -> Dict[str, Any]:
        try:
            self.connect()

            # Check health
            resp = self._session.get(f'{self._url}/v1/sys/health', verify=self._verify_tls)
            health = resp.json() if resp.content else {}

            # Check transit engine is mounted
            try:
                mounts = self._sys_api('GET', 'sys/mounts')
                mount_key = f'{self._mount}/'
                transit_mounted = mount_key in mounts.get('data', mounts)
            except Exception:
                transit_mounted = False

            # Try listing keys to verify transit access
            key_count = 0
            if transit_mounted:
                try:
                    result = self._api('LIST', 'keys')
                    keys = result.get('data', {}).get('keys', [])
                    key_count = len(keys)
                except Exception:
                    pass

            server_info = {
                'server_type': 'OpenBao' if health.get('server_time_utc') else 'Vault/OpenBao',
                'version': health.get('version', 'unknown'),
                'sealed': health.get('sealed', False),
                'initialized': health.get('initialized', True),
                'transit_mounted': transit_mounted,
                'mount_path': self._mount,
                'key_count': key_count,
            }

            self.disconnect()

            if not transit_mounted:
                return {
                    'success': False,
                    'message': f'Transit engine not mounted at {self._mount}/',
                    'details': server_info,
                }

            return {
                'success': True,
                'message': f'Connected to OpenBao {server_info["version"]} — {key_count} key(s)',
                'details': server_info,
            }
        except HsmConnectionError as e:
            return {'success': False, 'message': str(e), 'details': {}}
        except Exception as e:
            return {'success': False, 'message': f'Unexpected error: {e}', 'details': {}}

    def list_keys(self) -> List[HsmKeyInfo]:
        result = self._api('LIST', 'keys')
        key_names = result.get('data', {}).get('keys', [])

        keys = []
        for name in key_names:
            try:
                detail = self._api('GET', f'keys/{name}')
                data = detail.get('data', {})
                transit_type = data.get('type', 'unknown')
                algorithm = TRANSIT_TO_ALGORITHM.get(transit_type, transit_type)
                is_symmetric = transit_type in ('aes128-gcm96', 'aes256-gcm96', 'chacha20-poly1305')

                # Get public key for asymmetric keys
                public_pem = None
                if not is_symmetric and data.get('keys'):
                    latest_ver = str(data.get('latest_version', 1))
                    ver_data = data['keys'].get(latest_ver, {})
                    public_pem = ver_data.get('public_key', None)

                keys.append(HsmKeyInfo(
                    key_identifier=name,
                    label=name,
                    algorithm=algorithm,
                    key_type='symmetric' if is_symmetric else 'asymmetric',
                    purpose='encryption' if is_symmetric else 'signing',
                    public_key_pem=public_pem,
                    is_extractable=data.get('exportable', False),
                    metadata={
                        'transit_type': transit_type,
                        'min_version': data.get('min_decryption_version', 1),
                        'latest_version': data.get('latest_version', 1),
                        'supports_signing': data.get('supports_signing', False),
                        'supports_derivation': data.get('supports_derivation', False),
                        'deletion_allowed': data.get('deletion_allowed', False),
                    }
                ))
            except Exception as e:
                logger.warning(f'Failed to read key {name}: {e}')

        return keys

    def generate_key(
        self,
        label: str,
        algorithm: str,
        purpose: str = 'signing',
        extractable: bool = False
    ) -> HsmKeyInfo:
        if algorithm not in ALGORITHM_TO_TRANSIT:
            raise HsmOperationError(
                f'Unsupported algorithm: {algorithm}. '
                f'Supported: {", ".join(ALGORITHM_TO_TRANSIT.keys())}'
            )

        transit_type, key_class = ALGORITHM_TO_TRANSIT[algorithm]

        payload = {
            'type': transit_type,
            'exportable': extractable,
            'allow_plaintext_backup': extractable,
        }

        self._api('POST', f'keys/{label}', json=payload)

        # Read back the created key
        detail = self._api('GET', f'keys/{label}')
        data = detail.get('data', {})

        public_pem = None
        if key_class == 'asymmetric' and data.get('keys'):
            latest_ver = str(data.get('latest_version', 1))
            ver_data = data['keys'].get(latest_ver, {})
            public_pem = ver_data.get('public_key', None)

        return HsmKeyInfo(
            key_identifier=label,
            label=label,
            algorithm=algorithm,
            key_type=key_class,
            purpose=purpose,
            public_key_pem=public_pem,
            is_extractable=extractable,
            metadata={'transit_type': transit_type}
        )

    def delete_key(self, key_identifier: str) -> bool:
        # Transit requires deletion_allowed=true before deleting
        try:
            self._api('POST', f'keys/{key_identifier}/config', json={
                'deletion_allowed': True
            })
        except HsmOperationError:
            pass

        try:
            self._api('DELETE', f'keys/{key_identifier}')
            return True
        except HsmOperationError as e:
            raise HsmOperationError(f'Failed to delete key {key_identifier}: {e}')

    def get_public_key(self, key_identifier: str) -> str:
        detail = self._api('GET', f'keys/{key_identifier}')
        data = detail.get('data', {})

        if not data:
            raise HsmKeyNotFoundError(f'Key {key_identifier} not found')

        transit_type = data.get('type', '')
        if transit_type in ('aes128-gcm96', 'aes256-gcm96', 'chacha20-poly1305'):
            raise HsmOperationError(f'Key {key_identifier} is symmetric — no public key')

        latest_ver = str(data.get('latest_version', 1))
        ver_data = data.get('keys', {}).get(latest_ver, {})
        pem = ver_data.get('public_key')

        if not pem:
            raise HsmOperationError(f'No public key available for {key_identifier}')

        return pem

    def sign(
        self,
        key_identifier: str,
        data: bytes,
        algorithm: Optional[str] = None
    ) -> bytes:
        # Determine hash algorithm from key type if not specified
        hash_alg = None
        sig_alg = None

        if algorithm and algorithm in SIGN_HASH_ALGORITHM:
            hash_alg = SIGN_HASH_ALGORITHM[algorithm]
            sig_alg = SIGN_ALGORITHM.get(algorithm)
        else:
            # Read key to determine type
            detail = self._api('GET', f'keys/{key_identifier}')
            key_data = detail.get('data', {})
            if not key_data:
                raise HsmKeyNotFoundError(f'Key {key_identifier} not found')

            transit_type = key_data.get('type', '')
            ucm_alg = TRANSIT_TO_ALGORITHM.get(transit_type)
            if ucm_alg:
                hash_alg = SIGN_HASH_ALGORITHM.get(ucm_alg, 'sha2-256')
                sig_alg = SIGN_ALGORITHM.get(ucm_alg)

        payload = {
            'input': base64.b64encode(data).decode('ascii'),
        }
        if hash_alg:
            payload['hash_algorithm'] = hash_alg
        if sig_alg:
            payload['signature_algorithm'] = sig_alg

        result = self._api('POST', f'sign/{key_identifier}', json=payload)
        signature_str = result.get('data', {}).get('signature', '')

        # Transit returns "vault:v1:<base64>" format
        if ':' in signature_str:
            sig_b64 = signature_str.rsplit(':', 1)[-1]
        else:
            sig_b64 = signature_str

        return base64.b64decode(sig_b64)
