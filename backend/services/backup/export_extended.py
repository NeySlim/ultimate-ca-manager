"""
Extended export methods mixin for BackupService
"""
import base64
import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from models import db, SCEPRequest, AuditLog
from models.auth_certificate import AuthCertificate
from models.acme_models import DnsProvider, AcmeDomain, AcmeLocalDomain, AcmeClientOrder
from models.ssh import SSHCertificateAuthority, SSHCertificate
from models.msca import MicrosoftCA, MSCARequest
from models.discovered_certificate import ScanProfile, ScanRun, DiscoveredCertificate
from models.policy import ApprovalRequest
from models.hsm import HsmKey
from config.settings import Config
from utils.datetime_utils import utc_now, utc_isoformat

logger = logging.getLogger(__name__)


class ExportExtendedMixin:
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
