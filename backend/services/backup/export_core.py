"""
Core export methods mixin for BackupService
"""
import base64
import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from models import db, SystemConfig, User, CA, Certificate
from models.acme_models import AcmeAccount, AcmeEabCredential
from models.webauthn import WebAuthnCredential
from models.group import Group
from models.rbac import CustomRole
from models.certificate_template import CertificateTemplate
from models.truststore import TrustedCertificate
from models.sso import SSOProvider
from models.hsm import HsmProvider
from models.api_key import APIKey
from models.email_notification import SMTPConfig, NotificationConfig
from models.policy import CertificatePolicy
from config.settings import Config
from utils.datetime_utils import utc_now, utc_isoformat

logger = logging.getLogger(__name__)


class ExportCoreMixin:
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

