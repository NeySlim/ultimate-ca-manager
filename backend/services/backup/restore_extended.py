"""
Extended restore methods mixin for BackupService
"""
import uuid
import base64
import logging
from datetime import datetime
from typing import Dict, Any

from models import db
from config.settings import Config
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class RestoreExtendedMixin:
    def _restore_ssh_cas(self, backup_data: Dict, results: Dict, master_key: bytes) -> None:
        """Restore SSH certificate authorities from backup data"""
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

    def _restore_ssh_certificates(self, backup_data: Dict, results: Dict) -> None:
        """Restore SSH certificates from backup data"""
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

    def _restore_microsoft_cas(self, backup_data: Dict, results: Dict) -> None:
        """Restore Microsoft certificate authorities from backup data"""
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

    def _restore_scan_profiles(self, backup_data: Dict, results: Dict) -> None:
        """Restore scan profiles from backup data"""
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

    def _restore_hsm_keys(self, backup_data: Dict, results: Dict) -> None:
        """Restore HSM keys from backup data"""
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

    def _restore_approval_requests(self, backup_data: Dict, results: Dict) -> None:
        """Restore approval requests from backup data"""
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

    def _restore_acme_client_orders(self, backup_data: Dict, results: Dict) -> None:
        """Restore ACME client orders from backup data"""
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

    def _restore_https_files(self, backup_data: Dict, results: Dict) -> None:
        """Restore HTTPS server files from backup data"""
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
