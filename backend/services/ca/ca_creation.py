"""
CA creation and import operations
"""
import base64
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.x509.oid import ExtensionOID
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from models import CA, db
from models.hsm import HsmKey
from services.audit_service import AuditService
from services.trust_store import TrustStoreService
from .helpers import save_ca_files

logger = logging.getLogger(__name__)


class CACreationMixin:
    """CA creation and import operations"""

    @staticmethod
    def create_internal_ca(
        descr: str,
        dn: Dict[str, str],
        key_type: str = '2048',
        validity_days: int = 825,
        digest: str = 'sha256',
        caref: Optional[str] = None,
        ocsp_uri: Optional[str] = None,
        username: str = 'system',
        path_length: Optional[int] = None,
        name_constraints_permitted: Optional[List[str]] = None,
        name_constraints_excluded: Optional[List[str]] = None,
        policy_constraints_require: Optional[int] = None,
        policy_constraints_inhibit: Optional[int] = None,
        inhibit_any_policy: Optional[int] = None,
        sia_urls: Optional[List[str]] = None,
        hsm_provider_id: Optional[int] = None,
        hsm_key_id: Optional[int] = None,
        hsm_key_label: Optional[str] = None,
        hsm_key_algorithm: Optional[str] = None,
    ) -> CA:
        """
        Create an internal Certificate Authority.

        Args:
            descr: Description
            dn: Distinguished Name components (CN, O, OU, C, ST, L, email)
            key_type: Key type (used only for local-key CAs)
            validity_days: Validity in days
            digest: Hash algorithm
            caref: Parent CA refid (for intermediate CA)
            ocsp_uri: Optional OCSP URI
            username: User creating the CA
            hsm_key_id: Bind CA to an existing HSM key
            hsm_provider_id: Generate a new HSM key on this provider
            hsm_key_label: Label for the new HSM key
            hsm_key_algorithm: Algorithm for the new HSM key

        Returns:
            CA model instance
        """
        from services.hsm import HsmService
        from services.hsm.hsm_private_key import load_hsm_private_key
        from services.hsm.ca_key_loader import get_ca_signing_key

        # Resolve signing key - local generation, existing HSM key, or new HSM key
        use_hsm = bool(hsm_key_id) or bool(hsm_provider_id)
        hsm_key = None

        if hsm_key_id and (hsm_provider_id or hsm_key_label or hsm_key_algorithm):
            raise ValueError(
                "Provide either hsm_key_id (existing key) OR "
                "hsm_provider_id+hsm_key_label+hsm_key_algorithm (generate new)"
            )

        if use_hsm:
            if hsm_key_id:
                hsm_key = HsmKey.query.get(hsm_key_id)
                if not hsm_key:
                    raise ValueError(f"HSM key {hsm_key_id} not found")
                if CA.query.filter_by(hsm_key_id=hsm_key.id).first():
                    raise ValueError(
                        f"HSM key {hsm_key.label} is already bound to another CA"
                    )
            else:
                if not (hsm_provider_id and hsm_key_label and hsm_key_algorithm):
                    raise ValueError(
                        "hsm_provider_id, hsm_key_label and hsm_key_algorithm "
                        "are all required to generate a new HSM key"
                    )
                hsm_key = HsmService.generate_key(
                    provider_id=hsm_provider_id,
                    label=hsm_key_label,
                    algorithm=hsm_key_algorithm,
                    purpose='signing',
                )

            private_key = load_hsm_private_key(hsm_key.id)
            key_pem = None  # HSM keys don't have on-disk PEM
        else:
            # Local key generation
            private_key = TrustStoreService.generate_private_key(key_type)
            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )

        # Build subject
        subject = TrustStoreService.build_subject(dn)

        # Get parent CA if intermediate
        issuer = None
        issuer_private_key = None
        parent_cdp_urls = None
        parent_ocsp_urls = None
        parent_cps_uri = None
        parent_cps_oid = None

        if caref:
            parent_ca = CA.query.filter_by(refid=caref).first()
            if not parent_ca:
                raise ValueError(f"Parent CA not found: {caref}")

            # Load parent CA certificate
            parent_cert_pem = base64.b64decode(parent_ca.crt)
            parent_cert = x509.load_pem_x509_certificate(
                parent_cert_pem, default_backend()
            )
            issuer = parent_cert.subject

            # Load parent CA signing key
            if not parent_ca.has_private_key:
                raise ValueError("Parent CA has no private key")
            issuer_private_key = get_ca_signing_key(parent_ca)

            # Increment parent CA serial
            parent_ca.serial = (parent_ca.serial or 0) + 1

            # Resolve parent CDP/OCSP URLs
            if parent_ca.cdp_enabled:
                parent_cdp_urls = [url.replace('{ca_refid}', parent_ca.refid or '')
                                  for url in parent_ca.get_cdp_urls()]
            if parent_ca.ocsp_enabled:
                parent_ocsp_urls = parent_ca.get_ocsp_urls()
            if parent_ca.cps_enabled and parent_ca.cps_uri:
                parent_cps_uri = parent_ca.cps_uri
                parent_cps_oid = parent_ca.cps_oid

        # Create CA certificate
        cert_pem, generated_key_pem = TrustStoreService.create_ca_certificate(
            subject=subject,
            private_key=private_key,
            issuer=issuer,
            issuer_private_key=issuer_private_key,
            validity_days=validity_days,
            digest=digest,
            ocsp_uris=parent_ocsp_urls,
            cdp_urls=parent_cdp_urls,
            cps_uri=parent_cps_uri,
            cps_oid=parent_cps_oid,
            path_length=path_length,
            name_constraints_permitted=name_constraints_permitted,
            name_constraints_excluded=name_constraints_excluded,
            policy_constraints_require=policy_constraints_require,
            policy_constraints_inhibit=policy_constraints_inhibit,
            inhibit_any_policy=inhibit_any_policy,
            sia_urls=sia_urls,
        )

        # If using local key, use the generated key PEM
        if not use_hsm and generated_key_pem:
            key_pem = generated_key_pem

        # Parse certificate for details
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

        # Encrypt private key if encryption is enabled (local keys only)
        prv_encoded = None
        if key_pem is not None:
            prv_encoded = base64.b64encode(key_pem).decode('utf-8')
            try:
                from security.encryption import key_encryption
                if key_encryption.is_enabled:
                    prv_encoded = key_encryption.encrypt(prv_encoded)
            except ImportError:
                pass

        # Extract SKI from generated cert
        ca_ski = None
        try:
            ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
            ca_ski = ext.value.key_identifier.hex(':').upper()
        except Exception:
            pass

        # Create CA record
        ca = CA(
            refid=str(uuid.uuid4()),
            descr=descr,
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=prv_encoded,
            serial=0,
            caref=caref,
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            ski=ca_ski,
            valid_from=cert.not_valid_before_utc,
            valid_to=cert.not_valid_after_utc,
            imported_from='generated',
            created_by=username,
            path_length=path_length,
            policy_constraints_require=policy_constraints_require,
            policy_constraints_inhibit=policy_constraints_inhibit,
            inhibit_any_policy=inhibit_any_policy,
            hsm_key_id=hsm_key.id if hsm_key else None,
        )

        # Store JSON-serialized constraints
        if name_constraints_permitted:
            ca.set_name_constraints_permitted(name_constraints_permitted)
        if name_constraints_excluded:
            ca.set_name_constraints_excluded(name_constraints_excluded)
        if sia_urls:
            ca.sia_enabled = True
            ca.set_sia_urls(sia_urls)

        db.session.add(ca)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to persist CA: {e}")
            raise

        # Auto-enable CDP if protocol base URL is configured
        try:
            from utils.protocol_url import get_protocol_base_url
            base_url = get_protocol_base_url()
            if base_url:
                ca.cdp_enabled = True
                ca.set_cdp_urls([f"{base_url}/cdp/{ca.refid}.crl"])
                db.session.commit()
        except Exception:
            pass

        # Audit log
        hsm_note = f' (HSM key: {hsm_key.label})' if hsm_key else ''
        AuditService.log_ca('ca_created', ca, f'Created CA: {descr}{hsm_note}')

        # Save certificate to file
        save_ca_files(ca, cert_pem, key_pem)

        return ca

    @staticmethod
    def import_ca(
        descr: str,
        cert_pem: str,
        key_pem: Optional[str] = None,
        username: str = 'system'
    ) -> CA:
        """
        Import an existing CA certificate.

        Args:
            descr: Description
            cert_pem: Certificate in PEM format
            key_pem: Optional private key in PEM format
            username: User importing

        Returns:
            CA model instance
        """
        # Parse certificate
        cert = x509.load_pem_x509_certificate(
            cert_pem.encode() if isinstance(cert_pem, str) else cert_pem,
            default_backend()
        )

        # Validate it's a CA certificate
        try:
            bc = cert.extensions.get_extension_for_oid(
                x509.oid.ExtensionOID.BASIC_CONSTRAINTS
            )
            if not bc.value.ca:
                raise ValueError("Certificate is not a CA certificate")
        except x509.ExtensionNotFound:
            raise ValueError("Certificate has no BasicConstraints extension")

        # Create CA record
        ca = CA(
            refid=str(uuid.uuid4()),
            descr=descr,
            crt=base64.b64encode(cert_pem.encode() if isinstance(cert_pem, str) else cert_pem).decode('utf-8'),
            prv=base64.b64encode(key_pem.encode()).decode('utf-8') if key_pem else None,
            serial=0,
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            valid_from=cert.not_valid_before_utc,
            valid_to=cert.not_valid_after_utc,
            imported_from='manual',
            created_by=username
        )

        db.session.add(ca)
        db.session.commit()

        # Audit log
        AuditService.log_ca('ca_imported', ca, f'Imported CA: {descr}')

        # Save files
        cert_path_bytes = cert_pem.encode() if isinstance(cert_pem, str) else cert_pem
        key_path_bytes = key_pem.encode() if key_pem else None
        save_ca_files(ca, cert_path_bytes, key_path_bytes)

        return ca
