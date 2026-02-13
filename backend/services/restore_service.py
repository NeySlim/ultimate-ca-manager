"""
Restore Service for UCM
Handles decryption and restoration of backup archives
"""
import os
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

from models import db, User, CA, Certificate, SystemConfig
from models.acme_models import AcmeAccount
from models.webauthn import WebAuthnCredential
from config.settings import Config


class RestoreService:
    """Service for restoring encrypted system backups"""
    
    # Constants (must match BackupService)
    PBKDF2_ITERATIONS = 100000
    KEY_SIZE = 32
    NONCE_SIZE = 12
    SALT_SIZE = 32
    
    def __init__(self):
        self.current_version = Config.APP_VERSION
    
    def restore_backup(
        self,
        encrypted_data: bytes,
        password: str,
        options: Optional[Dict[str, bool]] = None
    ) -> Dict[str, Any]:
        """
        Restore from encrypted backup
        
        Args:
            encrypted_data: Encrypted backup file content
            password: Decryption password
            options: What to restore (cas, certificates, users, etc.)
            
        Returns:
            Dict with restore statistics
        """
        # Default options
        if options is None:
            options = {
                'restore_cas': True,
                'restore_certificates': True,
                'restore_users': True,
                'merge_users': False,
                'restore_configuration': True,
                'restore_acme_accounts': True
            }
        
        # Extract salt and encrypted data
        if len(encrypted_data) < self.SALT_SIZE:
            raise ValueError("Invalid backup file: too small")
        
        master_salt = encrypted_data[:self.SALT_SIZE]
        encrypted_backup = encrypted_data[self.SALT_SIZE:]
        
        # Derive master key
        master_key = self._derive_master_key(password, master_salt)
        
        # Decrypt backup
        try:
            json_data = self._decrypt_backup(encrypted_backup, master_key)
        except Exception as e:
            raise ValueError(f"Decryption failed: wrong password or corrupted file")
        
        # Parse JSON
        try:
            backup_data = json.loads(json_data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid backup format: {e}")
        
        # Validate backup structure
        self._validate_backup(backup_data)
        
        # Verify checksum
        self._verify_checksum(backup_data)
        
        # Check version compatibility
        self._check_version_compatibility(backup_data['metadata'])
        
        # Perform restoration in transaction
        stats = {
            'cas': 0,
            'certificates': 0,
            'users': 0,
            'acme_accounts': 0
        }
        
        with db.session.begin_nested():
            try:
                # Restore in order: CAs first, then certs (FK constraint)
                if options.get('restore_cas'):
                    stats['cas'] = self._restore_cas(
                        backup_data.get('certificate_authorities', []),
                        master_key
                    )
                
                if options.get('restore_certificates'):
                    stats['certificates'] = self._restore_certificates(
                        backup_data.get('certificates', []),
                        master_key
                    )
                
                if options.get('restore_users'):
                    stats['users'] = self._restore_users(
                        backup_data.get('users', []),
                        merge=options.get('merge_users', False)
                    )
                
                if options.get('restore_configuration'):
                    self._restore_configuration(backup_data.get('configuration', {}))
                
                if options.get('restore_acme_accounts'):
                    stats['acme_accounts'] = self._restore_acme_accounts(
                        backup_data.get('acme_accounts', [])
                    )
                
                db.session.commit()
                
            except Exception as e:
                db.session.rollback()
                raise Exception(f"Restore failed: {e}")
        
        # Signal service restart needed
        self._signal_restart()
        
        return stats
    
    def validate_backup(
        self,
        encrypted_data: bytes,
        password: str
    ) -> Dict[str, Any]:
        """
        Validate backup without restoring
        
        Returns metadata and contents summary
        """
        # Extract salt
        master_salt = encrypted_data[:self.SALT_SIZE]
        encrypted_backup = encrypted_data[self.SALT_SIZE:]
        
        # Derive key and decrypt
        master_key = self._derive_master_key(password, master_salt)
        
        try:
            json_data = self._decrypt_backup(encrypted_backup, master_key)
            backup_data = json.loads(json_data)
        except:
            return {
                'valid': False,
                'error': 'Invalid password or corrupted file'
            }
        
        # Extract info
        return {
            'valid': True,
            'metadata': backup_data.get('metadata', {}),
            'contents': {
                'cas': len(backup_data.get('certificate_authorities', [])),
                'certificates': len(backup_data.get('certificates', [])),
                'users': len(backup_data.get('users', [])),
                'acme_accounts': len(backup_data.get('acme_accounts', []))
            }
        }
    
    def _derive_master_key(self, password: str, salt: bytes) -> bytes:
        """Derive master key from password and salt"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
            backend=default_backend()
        )
        return kdf.derive(password.encode())
    
    def _decrypt_backup(self, encrypted_data: bytes, key: bytes) -> bytes:
        """Decrypt backup with AES-256-GCM"""
        if len(encrypted_data) < self.NONCE_SIZE:
            raise ValueError("Invalid encrypted data")
        
        nonce = encrypted_data[:self.NONCE_SIZE]
        ciphertext = encrypted_data[self.NONCE_SIZE:]
        
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)
    
    def _decrypt_private_key(
        self,
        encrypted_key: Dict[str, str],
        master_key: bytes
    ) -> str:
        """Decrypt individual private key"""
        salt = bytes.fromhex(encrypted_key['salt'])
        nonce = bytes.fromhex(encrypted_key['nonce'])
        ciphertext = bytes.fromhex(encrypted_key['ciphertext'])
        
        # Derive key-specific key
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
        return aesgcm.decrypt(nonce, ciphertext, None).decode()
    
    def _validate_backup(self, backup_data: Dict):
        """Validate backup structure"""
        required_keys = ['metadata', 'checksum']
        for key in required_keys:
            if key not in backup_data:
                raise ValueError(f"Invalid backup: missing {key}")
        
        metadata = backup_data['metadata']
        if 'version' not in metadata or 'ucm_version' not in metadata:
            raise ValueError("Invalid backup metadata")
    
    def _verify_checksum(self, backup_data: Dict):
        """Verify backup integrity"""
        if 'checksum' not in backup_data:
            raise ValueError("No checksum in backup")
        
        stored_checksum = backup_data['checksum']['value']
        
        # Remove checksum for recalculation
        checksum_data = backup_data.pop('checksum')
        
        # Recalculate
        json_str = json.dumps(backup_data, indent=2, sort_keys=True)
        calculated = hashlib.sha256(json_str.encode()).hexdigest()
        
        # Restore checksum
        backup_data['checksum'] = checksum_data
        
        if calculated != stored_checksum:
            raise ValueError("Backup integrity check failed: checksum mismatch")
    
    def _check_version_compatibility(self, metadata: Dict):
        """Check if backup version is compatible"""
        backup_version = metadata.get('ucm_version', '0.0.0')
        
        # Parse versions
        backup_major = int(backup_version.split('.')[0])
        current_major = int(self.current_version.split('.')[0])
        
        # For now, same major version required
        if backup_major != current_major:
            raise ValueError(
                f"Incompatible version: backup v{backup_version}, "
                f"current v{self.current_version}"
            )
    
    def _restore_cas(
        self,
        cas_data: List[Dict],
        master_key: bytes
    ) -> int:
        """Restore Certificate Authorities"""
        count = 0
        
        for ca_data in cas_data:
            # Check if CA already exists
            existing = CA.query.filter_by(refid=ca_data['refid']).first()
            if existing:
                continue  # Skip existing
            
            # Decrypt private key
            private_key = None
            if ca_data.get('private_key_pem_encrypted'):
                private_key = self._decrypt_private_key(
                    ca_data['private_key_pem_encrypted'],
                    master_key
                )
            
            # Re-encrypt if at-rest encryption is active
            if private_key:
                try:
                    from security.encryption import key_encryption
                    if key_encryption.is_enabled:
                        import base64
                        prv_b64 = base64.b64encode(private_key.encode()).decode()
                        prv_b64 = key_encryption.encrypt(prv_b64)
                        private_key = base64.b64decode(prv_b64).decode()
                except Exception:
                    pass
            
            # Create CA
            ca = CA(
                refid=ca_data['refid'],
                name=ca_data['name'],
                ca_type=ca_data['type'],
                subject_cn=ca_data['subject']['CN'],
                subject_o=ca_data['subject'].get('O'),
                subject_ou=ca_data['subject'].get('OU'),
                subject_c=ca_data['subject'].get('C'),
                subject_st=ca_data['subject'].get('ST'),
                subject_l=ca_data['subject'].get('L'),
                key_type=ca_data['key_type'],
                key_size=ca_data['key_size'],
                serial=ca_data['serial'],
                certificate=ca_data['certificate_pem'],
                private_key=private_key,
                crl_enabled=ca_data.get('crl_enabled', False),
                crl_validity_days=ca_data.get('crl_validity_days', 30),
                ocsp_enabled=ca_data.get('ocsp_enabled', False)
            )
            
            # Parse dates
            if ca_data.get('valid_from'):
                ca.valid_from = datetime.fromisoformat(ca_data['valid_from'])
            if ca_data.get('valid_to'):
                ca.valid_to = datetime.fromisoformat(ca_data['valid_to'])
            
            db.session.add(ca)
            count += 1
        
        return count
    
    def _restore_certificates(
        self,
        certs_data: List[Dict],
        master_key: bytes
    ) -> int:
        """Restore certificates"""
        count = 0
        
        for cert_data in certs_data:
            # Check if exists
            existing = Certificate.query.filter_by(refid=cert_data['refid']).first()
            if existing:
                continue
            
            # Get CA
            ca = CA.query.filter_by(refid=cert_data['ca_refid']).first()
            if not ca:
                continue  # Skip if CA not found
            
            # Decrypt private key
            private_key = None
            if cert_data.get('private_key_pem_encrypted'):
                private_key = self._decrypt_private_key(
                    cert_data['private_key_pem_encrypted'],
                    master_key
                )
            
            # Re-encrypt if at-rest encryption is active
            if private_key:
                try:
                    from security.encryption import key_encryption
                    if key_encryption.is_enabled:
                        import base64
                        prv_b64 = base64.b64encode(private_key.encode()).decode()
                        prv_b64 = key_encryption.encrypt(prv_b64)
                        private_key = base64.b64decode(prv_b64).decode()
                except Exception:
                    pass
            
            # Create certificate
            cert = Certificate(
                refid=cert_data['refid'],
                ca_id=ca.id,
                cert_type=cert_data['cert_type'],
                subject_cn=cert_data['subject']['CN'],
                subject_o=cert_data['subject'].get('O'),
                subject_ou=cert_data['subject'].get('OU'),
                subject_c=cert_data['subject'].get('C'),
                san_dns=','.join(cert_data.get('san_dns', [])),
                san_ip=','.join(cert_data.get('san_ip', [])),
                serial=cert_data['serial'],
                certificate=cert_data['certificate_pem'],
                private_key=private_key,
                revoked=cert_data.get('revoked', False),
                revocation_reason=cert_data.get('revocation_reason')
            )
            
            # Parse dates
            if cert_data.get('valid_from'):
                cert.valid_from = datetime.fromisoformat(cert_data['valid_from'])
            if cert_data.get('valid_to'):
                cert.valid_to = datetime.fromisoformat(cert_data['valid_to'])
            if cert_data.get('revocation_date'):
                cert.revocation_date = datetime.fromisoformat(cert_data['revocation_date'])
            
            db.session.add(cert)
            count += 1
        
        return count
    
    def _restore_users(
        self,
        users_data: List[Dict],
        merge: bool = False
    ) -> int:
        """Restore users"""
        count = 0
        
        for user_data in users_data:
            existing = User.query.filter_by(username=user_data['username']).first()
            
            if existing:
                if not merge:
                    continue  # Skip existing
                # Update existing
                user = existing
            else:
                user = User(username=user_data['username'])
            
            # Update fields
            user.email = user_data['email']
            user.full_name = user_data.get('full_name')
            user.role = user_data['role']
            user.active = user_data.get('active', True)
            user.mfa_enabled = user_data.get('mfa_enabled', False)
            user.password_hash = user_data['password_hash']
            
            if not existing:
                db.session.add(user)
            
            count += 1
            
            # Restore WebAuthn credentials
            for cred_data in user_data.get('webauthn_credentials', []):
                existing_cred = WebAuthnCredential.query.filter_by(
                    user_id=user.id,
                    credential_id=cred_data['credential_id']
                ).first()
                
                if not existing_cred:
                    cred = WebAuthnCredential(
                        user_id=user.id,
                        credential_id=cred_data['credential_id'],
                        public_key=cred_data['public_key'],
                        sign_count=cred_data['sign_count'],
                        name=cred_data.get('name'),
                        aaguid=cred_data.get('aaguid'),
                        enabled=True
                    )
                    db.session.add(cred)
        
        return count
    
    def _restore_configuration(self, config_data: Dict):
        """Restore system configuration"""
        if not config_data:
            return
        
        settings = config_data.get('settings', {})
        for key, value in settings.items():
            existing = SystemConfig.query.filter_by(key=key).first()
            if existing:
                existing.value = value
            else:
                config = SystemConfig(key=key, value=value)
                db.session.add(config)
    
    def _restore_acme_accounts(self, accounts_data: List[Dict]) -> int:
        """Restore ACME accounts"""
        count = 0
        
        for account_data in accounts_data:
            existing = AcmeAccount.query.filter_by(
                email=account_data['email']
            ).first()
            
            if existing:
                continue
            
            account = AcmeAccount(
                email=account_data['email'],
                account_url=account_data['account_url'],
                status=account_data['status'],
                private_key=account_data['key_pem']
            )
            db.session.add(account)
            count += 1
        
        return count
    
    def _signal_restart(self):
        """Signal that service restart is needed"""
        restart_file = Path('/opt/ucm/backend/data/.restart_requested')
        restart_file.parent.mkdir(parents=True, exist_ok=True)
        restart_file.touch()
