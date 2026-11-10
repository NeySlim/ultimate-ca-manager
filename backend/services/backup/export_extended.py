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

from .errors import BackupExportError
from .key_material import (
    decrypt_stored_key, decrypt_stored_secret, ensure_key_material,
)

logger = logging.getLogger(__name__)


class ExportExtendedMixin:




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
                'allow_any_principal': bool(getattr(ca, 'allow_any_principal', False)),
                'comment': getattr(ca, 'comment', None),
                'created_at': ca.created_at.isoformat() if getattr(ca, 'created_at', None) else None,
                'created_by': getattr(ca, 'created_by', None),
                'owner_group_id': getattr(ca, 'owner_group_id', None),
            }
            # Private key: re-encrypt with master key in _encrypt_section_keys
            # pass. SSH CAs store base64 of the OpenSSH PEM, and the restore
            # puts that same encoding back, so the archive keeps it as stored —
            # but a key that cannot be decrypted aborts the backup rather than
            # travelling as its at-rest ciphertext.
            prv = getattr(ca, 'private_key', None)
            if prv:
                label = f"SSH CA {getattr(ca, 'refid', None)}"
                ca_data['_private_key_plaintext'] = ensure_key_material(
                    decrypt_stored_key(prv, label=label), label=label
                )
            cas.append(ca_data)
        return cas












    def _export_https_files(self) -> Dict[str, Any]:
        """Export HTTPS server certificate and key files.

        A file that is not there means HTTPS is not configured from these
        paths, which is a normal shape of the archive. A file that is there
        and cannot be read is not: it used to be swallowed, and the backup
        that could not read the server key was still announced as complete.
        """
        result = {}
        for key, path in (('cert_pem', Config.HTTPS_CERT_PATH),
                          ('key_pem', Config.HTTPS_KEY_PATH)):
            try:
                if not path.exists():
                    continue
                result[key] = path.read_text()
            except OSError as exc:
                raise BackupExportError(
                    f"The HTTPS server {'certificate' if key == 'cert_pem' else 'key'} "
                    "exists but could not be read"
                ) from exc
        return result
