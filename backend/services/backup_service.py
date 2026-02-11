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
from config.settings import Config


class BackupService:
    """Service for creating encrypted system backups"""
    
    # Constants
    PBKDF2_ITERATIONS = 100000
    KEY_SIZE = 32  # 256 bits for AES-256
    NONCE_SIZE = 12  # 96 bits for GCM
    SALT_SIZE = 32
    
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
            }
        
        # Build backup data structure
        backup_data = {
            'metadata': self._get_metadata(backup_type),
            'configuration': self._export_configuration(include.get('configuration', True)),
            'users': self._export_users(include.get('users', True)),
            'certificate_authorities': self._export_cas(include.get('cas', True)),
            'certificates': self._export_certificates(include.get('certificates', True)),
            'acme_accounts': self._export_acme_accounts(include.get('acme_accounts', True)),
            'groups': self._export_groups(include.get('groups', True)),
            'custom_roles': self._export_custom_roles(include.get('custom_roles', True)),
            'certificate_templates': self._export_templates(include.get('certificate_templates', True)),
            'trusted_certificates': self._export_truststore(include.get('trusted_certificates', True)),
            'sso_providers': self._export_sso_providers(include.get('sso_providers', True)),
            'hsm_providers': self._export_hsm_providers(include.get('hsm_providers', True)),
            'api_keys': self._export_api_keys(include.get('api_keys', True)),
            'smtp_config': self._export_smtp_config(include.get('smtp_config', True)),
            'notification_config': self._export_notification_config(include.get('notification_config', True)),
            'certificate_policies': self._export_policies(include.get('certificate_policies', True)),
            'auth_certificates': self._export_auth_certificates(include.get('auth_certificates', True)),
            'dns_providers': self._export_dns_providers(include.get('dns_providers', True)),
            'acme_domains': self._export_acme_domains(include.get('acme_domains', True)),
            'https_server': self._export_https_files(),
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
                except:
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
            # Handle potential bytes in private_key
            key_pem = account.private_key
            if isinstance(key_pem, bytes):
                key_pem = key_pem.decode('utf-8')
            
            accounts.append({
                'email': account.email,
                'account_url': account.account_url,
                'status': account.status,
                'key_pem': key_pem
            })
        
        return accounts
    
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
                'is_wildcard_allowed': ad.is_wildcard_allowed,
                'auto_approve': ad.auto_approve,
                'created_by': ad.created_by,
            })
        return domains

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
        
        return backup_data
    
    def restore_backup(self, backup_bytes: bytes, password: str) -> Dict[str, Any]:
        """
        Restore from encrypted backup
        
        Args:
            backup_bytes: Encrypted backup file content
            password: Decryption password
            
        Returns:
            Dict with restore results
        """
        # Extract salt from beginning
        if len(backup_bytes) < self.SALT_SIZE + self.NONCE_SIZE:
            raise ValueError("Invalid backup file: too small")
        
        master_salt = backup_bytes[:self.SALT_SIZE]
        encrypted_data = backup_bytes[self.SALT_SIZE:]
        
        # Derive key from password with saved salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=master_salt,
            iterations=self.PBKDF2_ITERATIONS,
            backend=default_backend()
        )
        master_key = kdf.derive(password.encode())
        
        # Decrypt backup
        try:
            nonce = encrypted_data[:self.NONCE_SIZE]
            ciphertext = encrypted_data[self.NONCE_SIZE:]
            
            aesgcm = AESGCM(master_key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as e:
            raise ValueError("Decryption failed - wrong password or corrupted file")
        
        # Parse JSON
        try:
            backup_data = json.loads(plaintext.decode())
        except json.JSONDecodeError:
            raise ValueError("Invalid backup format: not valid JSON")
        
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
                existing.prv = base64.b64encode(prv_pem.encode()).decode() if prv_pem else None
            else:
                new_ca = CA(
                    refid=ca_data['refid'],
                    descr=ca_data.get('descr'),
                    subject=ca_data.get('subject'),
                    issuer=ca_data.get('issuer'),
                    serial=ca_data.get('serial'),
                    caref=ca_data.get('caref'),
                    crt=base64.b64encode(ca_data['certificate_pem'].encode()).decode() if ca_data.get('certificate_pem') else None,
                    prv=base64.b64encode(prv_pem.encode()).decode() if prv_pem else None
                )
                db.session.add(new_ca)
            results['cas'] += 1
        
        # Restore Certificates
        for cert_data in backup_data.get('certificates', []):
            existing = Certificate.query.filter_by(refid=cert_data['refid']).first()
            
            # Decrypt private key if encrypted
            prv_pem = None
            if cert_data.get('private_key_pem_encrypted'):
                prv_pem = self._decrypt_private_key(
                    cert_data['private_key_pem_encrypted'],
                    master_key
                )
            
            if existing:
                existing.descr = cert_data.get('descr')
                existing.crt = base64.b64encode(cert_data['certificate_pem'].encode()).decode() if cert_data.get('certificate_pem') else None
                existing.prv = base64.b64encode(prv_pem.encode()).decode() if prv_pem else None
            else:
                new_cert = Certificate(
                    refid=cert_data['refid'],
                    descr=cert_data.get('descr'),
                    caref=cert_data.get('caref'),
                    cert_type=cert_data.get('cert_type'),
                    subject=cert_data.get('subject'),
                    issuer=cert_data.get('issuer'),
                    serial_number=cert_data.get('serial_number'),
                    crt=base64.b64encode(cert_data['certificate_pem'].encode()).decode() if cert_data.get('certificate_pem') else None,
                    prv=base64.b64encode(prv_pem.encode()).decode() if prv_pem else None
                )
                db.session.add(new_cert)
            results['certificates'] += 1
        
        # Restore ACME accounts
        for acme_data in backup_data.get('acme_accounts', []):
            existing = AcmeAccount.query.filter_by(email=acme_data['email']).first()
            if existing:
                existing.account_url = acme_data.get('account_url')
                existing.status = acme_data.get('status')
            else:
                new_acme = AcmeAccount(
                    email=acme_data['email'],
                    account_url=acme_data.get('account_url'),
                    status=acme_data.get('status', 'valid'),
                    private_key=acme_data.get('key_pem')
                )
                db.session.add(new_acme)
            results['acme_accounts'] += 1
        
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
                    prv_pem = base64.b64decode(ca.prv)
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
                    prv_pem_bytes = base64.b64decode(cert.prv)
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
                existing.created_by = ad_data.get('created_by')
            else:
                new_ad = AcmeDomain(
                    domain=ad_data['domain'],
                    dns_provider_id=ad_data.get('dns_provider_id', 1),
                    is_wildcard_allowed=ad_data.get('is_wildcard_allowed', True),
                    auto_approve=ad_data.get('auto_approve', True),
                    created_by=ad_data.get('created_by'),
                )
                db.session.add(new_ad)
            results['acme_domains'] += 1
        
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
