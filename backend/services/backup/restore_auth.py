"""
Authentication-related restore methods mixin for BackupService
"""
import logging
from typing import Dict, Any

from models import db

logger = logging.getLogger(__name__)


class RestoreAuthMixin:
    def _restore_sso_providers(self, backup_data: Dict, results: Dict) -> None:
        """Restore SSO providers from backup data"""
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

    def _restore_hsm_providers(self, backup_data: Dict, results: Dict) -> None:
        """Restore HSM providers from backup data"""
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

    def _restore_api_keys(self, backup_data: Dict, results: Dict) -> None:
        """Restore API keys from backup data"""
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

    def _restore_auth_certificates(self, backup_data: Dict, results: Dict) -> None:
        """Restore authentication certificates from backup data"""
        import base64
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
