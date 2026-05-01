"""
Core restore methods mixin for BackupService
"""
import json
import hashlib
import base64
import logging
from datetime import datetime
from typing import Dict, Any

from models import db, User, CA, Certificate
from models.acme_models import AcmeAccount
from config.settings import Config

logger = logging.getLogger(__name__)


class RestoreCoreMixin:
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
        
        # Initialize results
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
        
        # Core restores
        self._restore_users(backup_data, results)
        self._restore_cas(backup_data, results, master_key)
        self._restore_certificates(backup_data, results, master_key)
        self._restore_acme_accounts(backup_data, results)
        self._restore_acme_eab_credentials(backup_data, results)
        self._restore_settings(backup_data, results)
        
        # Commit after core entities
        db.session.commit()
        
        # Regenerate CA/cert files on disk
        self._regenerate_files()
        
        # RBAC restores
        self._restore_groups(backup_data, results)
        self._restore_custom_roles(backup_data, results)
        self._restore_templates(backup_data, results)
        self._restore_truststore(backup_data, results)
        
        # Auth restores
        self._restore_sso_providers(backup_data, results)
        self._restore_hsm_providers(backup_data, results)
        self._restore_api_keys(backup_data, results)
        self._restore_auth_certificates(backup_data, results)
        
        # Notification restores
        self._restore_smtp_config(backup_data, results)
        self._restore_notification_config(backup_data, results)
        
        # Policy restores
        self._restore_policies(backup_data, results)
        self._restore_dns_providers(backup_data, results)
        self._restore_acme_domains(backup_data, results)
        self._restore_acme_local_domains(backup_data, results)
        
        # Extended restores
        self._restore_ssh_cas(backup_data, results, master_key)
        self._restore_ssh_certificates(backup_data, results)
        self._restore_microsoft_cas(backup_data, results)
        self._restore_scan_profiles(backup_data, results)
        self._restore_hsm_keys(backup_data, results)
        self._restore_approval_requests(backup_data, results)
        self._restore_acme_client_orders(backup_data, results)
        self._restore_https_files(backup_data, results)
        
        db.session.commit()
        
        return results
    
    def _restore_users(self, backup_data: Dict, results: Dict) -> None:
        """Restore users from backup data"""
        from models import User
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
    
    def _restore_cas(self, backup_data: Dict, results: Dict, master_key: bytes) -> None:
        """Restore certificate authorities from backup data"""
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
    
    def _restore_certificates(self, backup_data: Dict, results: Dict, master_key: bytes) -> None:
        """Restore certificates from backup data"""
        from datetime import datetime as _dt
        
        def _parse_dt(val):
            if not val:
                return None
            try:
                return _dt.fromisoformat(val.replace('Z', '+00:00'))
            except Exception:
                return None
        
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
            
            if existing:
                existing.descr = cert_data.get('descr')
                existing.crt = base64.b64encode(cert_data['certificate_pem'].encode()).decode() if cert_data.get('certificate_pem') else None
                if prv_b64:
                    existing.prv = prv_b64
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
    
    def _restore_acme_accounts(self, backup_data: Dict, results: Dict) -> None:
        """Restore ACME accounts from backup data (RFC 8555)"""
        for acme_data in backup_data.get('acme_accounts', []):
            account_id = acme_data.get('account_id')
            jwk_thumbprint = acme_data.get('jwk_thumbprint')
            if not account_id or not jwk_thumbprint or not acme_data.get('jwk'):
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
    
    def _restore_acme_eab_credentials(self, backup_data: Dict, results: Dict) -> None:
        """Restore ACME EAB credentials from backup data (RFC 8555)"""
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
    
    def _restore_settings(self, backup_data: Dict, results: Dict) -> None:
        """Restore system settings from backup data"""
        from models import SystemConfig
        configuration = backup_data.get('configuration', {})
        # Handle legacy backups where configuration might be a list instead of dict
        if isinstance(configuration, list):
            config_data = {}
        else:
            config_data = configuration.get('settings', {})
        for key, value in config_data.items():
            existing = SystemConfig.query.filter_by(key=key).first()
            if existing:
                existing.value = value
            else:
                new_config = SystemConfig(key=key, value=value)
                db.session.add(new_config)
            results['settings'] += 1
    
    def _regenerate_files(self) -> None:
        """Regenerate CA and certificate files on disk"""
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
