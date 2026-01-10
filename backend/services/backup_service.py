"""
Backup Service for UCM
Handles creation of encrypted, portable backup archives
"""
import os
import json
import hashlib
import secrets
import base64
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

from models import db, User, CA, Certificate, SystemConfig
from models.acme_models import AcmeAccount
from models.webauthn import WebAuthnCredential


class BackupService:
    """Service for creating encrypted system backups"""
    
    # Constants
    PBKDF2_ITERATIONS = 100000
    KEY_SIZE = 32  # 256 bits for AES-256
    NONCE_SIZE = 12  # 96 bits for GCM
    SALT_SIZE = 32
    
    def __init__(self):
        self.app_version = os.environ.get('APP_VERSION', '1.9.0')
    
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
                'email_password': False
            }
        
        # Build backup data structure
        backup_data = {
            'metadata': self._get_metadata(backup_type),
            'configuration': self._export_configuration(include.get('configuration', True)),
            'users': self._export_users(include.get('users', True)),
            'certificate_authorities': self._export_cas(include.get('cas', True)),
            'certificates': self._export_certificates(include.get('certificates', True)),
            'acme_accounts': self._export_acme_accounts(include.get('acme_accounts', True))
        }
        
        # Derive master key from password
        master_key, master_salt = self._derive_master_key(password)
        
        # Encrypt private keys individually
        backup_data = self._encrypt_private_keys(backup_data, master_key)
        
        # Calculate checksum of plaintext
        json_str = json.dumps(backup_data, indent=2, sort_keys=True)
        checksum = hashlib.sha256(json_str.encode()).hexdigest()
        backup_data['checksum'] = {
            'algorithm': 'SHA256',
            'value': checksum
        }
        
        # Re-serialize with checksum
        final_json = json.dumps(backup_data, indent=2, sort_keys=True)
        
        # Encrypt entire backup
        encrypted = self._encrypt_backup(final_json.encode(), master_key)
        
        # Prepend salt for decryption
        return master_salt + encrypted
    
    def _validate_password(self, password: str):
        """Validate backup password strength"""
        if len(password) < 12:
            raise ValueError("Backup password must be at least 12 characters")
        
        # Check entropy (basic)
        unique_chars = len(set(password))
        if unique_chars < 8:
            raise ValueError("Backup password is too simple")
    
    def _derive_master_key(self, password: str) -> tuple:
        """Derive encryption key from password using PBKDF2"""
        salt = secrets.token_bytes(self.SALT_SIZE)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
            backend=default_backend()
        )
        
        key = kdf.derive(password.encode())
        return key, salt
    
    def _encrypt_backup(self, data: bytes, key: bytes) -> bytes:
        """Encrypt backup data with AES-256-GCM"""
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        
        # Return nonce + ciphertext
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
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'hostname': os.environ.get('FQDN', 'unknown'),
            'backup_type': backup_type,
            'format_version': '1.0'
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
            config[sc.key] = sc.value
        
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
            
            user_data['webauthn_credentials'] = [
                {
                    'credential_id': cred.credential_id,
                    'public_key': cred.public_key,
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
                'ocsp_enabled': ca.ocsp_enabled,
                'ocsp_url': ca.ocsp_url,
                'imported_from': ca.imported_from,
                'certificate_pem': base64.b64decode(ca.crt).decode() if ca.crt else None,
                'private_key_pem_encrypted': None  # Will be set in _encrypt_private_keys
            }
            
            # Store unencrypted key temporarily (will be encrypted later)
            if ca.prv:
                try:
                    ca_data['_private_key_plaintext'] = base64.b64decode(ca.prv).decode()
                except:
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
                'san_dns': cert.san_dns,
                'san_ip': cert.san_ip,
                'san_email': cert.san_email,
                'san_uri': cert.san_uri,
                'ocsp_uri': cert.ocsp_uri,
                'private_key_location': cert.private_key_location,
                'certificate_pem': base64.b64decode(cert.crt).decode() if cert.crt else None,
                'csr_pem': base64.b64decode(cert.csr).decode() if cert.csr else None,
                'private_key_pem_encrypted': None  # Will be set in _encrypt_private_keys
            }
            
            # Store unencrypted key temporarily
            if cert.prv:
                try:
                    cert_data['_private_key_plaintext'] = base64.b64decode(cert.prv).decode()
                except:
                    cert_data['_private_key_plaintext'] = cert.prv
            
            certs.append(cert_data)
        
        return certs
    
    def _export_acme_accounts(self, include: bool) -> List[Dict[str, Any]]:
        """Export ACME accounts"""
        if not include:
            return []
        
        accounts = []
        for account in AcmeAccount.query.all():
            accounts.append({
                'email': account.email,
                'account_url': account.account_url,
                'status': account.status,
                'key_pem': account.private_key
            })
        
        return accounts
    
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
        
        return backup_data
