"""
Core export methods mixin for BackupService
"""
import base64
import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from models import db, SystemConfig, User, CA, Certificate
from services.acme import profiles as acme_profiles
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

from .key_material import (
    as_pem, decrypt_stored_key, decrypt_stored_secret, key_matches_certificate,
)

logger = logging.getLogger(__name__)


class ExportCoreMixin:
    def _get_metadata(self, backup_type: str) -> Dict[str, Any]:
        """Generate backup metadata.

        The schema fields (version, dialect, sections, counts, exclusions) are
        added by _schema_metadata() once the payload is known.
        """
        return {
            'version': '1.0',
            'ucm_version': self.app_version,
            'database_type': self._database_dialect(),
            'created_at': utc_now().isoformat() + 'Z',
            'hostname': os.environ.get('FQDN', 'unknown'),
            'backup_type': backup_type,
        }

    def _export_configuration(self, include: bool) -> Dict[str, Any]:
        """Export system configuration"""
        if not include:
            return {}

        config = {}
        encrypted_keys = []

        # Get all system config entries
        system_configs = SystemConfig.query.all()
        for sc in system_configs:
            val = sc.value
            # A setting is secret either because the row says so or because
            # its value is ciphertext (the scheduled-backup password is stored
            # that way). Both used to leave the restored installation without
            # it: the first was skipped outright, the second travelled as
            # ciphertext bound to a database key the target does not have.
            from utils.encryption import is_encrypted
            from security.encryption import key_encryption
            if sc.encrypted or (isinstance(val, str) and (
                    is_encrypted(val) or key_encryption.is_string_encrypted(val))):
                val = decrypt_stored_secret(val, label=f"setting {sc.key}")
                encrypted_keys.append(sc.key)
            if isinstance(val, bytes):
                try:
                    val = val.decode('utf-8')
                except Exception:
                    import base64
                    val = base64.b64encode(val).decode('utf-8')

            # ACME profiles bind templates by numeric id, which the backup
            # cannot carry (templates export and restore by name): export
            # the binding with the template name, remapped after restore.
            if sc.key == acme_profiles.CONFIG_KEY:
                val = acme_profiles.export_config_json() or val

            config[sc.key] = val

        return {
            'system': {
                'fqdn': os.environ.get('FQDN', ''),
                'https_port': int(os.environ.get('HTTPS_PORT', 8443)),
                'session_timeout': int(os.environ.get('SESSION_TIMEOUT', 3600)),
                'jwt_expiration': int(os.environ.get('JWT_EXPIRATION', 86400))
            },
            'settings': config,
            # Which settings the target has to store encrypted again, with the
            # key of the installation restoring them.
            'encrypted_settings': encrypted_keys,
        }


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
                'serial_number': ca.serial_number,
                'ski': ca.ski,
                'offline': bool(ca.offline),
                'offline_reason': ca.offline_reason,
                'offline_mode': ca.offline_mode,
                # Revocation state (#343): without it a restore brings a
                # revoked CA back as active, answering good over OCSP and
                # free to sign again
                'revoked': bool(ca.revoked),
                'revoked_at': ca.revoked_at.isoformat() if ca.revoked_at else None,
                'revoke_reason': ca.revoke_reason,
                'invalidity_at': ca.invalidity_at.isoformat() if ca.invalidity_at else None,
                'certificate_pem': base64.b64decode(ca.crt).decode() if ca.crt else None,
                # A CA awaiting its external certificate keeps its request:
                # without it the restored CA can never be completed (#298)
                'csr_pem': ca.csr,
                'private_key_pem_encrypted': None  # Will be set in _encrypt_private_keys
            }

            # Decrypt at-rest encryption before export (backup uses its own
            # encryption). A key that cannot be decrypted aborts the backup:
            # archiving the stored ciphertext in its place produced an archive
            # whose restored CA could no longer sign anything.
            if ca.prv:
                label = f"CA {ca.refid}"
                ca_data['_private_key_plaintext'] = as_pem(
                    decrypt_stored_key(ca.prv, label=label), label=label
                )
                if not key_matches_certificate(
                        ca_data['_private_key_plaintext'],
                        ca_data.get('certificate_pem'), label=label):
                    ca_data['_key_mismatch'] = True

            cas.append(ca_data)

        return cas

    def _export_revoked_serials(self, include: bool) -> List[Dict[str, Any]]:
        """Export the persistent revocation records (#343).

        These outlive the certificate and the CA rows: they are what the CRL
        builder and the OCSP responder answer from once the revoked object
        is gone, and what keeps a re-imported CA revoked. A backup without
        them silently un-revokes everything they covered."""
        if not include:
            return []

        from models.revoked_serial import RevokedSerial
        return [
            {
                'caref': rs.caref,
                'serial_number': rs.serial_number,
                'revoked_at': rs.revoked_at.isoformat() if rs.revoked_at else None,
                'revoke_reason': rs.revoke_reason,
                'invalidity_at': rs.invalidity_at.isoformat() if rs.invalidity_at else None,
                'valid_to': rs.valid_to.isoformat() if rs.valid_to else None,
                'certificate_id': rs.certificate_id,
            }
            for rs in RevokedSerial.query.all()
        ]

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
                'invalidity_at': cert.invalidity_at.isoformat() if cert.invalidity_at else None,
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

            # Decrypt at-rest encryption before export (see _export_cas)
            if cert.prv:
                label = f"certificate {cert.refid}"
                cert_data['_private_key_plaintext'] = as_pem(
                    decrypt_stored_key(cert.prv, label=label), label=label
                )
                if not key_matches_certificate(
                        cert_data['_private_key_plaintext'],
                        cert_data.get('certificate_pem'), label=label):
                    cert_data['_key_mismatch'] = True

            certs.append(cert_data)

        return certs












