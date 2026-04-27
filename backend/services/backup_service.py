"""
Backup Service for UCM
Handles creation of encrypted, portable backup archives
"""
import os
import json
import gzip
import struct
import uuid
import hashlib
import secrets
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

# Argon2id support (preferred KDF for v2 backups)
try:
    from argon2.low_level import hash_secret_raw, Type as Argon2Type
    _ARGON2_AVAILABLE = True
except ImportError:
    _ARGON2_AVAILABLE = False

from models import db, User, CA, Certificate, SystemConfig
from models.acme_models import AcmeAccount
from models.webauthn import WebAuthnCredential
from config.settings import Config
from utils.datetime_utils import utc_now, utc_isoformat

logger = logging.getLogger(__name__)


class BackupService:
    """Service for creating encrypted system backups
    
    Format v2 container layout:
        [0:4]      magic = b'UCMB'
        [4]        format_version = 0x02
        [5]        flags (bit 0 = gzip-compressed plaintext)
        [6]        kdf_id (1=PBKDF2-SHA256, 2=Argon2id)
        [7]        reserved = 0x00
        [8:10]     metadata_len (big-endian uint16)
        [10:10+N]  metadata JSON (unencrypted header: ucm_version, created_at,
                   kdf params, salt_b64, nonce_b64)
        [10+N:]    AES-256-GCM ciphertext (plaintext = gzipped JSON if flag set)
    
    Format v1 (legacy): raw 32-byte salt + 12-byte nonce + GCM ciphertext.
    restore_backup() auto-detects format from magic bytes.
    """
    
    # v1/legacy constants (PBKDF2)
    PBKDF2_ITERATIONS = 100000
    KEY_SIZE = 32  # 256 bits for AES-256
    NONCE_SIZE = 12  # 96 bits for GCM
    SALT_SIZE = 32
    
    # v2 constants
    MAGIC = b'UCMB'
    FORMAT_VERSION_V2 = 2
    FLAG_GZIP = 0x01
    KDF_PBKDF2 = 1
    KDF_ARGON2ID = 2
    
    # Argon2id params (OWASP 2024 recommendation for sensitive data)
    ARGON2_TIME_COST = 3
    ARGON2_MEMORY_COST = 65536  # 64 MiB
    ARGON2_PARALLELISM = 4
    ARGON2_SALT_SIZE = 16
    
    # Stronger PBKDF2 when Argon2 unavailable
    PBKDF2_ITERATIONS_V2 = 600000
    
    def __init__(self):
        self.app_version = Config.APP_VERSION
    
    def create_backup(
        self, 
        password: str,
        backup_type: str = "full",
        include: Optional[Dict[str, bool]] = None
    ) -> bytes:
        """
        Create encrypted backup archive
        
        Args:
            password: Encryption password (min 12 chars)
            backup_type: "full", "database", or "certificates"
            include: Dict of what to include (cas, certificates, users, etc.)
            
        Returns:
            Encrypted backup as bytes
        """
        # Validate password
        self._validate_password(password)
        
        # Default includes
        if include is None:
            include = {
                'cas': True,
                'certificates': True,
                'users': True,
                'configuration': True,
                'acme_accounts': True,
                'acme_eab_credentials': True,
                'email_password': False,
                'groups': True,
                'custom_roles': True,
                'certificate_templates': True,
                'trusted_certificates': True,
                'sso_providers': True,
                'hsm_providers': True,
                'api_keys': True,
                'smtp_config': True,
                'notification_config': True,
                'certificate_policies': True,
                'auth_certificates': True,
                'dns_providers': True,
                'acme_domains': True,
                'acme_local_domains': True,
                'ssh_cas': True,
                'ssh_certificates': True,
                'microsoft_cas': True,
                'msca_requests': True,
                'scan_profiles': True,
                'scan_runs': False,  # historical, can be large
                'discovered_certificates': False,  # historical, can be large
                'approval_requests': True,  # pending approvals matter
                'scep_requests': False,  # historical
                'acme_client_orders': False,  # historical
                'hsm_keys': True,
                'audit_logs': False,  # opt-in, tamper-evident chain, can be huge
            }
        
        # Build backup data structure
        def _safe(fn, *args, **kwargs):
            """Call an export method; return [] on failure (missing table, model import error, etc.)"""
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Backup export {fn.__name__} failed: {e}")
                return [] if 'export' in fn.__name__ else {}
        
        backup_data = {
            'metadata': self._get_metadata(backup_type),
            'configuration': _safe(self._export_configuration, include.get('configuration', True)),
            'users': _safe(self._export_users, include.get('users', True)),
            'certificate_authorities': _safe(self._export_cas, include.get('cas', True)),
            'certificates': _safe(self._export_certificates, include.get('certificates', True)),
            'acme_accounts': _safe(self._export_acme_accounts, include.get('acme_accounts', True)),
            'acme_eab_credentials': _safe(self._export_acme_eab_credentials, include.get('acme_eab_credentials', True)),
            'groups': _safe(self._export_groups, include.get('groups', True)),
            'custom_roles': _safe(self._export_custom_roles, include.get('custom_roles', True)),
            'certificate_templates': _safe(self._export_templates, include.get('certificate_templates', True)),
            'trusted_certificates': _safe(self._export_truststore, include.get('trusted_certificates', True)),
            'sso_providers': _safe(self._export_sso_providers, include.get('sso_providers', True)),
            'hsm_providers': _safe(self._export_hsm_providers, include.get('hsm_providers', True)),
            'api_keys': _safe(self._export_api_keys, include.get('api_keys', True)),
            'smtp_config': _safe(self._export_smtp_config, include.get('smtp_config', True)),
            'notification_config': _safe(self._export_notification_config, include.get('notification_config', True)),
            'certificate_policies': _safe(self._export_policies, include.get('certificate_policies', True)),
            'auth_certificates': _safe(self._export_auth_certificates, include.get('auth_certificates', True)),
            'dns_providers': _safe(self._export_dns_providers, include.get('dns_providers', True)),
            'acme_domains': _safe(self._export_acme_domains, include.get('acme_domains', True)),
            'acme_local_domains': _safe(self._export_acme_local_domains, include.get('acme_local_domains', True)),
            'ssh_cas': _safe(self._export_ssh_cas, include.get('ssh_cas', True)),
            'ssh_certificates': _safe(self._export_ssh_certificates, include.get('ssh_certificates', True)),
            'microsoft_cas': _safe(self._export_microsoft_cas, include.get('microsoft_cas', True)),
            'msca_requests': _safe(self._export_msca_requests, include.get('msca_requests', True)),
            'scan_profiles': _safe(self._export_scan_profiles, include.get('scan_profiles', True)),
            'scan_runs': _safe(self._export_scan_runs, include.get('scan_runs', False)),
            'discovered_certificates': _safe(self._export_discovered_certificates, include.get('discovered_certificates', False)),
            'approval_requests': _safe(self._export_approval_requests, include.get('approval_requests', True)),
            'scep_requests': _safe(self._export_scep_requests, include.get('scep_requests', False)),
            'acme_client_orders': _safe(self._export_acme_client_orders, include.get('acme_client_orders', False)),
            'hsm_keys': _safe(self._export_hsm_keys, include.get('hsm_keys', True)),
            'audit_logs': _safe(self._export_audit_logs, include.get('audit_logs', False)),
            'https_server': _safe(self._export_https_files),
        }
        
        # Choose KDF: Argon2id if available, else strong PBKDF2
        if _ARGON2_AVAILABLE:
            kdf_id = self.KDF_ARGON2ID
            salt = secrets.token_bytes(self.ARGON2_SALT_SIZE)
            master_key = self._derive_argon2id(password, salt)
            kdf_params = {
                'type': 'argon2id',
                'time_cost': self.ARGON2_TIME_COST,
                'memory_cost': self.ARGON2_MEMORY_COST,
                'parallelism': self.ARGON2_PARALLELISM,
                'hash_len': self.KEY_SIZE,
            }
        else:
            kdf_id = self.KDF_PBKDF2
            salt = secrets.token_bytes(self.SALT_SIZE)
            master_key = self._derive_pbkdf2(password, salt, self.PBKDF2_ITERATIONS_V2)
            kdf_params = {
                'type': 'pbkdf2-sha256',
                'iterations': self.PBKDF2_ITERATIONS_V2,
                'hash_len': self.KEY_SIZE,
            }
        
        # Encrypt private keys individually (uses same master_key + PBKDF2 per-key salt for legacy compat)
        backup_data = self._encrypt_private_keys(backup_data, master_key)
        
        # Calculate checksum of plaintext
        json_str = json.dumps(backup_data, indent=2, sort_keys=True)
        checksum = hashlib.sha256(json_str.encode()).hexdigest()
        backup_data['checksum'] = {
            'algorithm': 'SHA256',
            'value': checksum
        }
        
        # Serialize final payload
        final_json = json.dumps(backup_data, indent=2, sort_keys=True).encode()
        
        # Compress (gzip level 6 — good ratio, fast)
        flags = self.FLAG_GZIP
        plaintext = gzip.compress(final_json, compresslevel=6)
        
        # Encrypt with AES-256-GCM
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        ciphertext = AESGCM(master_key).encrypt(nonce, plaintext, self.MAGIC)
        
        # Build v2 container
        metadata = {
            'format_version': self.FORMAT_VERSION_V2,
            'ucm_version': self.app_version,
            'created_at': utc_now().isoformat() + 'Z',
            'backup_type': backup_type,
            'kdf': kdf_params,
            'salt_b64': base64.b64encode(salt).decode(),
            'nonce_b64': base64.b64encode(nonce).decode(),
        }
        metadata_bytes = json.dumps(metadata, separators=(',', ':')).encode()
        if len(metadata_bytes) > 65535:
            raise ValueError("Backup metadata too large")
        
        header = (
            self.MAGIC
            + bytes([self.FORMAT_VERSION_V2, flags, kdf_id, 0])
            + struct.pack('>H', len(metadata_bytes))
            + metadata_bytes
        )
        return header + ciphertext
    
    def _derive_argon2id(self, password: str, salt: bytes,
                          time_cost: int = None, memory_cost: int = None,
                          parallelism: int = None, hash_len: int = None) -> bytes:
        """Derive key using Argon2id (memory-hard, side-channel resistant)"""
        if not _ARGON2_AVAILABLE:
            raise RuntimeError("argon2-cffi not installed")
        return hash_secret_raw(
            secret=password.encode(),
            salt=salt,
            time_cost=time_cost or self.ARGON2_TIME_COST,
            memory_cost=memory_cost or self.ARGON2_MEMORY_COST,
            parallelism=parallelism or self.ARGON2_PARALLELISM,
            hash_len=hash_len or self.KEY_SIZE,
            type=Argon2Type.ID,
        )
    
    def _derive_pbkdf2(self, password: str, salt: bytes, iterations: int) -> bytes:
        """Derive key using PBKDF2-SHA256"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=iterations,
            backend=default_backend()
        )
        return kdf.derive(password.encode())
    
    def _validate_password(self, password: str):
        """Validate backup password strength"""
        if len(password) < 12:
            raise ValueError("Backup password must be at least 12 characters")
        
        # Check entropy (basic)
        unique_chars = len(set(password))
        if unique_chars < 8:
            raise ValueError("Backup password is too simple")
    
    def _derive_master_key(self, password: str) -> tuple:
        """Legacy v1 PBKDF2 derivation (kept for backward-compat restore)"""
        salt = secrets.token_bytes(self.SALT_SIZE)
        key = self._derive_pbkdf2(password, salt, self.PBKDF2_ITERATIONS)
        return key, salt
    
    def _encrypt_backup(self, data: bytes, key: bytes) -> bytes:
        """Legacy v1 AES-256-GCM encrypt (kept for tests / fallback)"""
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext
    
    def _encrypt_private_key(self, key_pem: str, master_key: bytes) -> Dict[str, str]:
        """Encrypt individual private key with unique salt"""
        # Derive unique key for this specific private key
        salt = secrets.token_bytes(self.SALT_SIZE)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=10000,  # Fewer iterations for per-key encryption
            backend=default_backend()
        )
        key = kdf.derive(master_key)
        
        # Encrypt
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, key_pem.encode(), None)
        
        return {
            'algorithm': 'AES-256-GCM',
            'salt': salt.hex(),
            'nonce': nonce.hex(),
            'ciphertext': ciphertext.hex()
        }
    
    def _get_metadata(self, backup_type: str) -> Dict[str, Any]:
        """Generate backup metadata"""
        return {
            'version': '1.0',
            'ucm_version': self.app_version,
            'database_type': 'sqlite',  # TODO: detect from config
            'created_at': utc_now().isoformat() + 'Z',
            'hostname': os.environ.get('FQDN', 'unknown'),
            'backup_type': backup_type,
            'format_version': '2.0'
        }
    
    def _export_configuration(self, include: bool) -> Dict[str, Any]:
        """Export system configuration"""
        if not include:
            return {}
        
        config = {}
        
        # Get all system config entries
        system_configs = SystemConfig.query.all()
        for sc in system_configs:
            # Skip sensitive data unless explicitly included
            if sc.encrypted:
                continue
            
            val = sc.value
            if isinstance(val, bytes):
                try:
                    val = val.decode('utf-8')
                except Exception:
                    import base64
                    val = base64.b64encode(val).decode('utf-8')
            
            config[sc.key] = val
        
        return {
            'system': {
                'fqdn': os.environ.get('FQDN', ''),
                'https_port': int(os.environ.get('HTTPS_PORT', 8443)),
                'session_timeout': int(os.environ.get('SESSION_TIMEOUT', 3600)),
                'jwt_expiration': int(os.environ.get('JWT_EXPIRATION', 86400))
            },
            'settings': config
        }
    
    def _export_users(self, include: bool) -> List[Dict[str, Any]]:
        """Export users with password hashes and WebAuthn credentials"""
        if not include:
            return []
        
        users = []
        for user in User.query.all():
            user_data = {
                'username': user.username,
                'email': user.email,
                'full_name': user.full_name,
                'role': user.role,
                'active': user.active,
                'mfa_enabled': user.mfa_enabled,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'password_hash': user.password_hash
            }
            
            # Export WebAuthn credentials
            webauthn_creds = WebAuthnCredential.query.filter_by(
                user_id=user.id, 
                enabled=True
            ).all()
            
            import base64
            user_data['webauthn_credentials'] = [
                {
                    'credential_id': base64.b64encode(cred.credential_id).decode('utf-8') if cred.credential_id else None,
                    'public_key': base64.b64encode(cred.public_key).decode('utf-8') if cred.public_key else None,
                    'sign_count': cred.sign_count,
                    'name': cred.name,
                    'aaguid': cred.aaguid
                }
                for cred in webauthn_creds
            ]
            
            users.append(user_data)
        
        return users
    
    def _export_cas(self, include: bool) -> List[Dict[str, Any]]:
        """Export Certificate Authorities with encrypted private keys"""
        if not include:
            return []
        
        import base64
        cas = []
        for ca in CA.query.all():
            ca_data = {
                'refid': ca.refid,
                'descr': ca.descr,
                'subject': ca.subject,
                'issuer': ca.issuer,
                'valid_from': ca.valid_from.isoformat() if ca.valid_from else None,
                'valid_to': ca.valid_to.isoformat() if ca.valid_to else None,
                'serial': ca.serial,
                'caref': ca.caref,  # Parent CA for intermediates
                'cdp_enabled': ca.cdp_enabled,
                'cdp_url': ca.cdp_url,
                'cdp_urls': ca.get_cdp_urls(),
                'ocsp_enabled': ca.ocsp_enabled,
                'ocsp_url': ca.ocsp_url,
                'ocsp_urls': ca.get_ocsp_urls(),
                'aia_ca_issuers_enabled': getattr(ca, 'aia_ca_issuers_enabled', False),
                'aia_ca_issuers_url': getattr(ca, 'aia_ca_issuers_url', None),
                'aia_ca_issuers_urls': ca.get_aia_urls(),
                'cps_enabled': ca.cps_enabled,
                'cps_uri': ca.cps_uri,
                'cps_oid': ca.cps_oid,
                'imported_from': ca.imported_from,
                'certificate_pem': base64.b64decode(ca.crt).decode() if ca.crt else None,
                'private_key_pem_encrypted': None  # Will be set in _encrypt_private_keys
            }
            
            # Decrypt at-rest encryption before export (backup uses its own encryption)
            if ca.prv:
                try:
                    from security.encryption import decrypt_private_key
                    prv_decrypted = decrypt_private_key(ca.prv)
                    ca_data['_private_key_plaintext'] = base64.b64decode(prv_decrypted).decode()
                except Exception:
                    ca_data['_private_key_plaintext'] = ca.prv
            
            cas.append(ca_data)
        
        return cas
    
    def _export_certificates(self, include: bool) -> List[Dict[str, Any]]:
        """Export certificates with encrypted private keys"""
        if not include:
            return []
        
        import base64
        certs = []
        for cert in Certificate.query.all():
            cert_data = {
                'refid': cert.refid,
                'descr': cert.descr,
                'caref': cert.caref,
                'cert_type': cert.cert_type,
                'subject': cert.subject,
                'issuer': cert.issuer,
                'serial_number': cert.serial_number,
                'valid_from': cert.valid_from.isoformat() if cert.valid_from else None,
                'valid_to': cert.valid_to.isoformat() if cert.valid_to else None,
                'key_algo': cert.key_algo,
                'san_dns': cert.san_dns,
                'san_ip': cert.san_ip,
                'san_email': cert.san_email,
                'san_uri': cert.san_uri,
                'ocsp_uri': cert.ocsp_uri,
                'ocsp_must_staple': getattr(cert, 'ocsp_must_staple', False),
                'private_key_location': cert.private_key_location,
                'revoked': bool(cert.revoked),
                'revoked_at': cert.revoked_at.isoformat() if cert.revoked_at else None,
                'revoke_reason': cert.revoke_reason,
                'archived': bool(cert.archived),
                'imported_from': cert.imported_from,
                'created_at': cert.created_at.isoformat() if cert.created_at else None,
                'created_by': cert.created_by,
                'source': cert.source,
                'template_id': cert.template_id,
                'owner_group_id': cert.owner_group_id,
                'certificate_pem': base64.b64decode(cert.crt).decode() if cert.crt else None,
                'csr_pem': base64.b64decode(cert.csr).decode() if cert.csr else None,
                'private_key_pem_encrypted': None  # Will be set in _encrypt_private_keys
            }
            
            # Decrypt at-rest encryption before export
            if cert.prv:
                try:
                    from security.encryption import decrypt_private_key
                    prv_decrypted = decrypt_private_key(cert.prv)
                    cert_data['_private_key_plaintext'] = base64.b64decode(prv_decrypted).decode()
                except Exception:
                    cert_data['_private_key_plaintext'] = cert.prv
            
            certs.append(cert_data)
        
        return certs
    
    def _export_acme_accounts(self, include: bool) -> List[Dict[str, Any]]:
        """Export ACME server accounts (RFC 8555 §7.1.2)."""
        if not include:
            return []

        accounts = []
        for account in AcmeAccount.query.all():
            accounts.append({
                'account_id': account.account_id,
                'jwk': account.jwk,
                'jwk_thumbprint': account.jwk_thumbprint,
                'contact': account.contact,
                'status': account.status,
                'terms_of_service_agreed': account.terms_of_service_agreed,
                'external_account_binding': account.external_account_binding,
                'created_at': utc_isoformat(account.created_at) if account.created_at else None,
                'updated_at': utc_isoformat(account.updated_at) if account.updated_at else None,
            })

        return accounts

    def _export_acme_eab_credentials(self, include: bool) -> List[Dict[str, Any]]:
        """Export ACME EAB credentials (RFC 8555 §7.3.4).

        Includes the HMAC key — required so restored ACME clients can keep
        registering. Key is already protected by the backup's master key
        (AES-256-GCM); no extra wrapping needed.
        """
        if not include:
            return []
        try:
            from models.acme_models import AcmeEabCredential
        except Exception:
            return []
        creds = []
        for c in AcmeEabCredential.query.all():
            creds.append({
                'kid': c.kid,
                'hmac_key_b64': c.hmac_key_b64,
                'label': c.label,
                'created_by_user_id': c.created_by_user_id,
                'created_at': utc_isoformat(c.created_at) if c.created_at else None,
                'expires_at': utc_isoformat(c.expires_at) if c.expires_at else None,
                'used_at': utc_isoformat(c.used_at) if c.used_at else None,
                'used_by_account_id': c.used_by_account_id,
                'revoked_at': utc_isoformat(c.revoked_at) if c.revoked_at else None,
                'revoked_by_user_id': c.revoked_by_user_id,
                'status': c.status,
            })
        return creds
    
    def _export_groups(self, include: bool) -> List[Dict[str, Any]]:
        """Export groups with members"""
        if not include:
            return []
        from models.group import Group, GroupMember
        groups = []
        for group in Group.query.all():
            members = []
            for m in group.members:
                members.append({
                    'user_id': m.user_id,
                    'role': m.role,
                })
            groups.append({
                'name': group.name,
                'description': group.description,
                'permissions': group.permissions,
                'members': members,
                'created_at': group.created_at.isoformat() if group.created_at else None,
            })
        return groups

    def _export_custom_roles(self, include: bool) -> List[Dict[str, Any]]:
        """Export custom roles"""
        if not include:
            return []
        from models.rbac import CustomRole
        roles = []
        for role in CustomRole.query.all():
            roles.append({
                'name': role.name,
                'description': role.description,
                'permissions': role.permissions,
                'inherits_from': role.parent.name if role.parent else None,
                'is_system': role.is_system,
                'created_at': role.created_at.isoformat() if role.created_at else None,
            })
        return roles

    def _export_templates(self, include: bool) -> List[Dict[str, Any]]:
        """Export certificate templates"""
        if not include:
            return []
        from models.certificate_template import CertificateTemplate
        templates = []
        for t in CertificateTemplate.query.all():
            templates.append({
                'name': t.name,
                'description': t.description,
                'template_type': t.template_type,
                'key_type': t.key_type,
                'validity_days': t.validity_days,
                'digest': t.digest,
                'dn_template': t.dn_template,
                'extensions_template': t.extensions_template,
                'is_system': t.is_system,
                'is_active': t.is_active,
                'created_by': t.created_by,
            })
        return templates

    def _export_truststore(self, include: bool) -> List[Dict[str, Any]]:
        """Export trusted certificates"""
        if not include:
            return []
        from models.truststore import TrustedCertificate
        certs = []
        for tc in TrustedCertificate.query.all():
            certs.append({
                'name': tc.name,
                'description': tc.description,
                'certificate_pem': tc.certificate_pem,
                'fingerprint_sha256': tc.fingerprint_sha256,
                'fingerprint_sha1': tc.fingerprint_sha1,
                'subject': tc.subject,
                'issuer': tc.issuer,
                'serial_number': tc.serial_number,
                'not_before': tc.not_before.isoformat() if tc.not_before else None,
                'not_after': tc.not_after.isoformat() if tc.not_after else None,
                'purpose': tc.purpose,
                'added_by': tc.added_by,
                'notes': tc.notes,
            })
        return certs

    def _export_sso_providers(self, include: bool) -> List[Dict[str, Any]]:
        """Export SSO providers with encrypted secrets"""
        if not include:
            return []
        from models.sso import SSOProvider
        providers = []
        for p in SSOProvider.query.all():
            data = {
                'name': p.name,
                'provider_type': p.provider_type,
                'enabled': p.enabled,
                'is_default': p.is_default,
                'display_name': p.display_name,
                'icon': p.icon,
                'default_role': p.default_role,
                'auto_create_users': p.auto_create_users,
                'auto_update_users': p.auto_update_users,
                'attribute_mapping': p.attribute_mapping,
                'role_mapping': p.role_mapping,
                # SAML
                'saml_entity_id': p.saml_entity_id,
                'saml_sso_url': p.saml_sso_url,
                'saml_slo_url': p.saml_slo_url,
                'saml_certificate': p.saml_certificate,
                'saml_sign_requests': p.saml_sign_requests,
                # OAuth2
                'oauth2_client_id': p.oauth2_client_id,
                'oauth2_client_secret': p._oauth2_client_secret,
                'oauth2_auth_url': p.oauth2_auth_url,
                'oauth2_token_url': p.oauth2_token_url,
                'oauth2_userinfo_url': p.oauth2_userinfo_url,
                'oauth2_scopes': p.oauth2_scopes,
                # LDAP
                'ldap_server': p.ldap_server,
                'ldap_port': p.ldap_port,
                'ldap_use_ssl': p.ldap_use_ssl,
                'ldap_bind_dn': p.ldap_bind_dn,
                'ldap_bind_password': p._ldap_bind_password,
                'ldap_base_dn': p.ldap_base_dn,
                'ldap_user_filter': p.ldap_user_filter,
                'ldap_group_filter': p.ldap_group_filter,
                'ldap_username_attr': p.ldap_username_attr,
                'ldap_email_attr': p.ldap_email_attr,
                'ldap_fullname_attr': p.ldap_fullname_attr,
            }
            providers.append(data)
        return providers

    def _export_hsm_providers(self, include: bool) -> List[Dict[str, Any]]:
        """Export HSM providers with config"""
        if not include:
            return []
        from models.hsm import HsmProvider
        providers = []
        for h in HsmProvider.query.all():
            providers.append({
                'name': h.name,
                'type': h.type,
                'config': h.config,
                'status': h.status,
            })
        return providers

    def _export_api_keys(self, include: bool) -> List[Dict[str, Any]]:
        """Export API keys (hashed, not plaintext)"""
        if not include:
            return []
        from models.api_key import APIKey
        keys = []
        for k in APIKey.query.all():
            keys.append({
                'user_id': k.user_id,
                'key_hash': k.key_hash,
                'name': k.name,
                'permissions': k.permissions,
                'is_active': k.is_active,
                'expires_at': k.expires_at.isoformat() if k.expires_at else None,
                'created_at': k.created_at.isoformat() if k.created_at else None,
            })
        return keys

    def _export_smtp_config(self, include: bool) -> List[Dict[str, Any]]:
        """Export SMTP configuration with encrypted password"""
        if not include:
            return []
        from models.email_notification import SMTPConfig
        configs = []
        for sc in SMTPConfig.query.all():
            configs.append({
                'smtp_host': sc.smtp_host,
                'smtp_port': sc.smtp_port,
                'smtp_user': sc.smtp_user,
                'smtp_password': sc._smtp_password,
                'smtp_from': sc.smtp_from,
                'smtp_from_name': sc.smtp_from_name,
                'smtp_use_tls': sc.smtp_use_tls,
                'smtp_use_ssl': sc.smtp_use_ssl,
                'enabled': sc.enabled,
            })
        return configs

    def _export_notification_config(self, include: bool) -> List[Dict[str, Any]]:
        """Export notification configurations"""
        if not include:
            return []
        from models.email_notification import NotificationConfig
        configs = []
        for nc in NotificationConfig.query.all():
            configs.append({
                'type': nc.type,
                'enabled': nc.enabled,
                'days_before': nc.days_before,
                'recipients': nc.recipients,
                'subject_template': nc.subject_template,
                'description': nc.description,
                'cooldown_hours': nc.cooldown_hours,
            })
        return configs

    def _export_policies(self, include: bool) -> List[Dict[str, Any]]:
        """Export certificate policies"""
        if not include:
            return []
        from models.policy import CertificatePolicy
        policies = []
        for p in CertificatePolicy.query.all():
            policies.append({
                'name': p.name,
                'description': p.description,
                'policy_type': p.policy_type,
                'ca_id': p.ca_id,
                'template_id': p.template_id,
                'rules': p.rules,
                'requires_approval': p.requires_approval,
                'approval_group_id': p.approval_group_id,
                'min_approvers': p.min_approvers,
                'notify_on_violation': p.notify_on_violation,
                'notification_emails': p.notification_emails,
                'is_active': p.is_active,
                'priority': p.priority,
                'created_by': p.created_by,
            })
        return policies

    def _export_auth_certificates(self, include: bool) -> List[Dict[str, Any]]:
        """Export authentication certificates"""
        if not include:
            return []
        from models.auth_certificate import AuthCertificate
        import base64
        certs = []
        for ac in AuthCertificate.query.all():
            cert_pem = ac.cert_pem
            if isinstance(cert_pem, bytes):
                cert_pem = base64.b64encode(cert_pem).decode('utf-8')
            certs.append({
                'user_id': ac.user_id,
                'cert_pem': cert_pem,
                'cert_serial': ac.cert_serial,
                'cert_subject': ac.cert_subject,
                'cert_issuer': ac.cert_issuer,
                'cert_fingerprint': ac.cert_fingerprint,
                'name': ac.name,
                'enabled': ac.enabled,
                'valid_from': ac.valid_from.isoformat() if ac.valid_from else None,
                'valid_until': ac.valid_until.isoformat() if ac.valid_until else None,
            })
        return certs

    def _export_dns_providers(self, include: bool) -> List[Dict[str, Any]]:
        """Export DNS providers with credentials"""
        if not include:
            return []
        from models.acme_models import DnsProvider
        providers = []
        for dp in DnsProvider.query.all():
            providers.append({
                'name': dp.name,
                'provider_type': dp.provider_type,
                'credentials': dp.credentials,
                'zones': dp.zones,
                'is_default': dp.is_default,
                'enabled': dp.enabled,
            })
        return providers

    def _export_acme_domains(self, include: bool) -> List[Dict[str, Any]]:
        """Export ACME domains"""
        if not include:
            return []
        from models.acme_models import AcmeDomain
        domains = []
        for ad in AcmeDomain.query.all():
            domains.append({
                'domain': ad.domain,
                'dns_provider_id': ad.dns_provider_id,
                'issuing_ca_id': ad.issuing_ca_id,
                'is_wildcard_allowed': ad.is_wildcard_allowed,
                'auto_approve': ad.auto_approve,
                'created_by': ad.created_by,
            })
        return domains

    def _export_acme_local_domains(self, include: bool) -> List[Dict[str, Any]]:
        """Export local ACME domain-to-CA mappings"""
        if not include:
            return []
        from models.acme_models import AcmeLocalDomain
        domains = []
        for ld in AcmeLocalDomain.query.all():
            domains.append({
                'domain': ld.domain,
                'issuing_ca_id': ld.issuing_ca_id,
                'auto_approve': ld.auto_approve,
                'created_by': ld.created_by,
            })
        return domains

    def _export_ssh_cas(self, include: bool, master_key: bytes = None) -> List[Dict[str, Any]]:
        """Export SSH Certificate Authorities (with private keys handled separately)"""
        if not include:
            return []
        try:
            from models.ssh import SSHCertificateAuthority
        except Exception:
            return []
        cas = []
        for ca in SSHCertificateAuthority.query.all():
            ca_data = {
                'refid': getattr(ca, 'refid', None),
                'descr': getattr(ca, 'descr', None),
                'ca_type': getattr(ca, 'ca_type', None),
                'key_type': getattr(ca, 'key_type', None),
                'public_key': getattr(ca, 'public_key', None),
                'fingerprint': getattr(ca, 'fingerprint', None),
                'serial_counter': getattr(ca, 'serial_counter', 0),
                'default_ttl': getattr(ca, 'default_ttl', 86400),
                'max_ttl': getattr(ca, 'max_ttl', 0),
                'default_extensions': getattr(ca, 'default_extensions', None),
                'allowed_principals': getattr(ca, 'allowed_principals', None),
                'comment': getattr(ca, 'comment', None),
                'created_at': ca.created_at.isoformat() if getattr(ca, 'created_at', None) else None,
                'created_by': getattr(ca, 'created_by', None),
                'owner_group_id': getattr(ca, 'owner_group_id', None),
            }
            # Private key: re-encrypt with master key in _encrypt_private_keys pass
            prv = getattr(ca, 'private_key', None)
            if prv:
                try:
                    from security.encryption import decrypt_private_key
                    ca_data['_private_key_plaintext'] = decrypt_private_key(prv) if isinstance(prv, str) else prv.decode() if isinstance(prv, bytes) else str(prv)
                except Exception:
                    ca_data['_private_key_plaintext'] = str(prv)
            cas.append(ca_data)
        return cas
    
    def _export_ssh_certificates(self, include: bool) -> List[Dict[str, Any]]:
        """Export SSH certificates"""
        if not include:
            return []
        try:
            from models.ssh import SSHCertificate
        except Exception:
            return []
        certs = []
        for c in SSHCertificate.query.all():
            certs.append({
                'refid': getattr(c, 'refid', None),
                'descr': getattr(c, 'descr', None),
                'ssh_ca_id': c.ssh_ca_id,
                'cert_type': getattr(c, 'cert_type', None),
                'key_id': getattr(c, 'key_id', None),
                'public_key': getattr(c, 'public_key', None),
                'certificate': getattr(c, 'certificate', None),
                'principals': getattr(c, 'principals', None),
                'serial': getattr(c, 'serial', None),
                'valid_from': c.valid_from.isoformat() if getattr(c, 'valid_from', None) else None,
                'valid_to': c.valid_to.isoformat() if getattr(c, 'valid_to', None) else None,
                'key_type': getattr(c, 'key_type', None),
                'fingerprint': getattr(c, 'fingerprint', None),
                'extensions': getattr(c, 'extensions', None),
                'critical_options': getattr(c, 'critical_options', None),
                'revoked': bool(getattr(c, 'revoked', False)),
                'revoked_at': c.revoked_at.isoformat() if getattr(c, 'revoked_at', None) else None,
                'revoke_reason': getattr(c, 'revoke_reason', None),
                'source': getattr(c, 'source', 'web'),
                'created_at': c.created_at.isoformat() if getattr(c, 'created_at', None) else None,
                'created_by': getattr(c, 'created_by', None),
                'owner_group_id': getattr(c, 'owner_group_id', None),
            })
        return certs
    
    def _export_microsoft_cas(self, include: bool) -> List[Dict[str, Any]]:
        """Export Microsoft CA (ADCS) connection configurations"""
        if not include:
            return []
        try:
            from models.msca import MicrosoftCA
        except Exception:
            return []
        items = []
        for ca in MicrosoftCA.query.all():
            items.append({
                'name': ca.name,
                'server': getattr(ca, 'server', None),
                'ca_name': getattr(ca, 'ca_name', None),
                'auth_method': getattr(ca, 'auth_method', None),
                'username': getattr(ca, 'username', None),
                'password': getattr(ca, 'password', None),  # already encrypted at rest
                'client_cert_pem': getattr(ca, 'client_cert_pem', None),
                'client_key_pem': getattr(ca, 'client_key_pem', None),
                'kerberos_principal': getattr(ca, 'kerberos_principal', None),
                'kerberos_keytab_path': getattr(ca, 'kerberos_keytab_path', None),
                'use_ssl': getattr(ca, 'use_ssl', True),
                'verify_ssl': getattr(ca, 'verify_ssl', True),
                'ca_bundle': getattr(ca, 'ca_bundle', None),
                'default_template': getattr(ca, 'default_template', None),
                'enabled': getattr(ca, 'enabled', True),
                'created_at': ca.created_at.isoformat() if getattr(ca, 'created_at', None) else None,
                'created_by': getattr(ca, 'created_by', None),
            })
        return items
    
    def _export_msca_requests(self, include: bool) -> List[Dict[str, Any]]:
        """Export MSCA sign request history"""
        if not include:
            return []
        try:
            from models.msca import MSCARequest
        except Exception:
            return []
        items = []
        for r in MSCARequest.query.all():
            items.append({
                'msca_id': r.msca_id,
                'csr_id': getattr(r, 'csr_id', None),
                'cert_id': getattr(r, 'cert_id', None),
                'request_id': getattr(r, 'request_id', None),
                'disposition_message': getattr(r, 'disposition_message', None),
                'template': getattr(r, 'template', None),
                'status': getattr(r, 'status', None),
                'submitted_at': r.submitted_at.isoformat() if getattr(r, 'submitted_at', None) else None,
                'issued_at': r.issued_at.isoformat() if getattr(r, 'issued_at', None) else None,
                'error_message': getattr(r, 'error_message', None),
                'cert_pem': getattr(r, 'cert_pem', None),
                'submitted_by': getattr(r, 'submitted_by', None),
                'enrollee_name': getattr(r, 'enrollee_name', None),
                'enrollee_upn': getattr(r, 'enrollee_upn', None),
            })
        return items
    
    def _export_scan_profiles(self, include: bool) -> List[Dict[str, Any]]:
        """Export discovery scan profiles"""
        if not include:
            return []
        try:
            from models.discovered_certificate import ScanProfile
        except Exception:
            return []
        profiles = []
        for p in ScanProfile.query.all():
            profiles.append({
                'name': p.name,
                'description': getattr(p, 'description', None),
                'targets': getattr(p, 'targets', None),
                'ports': getattr(p, 'ports', None),
                'schedule_enabled': getattr(p, 'schedule_enabled', False),
                'schedule_interval_minutes': getattr(p, 'schedule_interval_minutes', None),
                'notify_on_new': getattr(p, 'notify_on_new', True),
                'notify_on_change': getattr(p, 'notify_on_change', True),
                'notify_on_expiry': getattr(p, 'notify_on_expiry', True),
                'timeout': getattr(p, 'timeout', None),
                'max_workers': getattr(p, 'max_workers', None),
                'resolve_dns': getattr(p, 'resolve_dns', True),
                'last_scan_at': p.last_scan_at.isoformat() if getattr(p, 'last_scan_at', None) else None,
                'next_scan_at': p.next_scan_at.isoformat() if getattr(p, 'next_scan_at', None) else None,
                'created_at': p.created_at.isoformat() if getattr(p, 'created_at', None) else None,
            })
        return profiles
    
    def _export_scan_runs(self, include: bool) -> List[Dict[str, Any]]:
        """Export discovery scan run history"""
        if not include:
            return []
        try:
            from models.discovered_certificate import ScanRun
        except Exception:
            return []
        runs = []
        for r in ScanRun.query.all():
            runs.append({
                'scan_profile_id': r.scan_profile_id,
                'started_at': r.started_at.isoformat() if getattr(r, 'started_at', None) else None,
                'completed_at': r.completed_at.isoformat() if getattr(r, 'completed_at', None) else None,
                'status': getattr(r, 'status', None),
                'total_targets': getattr(r, 'total_targets', None),
                'targets_scanned': getattr(r, 'targets_scanned', None),
                'certs_found': getattr(r, 'certs_found', None),
                'new_certs': getattr(r, 'new_certs', None),
                'changed_certs': getattr(r, 'changed_certs', None),
                'errors': getattr(r, 'errors', None),
                'triggered_by': getattr(r, 'triggered_by', None),
                'triggered_by_user': getattr(r, 'triggered_by_user', None),
                'timeout': getattr(r, 'timeout', None),
                'max_workers': getattr(r, 'max_workers', None),
                'resolve_dns': getattr(r, 'resolve_dns', True),
            })
        return runs
    
    def _export_discovered_certificates(self, include: bool) -> List[Dict[str, Any]]:
        """Export discovered certificates"""
        if not include:
            return []
        try:
            from models.discovered_certificate import DiscoveredCertificate
        except Exception:
            return []
        items = []
        for d in DiscoveredCertificate.query.all():
            items.append({
                'scan_profile_id': getattr(d, 'scan_profile_id', None),
                'target': getattr(d, 'target', None),
                'port': getattr(d, 'port', None),
                'sni_hostname': getattr(d, 'sni_hostname', None),
                'subject': getattr(d, 'subject', None),
                'issuer': getattr(d, 'issuer', None),
                'serial_number': getattr(d, 'serial_number', None),
                'not_before': d.not_before.isoformat() if getattr(d, 'not_before', None) else None,
                'not_after': d.not_after.isoformat() if getattr(d, 'not_after', None) else None,
                'fingerprint_sha256': getattr(d, 'fingerprint_sha256', None),
                'pem_certificate': getattr(d, 'pem_certificate', None),
                'status': getattr(d, 'status', None),
                'ucm_certificate_id': getattr(d, 'ucm_certificate_id', None),
                'first_seen': d.first_seen.isoformat() if getattr(d, 'first_seen', None) else None,
                'last_seen': d.last_seen.isoformat() if getattr(d, 'last_seen', None) else None,
                'last_changed_at': d.last_changed_at.isoformat() if getattr(d, 'last_changed_at', None) else None,
                'previous_fingerprint': getattr(d, 'previous_fingerprint', None),
                'dns_hostname': getattr(d, 'dns_hostname', None),
                'san_dns_names': getattr(d, 'san_dns_names', None),
                'san_ip_addresses': getattr(d, 'san_ip_addresses', None),
                'san_emails': getattr(d, 'san_emails', None),
                'san_uris': getattr(d, 'san_uris', None),
                'scan_error': getattr(d, 'scan_error', None),
            })
        return items
    
    def _export_approval_requests(self, include: bool) -> List[Dict[str, Any]]:
        """Export approval requests (pending + recent)"""
        if not include:
            return []
        try:
            from models.policy import ApprovalRequest
        except Exception:
            return []
        items = []
        for a in ApprovalRequest.query.all():
            items.append({
                'request_type': getattr(a, 'request_type', None),
                'certificate_id': getattr(a, 'certificate_id', None),
                'request_data': getattr(a, 'request_data', None),
                'policy_id': getattr(a, 'policy_id', None),
                'requester_id': getattr(a, 'requester_id', None),
                'requester_comment': getattr(a, 'requester_comment', None),
                'status': getattr(a, 'status', None),
                'approvals': getattr(a, 'approvals', None),
                'required_approvals': getattr(a, 'required_approvals', 1),
                'created_at': a.created_at.isoformat() if getattr(a, 'created_at', None) else None,
                'expires_at': a.expires_at.isoformat() if getattr(a, 'expires_at', None) else None,
                'resolved_at': a.resolved_at.isoformat() if getattr(a, 'resolved_at', None) else None,
            })
        return items
    
    def _export_scep_requests(self, include: bool) -> List[Dict[str, Any]]:
        """Export SCEP enrollment history"""
        if not include:
            return []
        try:
            from models import SCEPRequest
        except Exception:
            return []
        items = []
        for r in SCEPRequest.query.all():
            items.append({
                'transaction_id': r.transaction_id,
                'csr': r.csr,
                'status': r.status,
                'approved_by': r.approved_by,
                'approved_at': r.approved_at.isoformat() if getattr(r, 'approved_at', None) else None,
                'rejection_reason': r.rejection_reason,
                'cert_refid': r.cert_refid,
                'subject': r.subject,
                'client_ip': r.client_ip,
                'created_at': r.created_at.isoformat() if getattr(r, 'created_at', None) else None,
            })
        return items
    
    def _export_acme_client_orders(self, include: bool) -> List[Dict[str, Any]]:
        """Export ACME client (proxy) order history"""
        if not include:
            return []
        try:
            from models.acme_models import AcmeClientOrder
        except Exception:
            return []
        items = []
        for o in AcmeClientOrder.query.all():
            items.append({
                'domains': getattr(o, 'domains', None),
                'challenge_type': getattr(o, 'challenge_type', None),
                'environment': getattr(o, 'environment', None),
                'key_type': getattr(o, 'key_type', None),
                'status': getattr(o, 'status', None),
                'order_url': getattr(o, 'order_url', None),
                'account_url': getattr(o, 'account_url', None),
                'finalize_url': getattr(o, 'finalize_url', None),
                'certificate_url': getattr(o, 'certificate_url', None),
                'challenges_data': getattr(o, 'challenges_data', None),
                'dns_provider_id': getattr(o, 'dns_provider_id', None),
                'certificate_id': getattr(o, 'certificate_id', None),
                'renewal_enabled': getattr(o, 'renewal_enabled', False),
                'last_renewal_at': o.last_renewal_at.isoformat() if getattr(o, 'last_renewal_at', None) else None,
                'renewal_failures': getattr(o, 'renewal_failures', 0),
                'error_message': getattr(o, 'error_message', None),
                'last_error_at': o.last_error_at.isoformat() if getattr(o, 'last_error_at', None) else None,
                'is_proxy_order': getattr(o, 'is_proxy_order', False),
                'dns_records_created': getattr(o, 'dns_records_created', None),
                'client_jwk_thumbprint': getattr(o, 'client_jwk_thumbprint', None),
                'upstream_order_url': getattr(o, 'upstream_order_url', None),
                'upstream_authz_urls': getattr(o, 'upstream_authz_urls', None),
                'expires_at': o.expires_at.isoformat() if getattr(o, 'expires_at', None) else None,
                'created_at': o.created_at.isoformat() if getattr(o, 'created_at', None) else None,
            })
        return items
    
    def _export_hsm_keys(self, include: bool) -> List[Dict[str, Any]]:
        """Export HSM key registrations (labels/ids, not the key material)"""
        if not include:
            return []
        try:
            from models.hsm import HsmKey
        except Exception:
            return []
        items = []
        for k in HsmKey.query.all():
            items.append({
                'provider_id': k.provider_id,
                'key_identifier': getattr(k, 'key_identifier', None),
                'label': getattr(k, 'label', None),
                'algorithm': getattr(k, 'algorithm', None),
                'key_type': getattr(k, 'key_type', None),
                'purpose': getattr(k, 'purpose', None),
                'public_key_pem': getattr(k, 'public_key_pem', None),
                'is_extractable': getattr(k, 'is_extractable', False),
                'extra_data': getattr(k, 'extra_data', None),
                'created_at': k.created_at.isoformat() if getattr(k, 'created_at', None) else None,
            })
        return items
    
    def _export_audit_logs(self, include: bool) -> List[Dict[str, Any]]:
        """Export audit log chain (opt-in — can be very large)"""
        if not include:
            return []
        try:
            from models import AuditLog
        except Exception:
            return []
        items = []
        for a in AuditLog.query.order_by(AuditLog.id.asc()).all():
            items.append({
                'timestamp': a.timestamp.isoformat() if a.timestamp else None,
                'username': a.username,
                'action': a.action,
                'resource_type': a.resource_type,
                'resource_id': a.resource_id,
                'resource_name': a.resource_name,
                'details': a.details,
                'ip_address': a.ip_address,
                'user_agent': a.user_agent,
                'success': bool(a.success),
                'prev_hash': a.prev_hash,
                'entry_hash': a.entry_hash,
            })
        return items
    
    def _export_https_files(self) -> Dict[str, Any]:
        """Export HTTPS server certificate and key files"""
        result = {}
        try:
            if Config.HTTPS_CERT_PATH.exists():
                result['cert_pem'] = Config.HTTPS_CERT_PATH.read_text()
        except Exception:
            pass
        try:
            if Config.HTTPS_KEY_PATH.exists():
                result['key_pem'] = Config.HTTPS_KEY_PATH.read_text()
        except Exception:
            pass
        return result

    def _encrypt_private_keys(self, backup_data: Dict, master_key: bytes) -> Dict:
        """Encrypt all private keys in the backup data"""
        # Encrypt CA private keys
        for ca in backup_data.get('certificate_authorities', []):
            if '_private_key_plaintext' in ca:
                ca['private_key_pem_encrypted'] = self._encrypt_private_key(
                    ca['_private_key_plaintext'],
                    master_key
                )
                del ca['_private_key_plaintext']
        
        # Encrypt certificate private keys
        for cert in backup_data.get('certificates', []):
            if '_private_key_plaintext' in cert:
                cert['private_key_pem_encrypted'] = self._encrypt_private_key(
                    cert['_private_key_plaintext'],
                    master_key
                )
                del cert['_private_key_plaintext']
        
        # Encrypt SSH CA private keys
        for ssh_ca in backup_data.get('ssh_cas', []):
            if '_private_key_plaintext' in ssh_ca:
                ssh_ca['private_key_pem_encrypted'] = self._encrypt_private_key(
                    ssh_ca['_private_key_plaintext'],
                    master_key
                )
                del ssh_ca['_private_key_plaintext']
        
        return backup_data
    
    def _decrypt_v1(self, backup_bytes: bytes, password: str) -> Tuple[bytes, Dict[str, Any]]:
        """Decrypt legacy v1 format: [salt(32)][nonce(12)][ciphertext+tag]"""
        if len(backup_bytes) < self.SALT_SIZE + self.NONCE_SIZE:
            raise ValueError("Invalid backup file: too small")
        
        master_salt = backup_bytes[:self.SALT_SIZE]
        encrypted_data = backup_bytes[self.SALT_SIZE:]
        master_key = self._derive_pbkdf2(password, master_salt, self.PBKDF2_ITERATIONS)
        
        try:
            nonce = encrypted_data[:self.NONCE_SIZE]
            ciphertext = encrypted_data[self.NONCE_SIZE:]
            plaintext = AESGCM(master_key).decrypt(nonce, ciphertext, None)
        except Exception:
            raise ValueError("Decryption failed - wrong password or corrupted file")
        
        try:
            backup_data = json.loads(plaintext.decode())
        except json.JSONDecodeError:
            raise ValueError("Invalid backup format: not valid JSON")
        
        return master_key, backup_data
    
    def _decrypt_v2(self, backup_bytes: bytes, password: str) -> Tuple[bytes, Dict[str, Any]]:
        """Decrypt v2 format: magic+version+flags+kdf+metadata+ciphertext"""
        if len(backup_bytes) < 10:
            raise ValueError("Invalid backup file: truncated header")
        
        magic = backup_bytes[:4]
        if magic != self.MAGIC:
            raise ValueError("Invalid backup file: bad magic bytes")
        
        version = backup_bytes[4]
        flags = backup_bytes[5]
        kdf_id = backup_bytes[6]
        # reserved = backup_bytes[7]
        
        if version != self.FORMAT_VERSION_V2:
            raise ValueError(f"Unsupported backup format version: {version}")
        
        metadata_len = struct.unpack('>H', backup_bytes[8:10])[0]
        if len(backup_bytes) < 10 + metadata_len + self.NONCE_SIZE:
            raise ValueError("Invalid backup file: truncated")
        
        metadata_bytes = backup_bytes[10:10 + metadata_len]
        ciphertext = backup_bytes[10 + metadata_len:]
        
        try:
            metadata = json.loads(metadata_bytes.decode())
        except json.JSONDecodeError:
            raise ValueError("Invalid backup metadata")
        
        # Derive key
        salt = base64.b64decode(metadata['salt_b64'])
        nonce = base64.b64decode(metadata['nonce_b64'])
        kdf_params = metadata.get('kdf', {})
        
        if kdf_id == self.KDF_ARGON2ID:
            if not _ARGON2_AVAILABLE:
                raise ValueError("Backup uses Argon2id but argon2-cffi is not installed")
            master_key = self._derive_argon2id(
                password, salt,
                time_cost=kdf_params.get('time_cost', self.ARGON2_TIME_COST),
                memory_cost=kdf_params.get('memory_cost', self.ARGON2_MEMORY_COST),
                parallelism=kdf_params.get('parallelism', self.ARGON2_PARALLELISM),
                hash_len=kdf_params.get('hash_len', self.KEY_SIZE),
            )
        elif kdf_id == self.KDF_PBKDF2:
            master_key = self._derive_pbkdf2(
                password, salt, kdf_params.get('iterations', self.PBKDF2_ITERATIONS_V2)
            )
        else:
            raise ValueError(f"Unknown KDF id: {kdf_id}")
        
        # Decrypt
        try:
            # v2 uses magic bytes as AAD to authenticate the container
            plaintext = AESGCM(master_key).decrypt(nonce, ciphertext, self.MAGIC)
        except Exception:
            raise ValueError("Decryption failed - wrong password or corrupted file")
        
        # Decompress if gzipped
        if flags & self.FLAG_GZIP:
            try:
                plaintext = gzip.decompress(plaintext)
            except Exception:
                raise ValueError("Invalid backup: gzip decompression failed")
        
        try:
            backup_data = json.loads(plaintext.decode())
        except json.JSONDecodeError:
            raise ValueError("Invalid backup format: not valid JSON")
        
        return master_key, backup_data
    
    def restore_backup(self, backup_bytes: bytes, password: str) -> Dict[str, Any]:
        """
        Restore from encrypted backup. Auto-detects format v1 (legacy) or v2.
        
        Args:
            backup_bytes: Encrypted backup file content
            password: Decryption password
            
        Returns:
            Dict with restore results
        """
        # Detect format from magic bytes
        if len(backup_bytes) >= 4 and backup_bytes[:4] == self.MAGIC:
            master_key, backup_data = self._decrypt_v2(backup_bytes, password)
        else:
            master_key, backup_data = self._decrypt_v1(backup_bytes, password)
        
        # Verify checksum
        saved_checksum = backup_data.pop('checksum', None)
        if saved_checksum:
            json_str = json.dumps(backup_data, indent=2, sort_keys=True)
            calc_checksum = hashlib.sha256(json_str.encode()).hexdigest()
            if calc_checksum != saved_checksum.get('value'):
                raise ValueError("Backup checksum mismatch - file may be corrupted")
        
        # Restore data
        results = {
            'users': 0,
            'cas': 0,
            'certificates': 0,
            'acme_accounts': 0,
            'acme_eab_credentials': 0,
            'settings': 0,
            'groups': 0,
            'custom_roles': 0,
            'certificate_templates': 0,
            'trusted_certificates': 0,
            'sso_providers': 0,
            'hsm_providers': 0,
            'api_keys': 0,
            'smtp_config': 0,
            'notification_config': 0,
            'certificate_policies': 0,
            'auth_certificates': 0,
            'dns_providers': 0,
            'acme_domains': 0,
            'acme_local_domains': 0,
            'https_server': 0,
        }
        
        # Restore users
        for user_data in backup_data.get('users', []):
            existing = User.query.filter_by(username=user_data['username']).first()
            if existing:
                existing.email = user_data.get('email')
                existing.full_name = user_data.get('full_name')
                existing.role = user_data.get('role', 'user')
                existing.active = user_data.get('active', True)
                existing.password_hash = user_data.get('password_hash')
            else:
                new_user = User(
                    username=user_data['username'],
                    email=user_data.get('email'),
                    full_name=user_data.get('full_name'),
                    role=user_data.get('role', 'user'),
                    active=user_data.get('active', True),
                    password_hash=user_data.get('password_hash')
                )
                db.session.add(new_user)
            results['users'] += 1
        
        # Restore CAs
        import base64
        for ca_data in backup_data.get('certificate_authorities', []):
            existing = CA.query.filter_by(refid=ca_data['refid']).first()
            
            # Decrypt private key if encrypted
            prv_pem = None
            if ca_data.get('private_key_pem_encrypted'):
                prv_pem = self._decrypt_private_key(
                    ca_data['private_key_pem_encrypted'], 
                    master_key
                )
            
            if existing:
                existing.descr = ca_data.get('descr')
                existing.crt = base64.b64encode(ca_data['certificate_pem'].encode()).decode() if ca_data.get('certificate_pem') else None
                prv_b64 = base64.b64encode(prv_pem.encode()).decode() if prv_pem else None
                if prv_b64:
                    from security.encryption import encrypt_private_key
                    prv_b64 = encrypt_private_key(prv_b64)
                existing.prv = prv_b64
            else:
                prv_b64 = base64.b64encode(prv_pem.encode()).decode() if prv_pem else None
                if prv_b64:
                    from security.encryption import encrypt_private_key
                    prv_b64 = encrypt_private_key(prv_b64)
                new_ca = CA(
                    refid=ca_data['refid'],
                    descr=ca_data.get('descr'),
                    subject=ca_data.get('subject'),
                    issuer=ca_data.get('issuer'),
                    serial=ca_data.get('serial'),
                    caref=ca_data.get('caref'),
                    crt=base64.b64encode(ca_data['certificate_pem'].encode()).decode() if ca_data.get('certificate_pem') else None,
                    prv=prv_b64
                )
                db.session.add(new_ca)
            results['cas'] += 1
        
        # Restore Certificates
        from datetime import datetime as _dt
        for cert_data in backup_data.get('certificates', []):
            existing = Certificate.query.filter_by(refid=cert_data['refid']).first()
            
            # Decrypt private key if encrypted
            prv_pem = None
            if cert_data.get('private_key_pem_encrypted'):
                prv_pem = self._decrypt_private_key(
                    cert_data['private_key_pem_encrypted'],
                    master_key
                )
            
            prv_b64 = None
            if prv_pem:
                prv_b64 = base64.b64encode(prv_pem.encode()).decode()
                from security.encryption import encrypt_private_key
                prv_b64 = encrypt_private_key(prv_b64)
            
            def _parse_dt(val):
                if not val:
                    return None
                try:
                    return _dt.fromisoformat(val.replace('Z', '+00:00'))
                except Exception:
                    return None
            
            if existing:
                existing.descr = cert_data.get('descr')
                existing.crt = base64.b64encode(cert_data['certificate_pem'].encode()).decode() if cert_data.get('certificate_pem') else None
                if prv_b64:
                    existing.prv = prv_b64
                # Restore revocation + archival state (critical — was missing)
                existing.revoked = bool(cert_data.get('revoked', False))
                existing.revoked_at = _parse_dt(cert_data.get('revoked_at'))
                existing.revoke_reason = cert_data.get('revoke_reason')
                existing.archived = bool(cert_data.get('archived', False))
            else:
                new_cert = Certificate(
                    refid=cert_data['refid'],
                    descr=cert_data.get('descr'),
                    caref=cert_data.get('caref'),
                    cert_type=cert_data.get('cert_type'),
                    subject=cert_data.get('subject'),
                    issuer=cert_data.get('issuer'),
                    serial_number=cert_data.get('serial_number'),
                    valid_from=_parse_dt(cert_data.get('valid_from')),
                    valid_to=_parse_dt(cert_data.get('valid_to')),
                    key_algo=cert_data.get('key_algo'),
                    san_dns=cert_data.get('san_dns'),
                    san_ip=cert_data.get('san_ip'),
                    san_email=cert_data.get('san_email'),
                    san_uri=cert_data.get('san_uri'),
                    ocsp_uri=cert_data.get('ocsp_uri'),
                    ocsp_must_staple=bool(cert_data.get('ocsp_must_staple', False)),
                    private_key_location=cert_data.get('private_key_location', 'stored'),
                    revoked=bool(cert_data.get('revoked', False)),
                    revoked_at=_parse_dt(cert_data.get('revoked_at')),
                    revoke_reason=cert_data.get('revoke_reason'),
                    archived=bool(cert_data.get('archived', False)),
                    imported_from=cert_data.get('imported_from'),
                    created_by=cert_data.get('created_by'),
                    source=cert_data.get('source', 'manual'),
                    template_id=cert_data.get('template_id'),
                    owner_group_id=cert_data.get('owner_group_id'),
                    crt=base64.b64encode(cert_data['certificate_pem'].encode()).decode() if cert_data.get('certificate_pem') else None,
                    csr=base64.b64encode(cert_data['csr_pem'].encode()).decode() if cert_data.get('csr_pem') else None,
                    prv=prv_b64
                )
                db.session.add(new_cert)
            results['certificates'] += 1
        
        # Restore ACME accounts (RFC 8555 §7.1.2)
        for acme_data in backup_data.get('acme_accounts', []):
            account_id = acme_data.get('account_id')
            jwk_thumbprint = acme_data.get('jwk_thumbprint')
            if not account_id or not jwk_thumbprint or not acme_data.get('jwk'):
                # Legacy v1 backup with email/account_url/key_pem — not restorable as
                # ACME server account (different shape). Skip silently.
                continue
            existing = AcmeAccount.query.filter_by(account_id=account_id).first()
            if existing:
                existing.jwk = acme_data['jwk']
                existing.jwk_thumbprint = jwk_thumbprint
                existing.contact = acme_data.get('contact')
                existing.status = acme_data.get('status', 'valid')
                existing.terms_of_service_agreed = acme_data.get('terms_of_service_agreed', False)
                existing.external_account_binding = acme_data.get('external_account_binding')
            else:
                new_acme = AcmeAccount(
                    account_id=account_id,
                    jwk=acme_data['jwk'],
                    jwk_thumbprint=jwk_thumbprint,
                    contact=acme_data.get('contact'),
                    status=acme_data.get('status', 'valid'),
                    terms_of_service_agreed=acme_data.get('terms_of_service_agreed', False),
                    external_account_binding=acme_data.get('external_account_binding'),
                )
                db.session.add(new_acme)
            results['acme_accounts'] += 1

        # Restore ACME EAB credentials (RFC 8555 §7.3.4)
        try:
            from models.acme_models import AcmeEabCredential
            from datetime import datetime as _dt
            def _parse_dt(v):
                if not v:
                    return None
                try:
                    return _dt.fromisoformat(v.replace('Z', '+00:00'))
                except Exception:
                    return None
            for eab in backup_data.get('acme_eab_credentials', []):
                kid = eab.get('kid')
                if not kid or not eab.get('hmac_key_b64'):
                    continue
                existing = AcmeEabCredential.query.filter_by(kid=kid).first()
                if existing:
                    existing.hmac_key_b64 = eab['hmac_key_b64']
                    existing.label = eab.get('label')
                    existing.status = eab.get('status', 'active')
                    existing.used_at = _parse_dt(eab.get('used_at'))
                    existing.used_by_account_id = eab.get('used_by_account_id')
                    existing.revoked_at = _parse_dt(eab.get('revoked_at'))
                    existing.revoked_by_user_id = eab.get('revoked_by_user_id')
                    existing.expires_at = _parse_dt(eab.get('expires_at'))
                else:
                    new_eab = AcmeEabCredential(
                        kid=kid,
                        hmac_key_b64=eab['hmac_key_b64'],
                        label=eab.get('label'),
                        created_by_user_id=eab.get('created_by_user_id'),
                        expires_at=_parse_dt(eab.get('expires_at')),
                        used_at=_parse_dt(eab.get('used_at')),
                        used_by_account_id=eab.get('used_by_account_id'),
                        revoked_at=_parse_dt(eab.get('revoked_at')),
                        revoked_by_user_id=eab.get('revoked_by_user_id'),
                        status=eab.get('status', 'active'),
                    )
                    db.session.add(new_eab)
                results.setdefault('acme_eab_credentials', 0)
                results['acme_eab_credentials'] += 1
        except Exception as e:
            logger.warning(f"Failed to restore acme_eab_credentials: {e}")

        # Restore settings
        config_data = backup_data.get('configuration', {}).get('settings', {})
        for key, value in config_data.items():
            existing = SystemConfig.query.filter_by(key=key).first()
            if existing:
                existing.value = value
            else:
                new_config = SystemConfig(key=key, value=value)
                db.session.add(new_config)
            results['settings'] += 1
        
        db.session.commit()
        
        # Regenerate CA/cert files on disk
        from utils.file_naming import ca_cert_path, ca_key_path, cert_cert_path, cert_key_path, cert_csr_path
        
        for ca in CA.query.all():
            if ca.crt:
                try:
                    cert_pem = base64.b64decode(ca.crt)
                    p = ca_cert_path(ca)
                    Config.CA_DIR.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(cert_pem)
                except Exception:
                    pass
            if ca.prv:
                try:
                    from security.encryption import decrypt_private_key
                    prv_pem = base64.b64decode(decrypt_private_key(ca.prv))
                    p = ca_key_path(ca)
                    Config.PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(prv_pem)
                    p.chmod(0o600)
                except Exception:
                    pass
        
        for cert in Certificate.query.all():
            if cert.crt:
                try:
                    cert_pem_bytes = base64.b64decode(cert.crt)
                    p = cert_cert_path(cert)
                    Config.CERT_DIR.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(cert_pem_bytes)
                except Exception:
                    pass
            if cert.csr:
                try:
                    csr_data = cert.csr
                    if csr_data.startswith('-----BEGIN'):
                        csr_bytes = csr_data.encode('utf-8')
                    else:
                        csr_bytes = base64.b64decode(csr_data)
                    p = cert_csr_path(cert)
                    p.write_bytes(csr_bytes)
                except Exception:
                    pass
            if cert.prv:
                try:
                    from security.encryption import decrypt_private_key
                    prv_pem_bytes = base64.b64decode(decrypt_private_key(cert.prv))
                    p = cert_key_path(cert)
                    Config.PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(prv_pem_bytes)
                    p.chmod(0o600)
                except Exception:
                    pass
        
        # Restore groups
        from models.group import Group, GroupMember
        for grp_data in backup_data.get('groups', []):
            existing = Group.query.filter_by(name=grp_data['name']).first()
            if existing:
                existing.description = grp_data.get('description')
                existing.permissions = grp_data.get('permissions')
                group = existing
            else:
                group = Group(
                    name=grp_data['name'],
                    description=grp_data.get('description'),
                    permissions=grp_data.get('permissions'),
                )
                db.session.add(group)
                db.session.flush()
            # Restore members
            for m_data in grp_data.get('members', []):
                existing_m = GroupMember.query.filter_by(
                    group_id=group.id, user_id=m_data['user_id']
                ).first()
                if not existing_m:
                    db.session.add(GroupMember(
                        group_id=group.id,
                        user_id=m_data['user_id'],
                        role=m_data.get('role', 'member'),
                    ))
            results['groups'] += 1
        
        # Restore custom roles
        from models.rbac import CustomRole
        for role_data in backup_data.get('custom_roles', []):
            existing = CustomRole.query.filter_by(name=role_data['name']).first()
            if existing:
                existing.description = role_data.get('description')
                existing.permissions = role_data.get('permissions')
                existing.is_system = role_data.get('is_system', False)
            else:
                new_role = CustomRole(
                    name=role_data['name'],
                    description=role_data.get('description'),
                    permissions=role_data.get('permissions'),
                    is_system=role_data.get('is_system', False),
                )
                db.session.add(new_role)
            results['custom_roles'] += 1
        
        # Restore certificate templates
        from models.certificate_template import CertificateTemplate as CT
        for t_data in backup_data.get('certificate_templates', []):
            existing = CT.query.filter_by(name=t_data['name']).first()
            if existing:
                existing.description = t_data.get('description')
                existing.template_type = t_data.get('template_type')
                existing.key_type = t_data.get('key_type')
                existing.validity_days = t_data.get('validity_days')
                existing.digest = t_data.get('digest')
                existing.dn_template = t_data.get('dn_template')
                existing.extensions_template = t_data.get('extensions_template')
                existing.is_system = t_data.get('is_system', False)
                existing.is_active = t_data.get('is_active', True)
            else:
                new_t = CT(
                    name=t_data['name'],
                    description=t_data.get('description'),
                    template_type=t_data.get('template_type', 'custom'),
                    key_type=t_data.get('key_type'),
                    validity_days=t_data.get('validity_days'),
                    digest=t_data.get('digest'),
                    dn_template=t_data.get('dn_template'),
                    extensions_template=t_data.get('extensions_template', '{}'),
                    is_system=t_data.get('is_system', False),
                    is_active=t_data.get('is_active', True),
                    created_by=t_data.get('created_by'),
                )
                db.session.add(new_t)
            results['certificate_templates'] += 1
        
        # Restore trusted certificates
        from models.truststore import TrustedCertificate
        for tc_data in backup_data.get('trusted_certificates', []):
            existing = TrustedCertificate.query.filter_by(
                fingerprint_sha256=tc_data['fingerprint_sha256']
            ).first()
            if existing:
                existing.name = tc_data.get('name')
                existing.description = tc_data.get('description')
                existing.certificate_pem = tc_data.get('certificate_pem')
                existing.purpose = tc_data.get('purpose')
                existing.notes = tc_data.get('notes')
            else:
                new_tc = TrustedCertificate(
                    name=tc_data.get('name', ''),
                    description=tc_data.get('description'),
                    certificate_pem=tc_data.get('certificate_pem', ''),
                    fingerprint_sha256=tc_data['fingerprint_sha256'],
                    fingerprint_sha1=tc_data.get('fingerprint_sha1'),
                    subject=tc_data.get('subject'),
                    issuer=tc_data.get('issuer'),
                    serial_number=tc_data.get('serial_number'),
                    purpose=tc_data.get('purpose'),
                    added_by=tc_data.get('added_by'),
                    notes=tc_data.get('notes'),
                )
                db.session.add(new_tc)
            results['trusted_certificates'] += 1
        
        # Restore SSO providers
        from models.sso import SSOProvider
        for sso_data in backup_data.get('sso_providers', []):
            existing = SSOProvider.query.filter_by(name=sso_data['name']).first()
            if existing:
                sso = existing
            else:
                sso = SSOProvider(name=sso_data['name'])
                db.session.add(sso)
            sso.provider_type = sso_data.get('provider_type', 'oauth2')
            sso.enabled = sso_data.get('enabled', False)
            sso.is_default = sso_data.get('is_default', False)
            sso.display_name = sso_data.get('display_name')
            sso.icon = sso_data.get('icon')
            sso.default_role = sso_data.get('default_role', 'viewer')
            sso.auto_create_users = sso_data.get('auto_create_users', True)
            sso.auto_update_users = sso_data.get('auto_update_users', True)
            sso.attribute_mapping = sso_data.get('attribute_mapping')
            sso.role_mapping = sso_data.get('role_mapping')
            sso.saml_entity_id = sso_data.get('saml_entity_id')
            sso.saml_sso_url = sso_data.get('saml_sso_url')
            sso.saml_slo_url = sso_data.get('saml_slo_url')
            sso.saml_certificate = sso_data.get('saml_certificate')
            sso.saml_sign_requests = sso_data.get('saml_sign_requests', True)
            sso.oauth2_client_id = sso_data.get('oauth2_client_id')
            sso._oauth2_client_secret = sso_data.get('oauth2_client_secret')
            sso.oauth2_auth_url = sso_data.get('oauth2_auth_url')
            sso.oauth2_token_url = sso_data.get('oauth2_token_url')
            sso.oauth2_userinfo_url = sso_data.get('oauth2_userinfo_url')
            sso.oauth2_scopes = sso_data.get('oauth2_scopes')
            sso.ldap_server = sso_data.get('ldap_server')
            sso.ldap_port = sso_data.get('ldap_port', 389)
            sso.ldap_use_ssl = sso_data.get('ldap_use_ssl', False)
            sso.ldap_bind_dn = sso_data.get('ldap_bind_dn')
            sso._ldap_bind_password = sso_data.get('ldap_bind_password')
            sso.ldap_base_dn = sso_data.get('ldap_base_dn')
            sso.ldap_user_filter = sso_data.get('ldap_user_filter')
            sso.ldap_group_filter = sso_data.get('ldap_group_filter')
            sso.ldap_username_attr = sso_data.get('ldap_username_attr')
            sso.ldap_email_attr = sso_data.get('ldap_email_attr')
            sso.ldap_fullname_attr = sso_data.get('ldap_fullname_attr')
            results['sso_providers'] += 1
        
        # Restore HSM providers
        from models.hsm import HsmProvider
        for hsm_data in backup_data.get('hsm_providers', []):
            existing = HsmProvider.query.filter_by(name=hsm_data['name']).first()
            if existing:
                existing.type = hsm_data.get('type')
                existing.config = hsm_data.get('config', '{}')
                existing.status = hsm_data.get('status', 'unknown')
            else:
                new_hsm = HsmProvider(
                    name=hsm_data['name'],
                    type=hsm_data.get('type', 'pkcs11'),
                    config=hsm_data.get('config', '{}'),
                    status=hsm_data.get('status', 'unknown'),
                )
                db.session.add(new_hsm)
            results['hsm_providers'] += 1
        
        # Restore API keys
        from models.api_key import APIKey
        for ak_data in backup_data.get('api_keys', []):
            existing = APIKey.query.filter_by(key_hash=ak_data['key_hash']).first()
            if existing:
                existing.name = ak_data.get('name')
                existing.permissions = ak_data.get('permissions', '[]')
                existing.is_active = ak_data.get('is_active', True)
            else:
                new_ak = APIKey(
                    user_id=ak_data.get('user_id', 1),
                    key_hash=ak_data['key_hash'],
                    name=ak_data.get('name', 'restored'),
                    permissions=ak_data.get('permissions', '[]'),
                    is_active=ak_data.get('is_active', True),
                )
                db.session.add(new_ak)
            results['api_keys'] += 1
        
        # Restore SMTP config
        from models.email_notification import SMTPConfig, NotificationConfig
        for smtp_data in backup_data.get('smtp_config', []):
            existing = SMTPConfig.query.first()
            if existing:
                smtp = existing
            else:
                smtp = SMTPConfig()
                db.session.add(smtp)
            smtp.smtp_host = smtp_data.get('smtp_host')
            smtp.smtp_port = smtp_data.get('smtp_port', 587)
            smtp.smtp_user = smtp_data.get('smtp_user')
            smtp._smtp_password = smtp_data.get('smtp_password')
            smtp.smtp_from = smtp_data.get('smtp_from')
            smtp.smtp_from_name = smtp_data.get('smtp_from_name')
            smtp.smtp_use_tls = smtp_data.get('smtp_use_tls', True)
            smtp.smtp_use_ssl = smtp_data.get('smtp_use_ssl', False)
            smtp.enabled = smtp_data.get('enabled', False)
            results['smtp_config'] += 1
        
        # Restore notification config
        for nc_data in backup_data.get('notification_config', []):
            existing = NotificationConfig.query.filter_by(type=nc_data['type']).first()
            if existing:
                existing.enabled = nc_data.get('enabled', True)
                existing.days_before = nc_data.get('days_before')
                existing.recipients = nc_data.get('recipients')
                existing.subject_template = nc_data.get('subject_template')
                existing.description = nc_data.get('description')
                existing.cooldown_hours = nc_data.get('cooldown_hours', 24)
            else:
                new_nc = NotificationConfig(
                    type=nc_data['type'],
                    enabled=nc_data.get('enabled', True),
                    days_before=nc_data.get('days_before'),
                    recipients=nc_data.get('recipients'),
                    subject_template=nc_data.get('subject_template'),
                    description=nc_data.get('description'),
                    cooldown_hours=nc_data.get('cooldown_hours', 24),
                )
                db.session.add(new_nc)
            results['notification_config'] += 1
        
        # Restore certificate policies
        from models.policy import CertificatePolicy
        for pol_data in backup_data.get('certificate_policies', []):
            existing = CertificatePolicy.query.filter_by(name=pol_data['name']).first()
            if existing:
                existing.description = pol_data.get('description')
                existing.policy_type = pol_data.get('policy_type')
                existing.rules = pol_data.get('rules', '{}')
                existing.requires_approval = pol_data.get('requires_approval', False)
                existing.min_approvers = pol_data.get('min_approvers', 1)
                existing.notify_on_violation = pol_data.get('notify_on_violation', True)
                existing.notification_emails = pol_data.get('notification_emails')
                existing.is_active = pol_data.get('is_active', True)
                existing.priority = pol_data.get('priority', 100)
            else:
                new_pol = CertificatePolicy(
                    name=pol_data['name'],
                    description=pol_data.get('description'),
                    policy_type=pol_data.get('policy_type', 'issuance'),
                    ca_id=pol_data.get('ca_id'),
                    template_id=pol_data.get('template_id'),
                    rules=pol_data.get('rules', '{}'),
                    requires_approval=pol_data.get('requires_approval', False),
                    approval_group_id=pol_data.get('approval_group_id'),
                    min_approvers=pol_data.get('min_approvers', 1),
                    notify_on_violation=pol_data.get('notify_on_violation', True),
                    notification_emails=pol_data.get('notification_emails'),
                    is_active=pol_data.get('is_active', True),
                    priority=pol_data.get('priority', 100),
                    created_by=pol_data.get('created_by'),
                )
                db.session.add(new_pol)
            results['certificate_policies'] += 1
        
        # Restore auth certificates
        from models.auth_certificate import AuthCertificate
        for ac_data in backup_data.get('auth_certificates', []):
            existing = AuthCertificate.query.filter_by(
                cert_serial=ac_data['cert_serial']
            ).first()
            cert_pem_val = ac_data.get('cert_pem')
            if isinstance(cert_pem_val, str) and cert_pem_val:
                try:
                    cert_pem_val = base64.b64decode(cert_pem_val)
                except Exception:
                    cert_pem_val = cert_pem_val.encode('utf-8')
            if existing:
                existing.cert_pem = cert_pem_val
                existing.cert_subject = ac_data.get('cert_subject', '')
                existing.cert_issuer = ac_data.get('cert_issuer')
                existing.cert_fingerprint = ac_data.get('cert_fingerprint')
                existing.name = ac_data.get('name')
                existing.enabled = ac_data.get('enabled', True)
            else:
                new_ac = AuthCertificate(
                    user_id=ac_data.get('user_id', 1),
                    cert_pem=cert_pem_val,
                    cert_serial=ac_data['cert_serial'],
                    cert_subject=ac_data.get('cert_subject', ''),
                    cert_issuer=ac_data.get('cert_issuer'),
                    cert_fingerprint=ac_data.get('cert_fingerprint'),
                    name=ac_data.get('name'),
                    enabled=ac_data.get('enabled', True),
                )
                db.session.add(new_ac)
            results['auth_certificates'] += 1
        
        # Restore DNS providers
        from models.acme_models import DnsProvider, AcmeDomain
        for dp_data in backup_data.get('dns_providers', []):
            existing = DnsProvider.query.filter_by(name=dp_data['name']).first()
            if existing:
                existing.provider_type = dp_data.get('provider_type')
                existing.credentials = dp_data.get('credentials')
                existing.zones = dp_data.get('zones')
                existing.is_default = dp_data.get('is_default', False)
                existing.enabled = dp_data.get('enabled', True)
            else:
                new_dp = DnsProvider(
                    name=dp_data['name'],
                    provider_type=dp_data.get('provider_type', 'manual'),
                    credentials=dp_data.get('credentials'),
                    zones=dp_data.get('zones'),
                    is_default=dp_data.get('is_default', False),
                    enabled=dp_data.get('enabled', True),
                )
                db.session.add(new_dp)
            results['dns_providers'] += 1
        
        # Restore ACME domains
        for ad_data in backup_data.get('acme_domains', []):
            existing = AcmeDomain.query.filter_by(domain=ad_data['domain']).first()
            if existing:
                existing.is_wildcard_allowed = ad_data.get('is_wildcard_allowed', True)
                existing.auto_approve = ad_data.get('auto_approve', True)
                existing.issuing_ca_id = ad_data.get('issuing_ca_id')
                existing.created_by = ad_data.get('created_by')
            else:
                new_ad = AcmeDomain(
                    domain=ad_data['domain'],
                    dns_provider_id=ad_data.get('dns_provider_id', 1),
                    issuing_ca_id=ad_data.get('issuing_ca_id'),
                    is_wildcard_allowed=ad_data.get('is_wildcard_allowed', True),
                    auto_approve=ad_data.get('auto_approve', True),
                    created_by=ad_data.get('created_by'),
                )
                db.session.add(new_ad)
            results['acme_domains'] += 1
        
        # Restore ACME local domains
        from models.acme_models import AcmeLocalDomain
        for ld_data in backup_data.get('acme_local_domains', []):
            existing = AcmeLocalDomain.query.filter_by(domain=ld_data['domain']).first()
            if existing:
                existing.issuing_ca_id = ld_data.get('issuing_ca_id')
                existing.auto_approve = ld_data.get('auto_approve', True)
                existing.created_by = ld_data.get('created_by')
            else:
                new_ld = AcmeLocalDomain(
                    domain=ld_data['domain'],
                    issuing_ca_id=ld_data.get('issuing_ca_id'),
                    auto_approve=ld_data.get('auto_approve', True),
                    created_by=ld_data.get('created_by'),
                )
                db.session.add(new_ld)
            results['acme_local_domains'] += 1
        
        # Restore SSH CAs
        results.setdefault('ssh_cas', 0)
        for sca_data in backup_data.get('ssh_cas', []):
            try:
                from models.ssh import SSHCertificateAuthority
                from security.encryption import encrypt_private_key
            except Exception:
                break
            refid = sca_data.get('refid')
            existing = SSHCertificateAuthority.query.filter_by(refid=refid).first() if refid else None
            if existing:
                continue
            sca = SSHCertificateAuthority(
                refid=refid or str(uuid.uuid4()),
                descr=sca_data.get('descr', 'Imported SSH CA'),
                ca_type=sca_data.get('ca_type', 'user'),
                key_type=sca_data.get('key_type', 'ed25519'),
                public_key=sca_data.get('public_key', ''),
                private_key='',
                fingerprint=sca_data.get('fingerprint', ''),
                serial_counter=sca_data.get('serial_counter', 0),
                default_ttl=sca_data.get('default_ttl', 86400),
                max_ttl=sca_data.get('max_ttl', 0),
                default_extensions=sca_data.get('default_extensions'),
                allowed_principals=sca_data.get('allowed_principals'),
                comment=sca_data.get('comment'),
                created_by=sca_data.get('created_by'),
                owner_group_id=sca_data.get('owner_group_id'),
            )
            prv = sca_data.get('private_key_pem_encrypted') or sca_data.get('_private_key_plaintext')
            if prv:
                try:
                    if 'private_key_pem_encrypted' in sca_data:
                        prv = self._decrypt_private_key(sca_data['private_key_pem_encrypted'], master_key)
                    sca.private_key = encrypt_private_key(prv)
                except Exception as e:
                    logger.warning(f"Failed to restore SSH CA private key: {e}")
            db.session.add(sca)
            try:
                db.session.commit()
                results['ssh_cas'] += 1
            except Exception as e:
                db.session.rollback()
                logger.warning(f"SSH CA restore failed: {e}")
        
        # Restore SSH certificates
        results.setdefault('ssh_certificates', 0)
        for sc_data in backup_data.get('ssh_certificates', []):
            try:
                from models.ssh import SSHCertificate
            except Exception:
                break
            refid = sc_data.get('refid')
            if refid and SSHCertificate.query.filter_by(refid=refid).first():
                continue
            try:
                sc = SSHCertificate(
                    refid=refid or str(uuid.uuid4()),
                    descr=sc_data.get('descr'),
                    ssh_ca_id=sc_data['ssh_ca_id'],
                    cert_type=sc_data.get('cert_type', 'user'),
                    key_id=sc_data.get('key_id', ''),
                    public_key=sc_data.get('public_key', ''),
                    certificate=sc_data.get('certificate', ''),
                    principals=sc_data.get('principals', ''),
                    serial=sc_data.get('serial', 0),
                    valid_from=datetime.fromisoformat(sc_data['valid_from']) if sc_data.get('valid_from') else utc_now(),
                    valid_to=datetime.fromisoformat(sc_data['valid_to']) if sc_data.get('valid_to') else utc_now(),
                    key_type=sc_data.get('key_type', 'ed25519'),
                    fingerprint=sc_data.get('fingerprint', ''),
                    extensions=sc_data.get('extensions'),
                    critical_options=sc_data.get('critical_options'),
                    revoked=bool(sc_data.get('revoked', False)),
                    revoked_at=datetime.fromisoformat(sc_data['revoked_at']) if sc_data.get('revoked_at') else None,
                    revoke_reason=sc_data.get('revoke_reason'),
                    source=sc_data.get('source', 'web'),
                    created_by=sc_data.get('created_by'),
                    owner_group_id=sc_data.get('owner_group_id'),
                )
                db.session.add(sc)
                db.session.commit()
                results['ssh_certificates'] += 1
            except Exception as e:
                db.session.rollback()
                logger.warning(f"SSH cert restore failed: {e}")
        
        # Restore Microsoft CAs
        results.setdefault('microsoft_cas', 0)
        for msca_data in backup_data.get('microsoft_cas', []):
            try:
                from models.msca import MicrosoftCA
            except Exception:
                break
            if MicrosoftCA.query.filter_by(name=msca_data.get('name')).first():
                continue
            try:
                msca = MicrosoftCA(
                    name=msca_data['name'],
                    server=msca_data.get('server'),
                    ca_name=msca_data.get('ca_name'),
                    auth_method=msca_data.get('auth_method', 'ntlm'),
                    username=msca_data.get('username'),
                    password=msca_data.get('password'),
                    client_cert_pem=msca_data.get('client_cert_pem'),
                    client_key_pem=msca_data.get('client_key_pem'),
                    kerberos_principal=msca_data.get('kerberos_principal'),
                    kerberos_keytab_path=msca_data.get('kerberos_keytab_path'),
                    use_ssl=msca_data.get('use_ssl', True),
                    verify_ssl=msca_data.get('verify_ssl', True),
                    ca_bundle=msca_data.get('ca_bundle'),
                    default_template=msca_data.get('default_template'),
                    enabled=msca_data.get('enabled', True),
                    created_by=msca_data.get('created_by'),
                )
                db.session.add(msca)
                db.session.commit()
                results['microsoft_cas'] += 1
            except Exception as e:
                db.session.rollback()
                logger.warning(f"MSCA restore failed: {e}")
        
        # Restore scan profiles
        results.setdefault('scan_profiles', 0)
        for sp_data in backup_data.get('scan_profiles', []):
            try:
                from models.discovered_certificate import ScanProfile
            except Exception:
                break
            if ScanProfile.query.filter_by(name=sp_data.get('name')).first():
                continue
            try:
                sp = ScanProfile(
                    name=sp_data['name'],
                    description=sp_data.get('description'),
                    targets=sp_data.get('targets', '[]'),
                    ports=sp_data.get('ports', '[443]'),
                    schedule_enabled=sp_data.get('schedule_enabled', False),
                    schedule_interval_minutes=sp_data.get('schedule_interval_minutes'),
                    notify_on_new=sp_data.get('notify_on_new', True),
                    notify_on_change=sp_data.get('notify_on_change', True),
                    notify_on_expiry=sp_data.get('notify_on_expiry', True),
                    timeout=sp_data.get('timeout', 5),
                    max_workers=sp_data.get('max_workers', 10),
                    resolve_dns=sp_data.get('resolve_dns', True),
                )
                db.session.add(sp)
                db.session.commit()
                results['scan_profiles'] += 1
            except Exception as e:
                db.session.rollback()
                logger.warning(f"Scan profile restore failed: {e}")
        
        # Restore HSM keys
        results.setdefault('hsm_keys', 0)
        for k_data in backup_data.get('hsm_keys', []):
            try:
                from models.hsm import HsmKey
            except Exception:
                break
            try:
                existing = HsmKey.query.filter_by(
                    provider_id=k_data['provider_id'],
                    key_identifier=k_data.get('key_identifier'),
                ).first()
                if existing:
                    continue
                hk = HsmKey(
                    provider_id=k_data['provider_id'],
                    key_identifier=k_data.get('key_identifier'),
                    label=k_data.get('label'),
                    algorithm=k_data.get('algorithm'),
                    key_type=k_data.get('key_type'),
                    purpose=k_data.get('purpose'),
                    public_key_pem=k_data.get('public_key_pem'),
                    is_extractable=k_data.get('is_extractable', False),
                    extra_data=k_data.get('extra_data'),
                )
                db.session.add(hk)
                db.session.commit()
                results['hsm_keys'] += 1
            except Exception as e:
                db.session.rollback()
                logger.warning(f"HSM key restore failed: {e}")
        
        # Restore approval requests
        results.setdefault('approval_requests', 0)
        for ar_data in backup_data.get('approval_requests', []):
            try:
                from models.policy import ApprovalRequest
            except Exception:
                break
            try:
                ar = ApprovalRequest(
                    request_type=ar_data.get('request_type', 'certificate'),
                    certificate_id=ar_data.get('certificate_id'),
                    request_data=ar_data.get('request_data'),
                    policy_id=ar_data.get('policy_id'),
                    requester_id=ar_data.get('requester_id'),
                    requester_comment=ar_data.get('requester_comment'),
                    status=ar_data.get('status', 'pending'),
                    approvals=ar_data.get('approvals', '[]'),
                    required_approvals=ar_data.get('required_approvals', 1),
                )
                if ar_data.get('expires_at'):
                    try:
                        ar.expires_at = datetime.fromisoformat(ar_data['expires_at'])
                    except Exception:
                        pass
                if ar_data.get('resolved_at'):
                    try:
                        ar.resolved_at = datetime.fromisoformat(ar_data['resolved_at'])
                    except Exception:
                        pass
                db.session.add(ar)
                db.session.commit()
                results['approval_requests'] += 1
            except Exception as e:
                db.session.rollback()
                logger.warning(f"Approval request restore failed: {e}")

        # Restore ACME client orders (proxy + direct renewals)
        results.setdefault('acme_client_orders', 0)
        for o_data in backup_data.get('acme_client_orders', []):
            try:
                from models.acme_models import AcmeClientOrder
            except Exception:
                break
            try:
                order = AcmeClientOrder(
                    domains=o_data.get('domains', '[]'),
                    challenge_type=o_data.get('challenge_type', 'dns-01'),
                    environment=o_data.get('environment', 'staging'),
                    key_type=o_data.get('key_type', 'RSA-2048'),
                    status=o_data.get('status', 'pending'),
                    order_url=o_data.get('order_url'),
                    account_url=o_data.get('account_url'),
                    finalize_url=o_data.get('finalize_url'),
                    certificate_url=o_data.get('certificate_url'),
                    challenges_data=o_data.get('challenges_data'),
                    dns_provider_id=o_data.get('dns_provider_id'),
                    certificate_id=o_data.get('certificate_id'),
                    renewal_enabled=o_data.get('renewal_enabled', True),
                    is_proxy_order=o_data.get('is_proxy_order', False),
                    dns_records_created=o_data.get('dns_records_created'),
                    client_jwk_thumbprint=o_data.get('client_jwk_thumbprint'),
                    upstream_order_url=o_data.get('upstream_order_url'),
                    upstream_authz_urls=o_data.get('upstream_authz_urls'),
                    error_message=o_data.get('error_message'),
                )
                db.session.add(order)
                db.session.commit()
                results['acme_client_orders'] += 1
            except Exception as e:
                db.session.rollback()
                logger.warning(f"ACME client order restore failed: {e}")

        # Restore HTTPS server files
        https_data = backup_data.get('https_server', {})
        if https_data.get('cert_pem'):
            try:
                Config.HTTPS_CERT_PATH.parent.mkdir(parents=True, exist_ok=True)
                Config.HTTPS_CERT_PATH.write_text(https_data['cert_pem'])
                results['https_server'] += 1
            except Exception:
                pass
        if https_data.get('key_pem'):
            try:
                Config.HTTPS_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
                Config.HTTPS_KEY_PATH.write_text(https_data['key_pem'])
                Config.HTTPS_KEY_PATH.chmod(0o600)
                results['https_server'] += 1
            except Exception:
                pass
        
        db.session.commit()
        
        return results
    
    def _decrypt_private_key(self, encrypted_data: Dict[str, str], master_key: bytes) -> str:
        """Decrypt individual private key"""
        salt = bytes.fromhex(encrypted_data['salt'])
        nonce = bytes.fromhex(encrypted_data['nonce'])
        ciphertext = bytes.fromhex(encrypted_data['ciphertext'])
        
        # Derive key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=10000,
            backend=default_backend()
        )
        key = kdf.derive(master_key)
        
        # Decrypt
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        
        return plaintext.decode()
