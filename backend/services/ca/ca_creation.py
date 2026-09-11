"""
CA creation and import operations
"""
import base64
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.x509.oid import ExtensionOID
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from models import CA, db
from models.hsm import HsmKey
from services.audit_service import AuditService
from services.trust_store import TrustStoreService
from utils.datetime_utils import to_naive_utc, utc_isoformat, utc_now
from utils.serial_format import serial_to_int
from .helpers import save_ca_files, save_ca_key_file

logger = logging.getLogger(__name__)


class CACreationMixin:
    """CA creation and import operations"""

    @staticmethod
    def _resolve_signing_key(
        key_type: str,
        hsm_provider_id: Optional[int],
        hsm_key_id: Optional[int],
        hsm_key_label: Optional[str],
        hsm_key_algorithm: Optional[str],
    ):
        """Resolve the CA signing key: local generation, existing HSM key, or
        new HSM key.

        Returns (private_key, key_pem_bytes_or_None, hsm_key_or_None).
        key_pem is None for HSM-backed keys (no on-disk PEM).
        """
        from services.hsm import HsmService
        from services.hsm.hsm_private_key import load_hsm_private_key

        if hsm_key_id and (hsm_provider_id or hsm_key_label or hsm_key_algorithm):
            raise ValueError(
                "Provide either hsm_key_id (existing key) OR "
                "hsm_provider_id+hsm_key_label+hsm_key_algorithm (generate new)"
            )

        use_hsm = bool(hsm_key_id) or bool(hsm_provider_id)
        if not use_hsm:
            private_key = TrustStoreService.generate_private_key(key_type)
            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            return private_key, key_pem, None

        if hsm_key_id:
            # Lock the HSM key row to serialise concurrent CA creations
            # binding the same key. The DB also enforces uq_ca_hsm_key_id
            # (migration 032) as a defense-in-depth safety net.
            try:
                hsm_key = (
                    HsmKey.query.filter_by(id=hsm_key_id)
                    .with_for_update()
                    .one_or_none()
                )
            except Exception:
                # SQLite has no row-level locks; fall back to plain lookup.
                hsm_key = db.session.get(HsmKey, hsm_key_id)
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

        return load_hsm_private_key(hsm_key.id), None, hsm_key

    @staticmethod
    def _encode_private_key(key_pem: Optional[bytes]) -> Optional[str]:
        """Base64-encode a PEM key and encrypt it at rest when enabled."""
        if key_pem is None:
            return None
        prv_encoded = base64.b64encode(key_pem).decode('utf-8')
        try:
            from security.encryption import key_encryption
            if key_encryption.is_enabled:
                prv_encoded = key_encryption.encrypt(prv_encoded)
        except ImportError:
            pass
        return prv_encoded

    @staticmethod
    def _unique_url_slug(descr):
        """Unique, immutable slug for named protocol URLs (#207).

        '-delta' suffixes are reserved by the delta CRL route — pad them so
        /cdp/<slug>-delta.crl stays unambiguous.
        """
        from utils.sanitize import ca_url_slug
        base = ca_url_slug(descr)
        if not base:
            return None
        if base.endswith('-delta'):
            base += '-ca'
        slug = base
        i = 2
        while CA.query.filter_by(url_slug=slug).first() is not None:
            slug = f"{base}-{i}"
            i += 1
        return slug

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
        name_constraints_permitted: Optional[List[dict]] = None,
        name_constraints_excluded: Optional[List[dict]] = None,
        policy_constraints_require: Optional[int] = None,
        policy_constraints_inhibit: Optional[int] = None,
        inhibit_any_policy: Optional[int] = None,
        sia_urls: Optional[List[str]] = None,
        hsm_provider_id: Optional[int] = None,
        hsm_key_id: Optional[int] = None,
        hsm_key_label: Optional[str] = None,
        hsm_key_algorithm: Optional[str] = None,
        key_usage: Optional[List[str]] = None,
        extended_key_usage: Optional[List[str]] = None,
        named_urls: bool = False,
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
        from services.hsm.ca_key_loader import get_ca_signing_key

        # Resolve signing key - local generation, existing HSM key, or new HSM key
        private_key, key_pem, hsm_key = CACreationMixin._resolve_signing_key(
            key_type, hsm_provider_id, hsm_key_id, hsm_key_label, hsm_key_algorithm
        )
        use_hsm = hsm_key is not None

        # Build subject
        subject = TrustStoreService.build_subject(dn)

        # Get parent CA if intermediate
        issuer = None
        issuer_private_key = None
        parent_cert = None
        parent_cdp_urls = None
        parent_ocsp_urls = None
        parent_aia_urls = None
        parent_cps_uri = None
        parent_cps_oid = None
        parent_not_after = None

        if caref:
            parent_ca = CA.query.filter_by(refid=caref).first()
            if not parent_ca:
                raise ValueError(f"Parent CA not found: {caref}")
            if not parent_ca.crt:
                raise ValueError("Parent CA is awaiting its certificate")

            # Load parent CA certificate
            parent_cert_pem = base64.b64decode(parent_ca.crt)
            parent_cert = x509.load_pem_x509_certificate(
                parent_cert_pem, default_backend()
            )
            issuer = parent_cert.subject
            # The parent can only vouch inside its own validity window
            from utils.ca_signing_window import check_issuer_window
            check_issuer_window(parent_cert)
            parent_not_after = to_naive_utc(parent_cert.not_valid_after_utc)

            # Clamp the requested pathLenConstraint to what the parent permits
            # (RFC 5280 §4.2.1.9) before the certificate is built AND before
            # the CA row is stored, so the two can never disagree. A pathLen-0
            # parent refuses outright — the same rule (and error string) the
            # sign-CSR sub-CA path enforces; without this, POST /api/v2/cas
            # minted a child asserting any pathLen under any parent.
            from services.trust_store.csr_operations_mixin import capped_path_length
            path_length = capped_path_length(path_length, parent_cert)

            # Load parent CA signing key
            if not parent_ca.has_private_key:
                raise ValueError("Parent CA has no private key")
            issuer_private_key = get_ca_signing_key(parent_ca)

            # Increment parent CA serial
            parent_ca.serial = (parent_ca.serial or 0) + 1

            # Resolve parent CDP/OCSP/AIA URLs
            if parent_ca.cdp_enabled:
                parent_cdp_urls = [url.replace('{ca_refid}', parent_ca.url_ref)
                                  for url in parent_ca.get_cdp_urls()]
            if parent_ca.ocsp_enabled:
                parent_ocsp_urls = parent_ca.get_ocsp_urls()
            if parent_ca.aia_ca_issuers_enabled:
                parent_aia_urls = [
                    url.replace('{ca_refid}', parent_ca.url_ref)
                    for url in parent_ca.get_aia_urls()
                ]
            if parent_ca.cps_enabled and parent_ca.cps_uri:
                parent_cps_uri = parent_ca.cps_uri
                parent_cps_oid = parent_ca.cps_oid

        # Create CA certificate
        cert_pem, generated_key_pem = TrustStoreService.create_ca_certificate(
            subject=subject,
            private_key=private_key,
            issuer=issuer,
            issuer_private_key=issuer_private_key,
            issuer_cert=parent_cert,
            validity_days=validity_days,
            digest=digest,
            ocsp_uris=parent_ocsp_urls,
            cdp_urls=parent_cdp_urls,
            aia_ca_issuers_urls=parent_aia_urls,
            cps_uri=parent_cps_uri,
            cps_oid=parent_cps_oid,
            path_length=path_length,
            name_constraints_permitted=name_constraints_permitted,
            name_constraints_excluded=name_constraints_excluded,
            policy_constraints_require=policy_constraints_require,
            policy_constraints_inhibit=policy_constraints_inhibit,
            inhibit_any_policy=inhibit_any_policy,
            sia_urls=sia_urls,
            key_usage=key_usage,
            extended_key_usage=extended_key_usage,
            not_valid_after_max=parent_not_after,
        )

        # If using local key, use the generated key PEM
        if not use_hsm and generated_key_pem:
            key_pem = generated_key_pem

        # Parse certificate for details
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

        # Encrypt private key if encryption is enabled (local keys only)
        prv_encoded = CACreationMixin._encode_private_key(key_pem)

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
            url_slug=CACreationMixin._unique_url_slug(descr) if named_urls else None,
            descr=descr,
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=prv_encoded,
            serial=0,
            serial_number=str(cert.serial_number),
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
                ca.set_cdp_urls([f"{base_url}/cdp/{ca.url_ref}.crl"])
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

        # Validate it's a CA certificate (RFC 5280 §4.2.1.9 + §4.2.1.3) —
        # shared with the external-CSR completion so both enforce the same rules.
        from utils.ca_profile import validate_ca_certificate
        ca_warning = validate_ca_certificate(cert)
        if ca_warning:
            logger.warning(f"Imported CA {descr}: {ca_warning}")

        # Extract SKI for AKI fallback in CRL/cert signing
        ca_ski = None
        try:
            ski_ext = cert.extensions.get_extension_for_oid(
                x509.oid.ExtensionOID.SUBJECT_KEY_IDENTIFIER
            )
            ca_ski = ski_ext.value.key_identifier.hex(':').upper()
        except x509.ExtensionNotFound:
            pass

        # Encrypt imported private key at rest, mirroring create_internal_ca
        # (otherwise imported CA keys sit base64-only in the DB).
        prv_encoded = CACreationMixin._encode_private_key(
            key_pem.encode() if isinstance(key_pem, str) else key_pem
        ) if key_pem else None

        # Create CA record
        ca = CA(
            refid=str(uuid.uuid4()),
            descr=descr,
            crt=base64.b64encode(cert_pem.encode() if isinstance(cert_pem, str) else cert_pem).decode('utf-8'),
            prv=prv_encoded,
            serial=0,
            serial_number=str(cert.serial_number),
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            ski=ca_ski,
            valid_from=cert.not_valid_before_utc,
            valid_to=cert.not_valid_after_utc,
            imported_from='manual',
            created_by=username
        )

        db.session.add(ca)
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/ca/ca_creation.py:314: {_commit_err}", exc_info=True)
            raise

        # Audit log
        AuditService.log_ca('ca_imported', ca, f'Imported CA: {descr}')

        # Save files
        cert_path_bytes = cert_pem.encode() if isinstance(cert_pem, str) else cert_pem
        key_path_bytes = key_pem.encode() if key_pem else None
        save_ca_files(ca, cert_path_bytes, key_path_bytes)

        return ca

    # ------------------------------------------------------------------
    # External-CSR mode (#298): key pair lives in UCM, certificate is
    # signed by an external (typically offline root) CA.
    # ------------------------------------------------------------------

    @staticmethod
    def create_external_ca(
        descr: str,
        dn: Dict[str, str],
        key_type: str = '2048',
        digest: str = 'sha256',
        username: str = 'system',
        path_length: Optional[int] = None,
        key_usage: Optional[List[str]] = None,
        hsm_provider_id: Optional[int] = None,
        hsm_key_id: Optional[int] = None,
        hsm_key_label: Optional[str] = None,
        hsm_key_algorithm: Optional[str] = None,
        named_urls: bool = False,
    ) -> CA:
        """Create a pending CA: key pair + CA CSR, no certificate yet.

        The row uses the crt='' sentinel until complete_external_ca installs
        the externally signed certificate. The private key (or HSM binding)
        is created immediately so the CSR's public key is final.
        """
        private_key, key_pem, hsm_key = CACreationMixin._resolve_signing_key(
            key_type, hsm_provider_id, hsm_key_id, hsm_key_label, hsm_key_algorithm
        )

        subject = TrustStoreService.build_subject(dn)
        csr_pem = TrustStoreService.generate_ca_csr(
            subject, private_key, digest=digest,
            path_length=path_length, key_usage=key_usage,
        )

        ca = CA(
            refid=str(uuid.uuid4()),
            url_slug=CACreationMixin._unique_url_slug(descr) if named_urls else None,
            descr=descr,
            crt='',  # pending sentinel — awaiting the external certificate
            csr=base64.b64encode(csr_pem).decode('utf-8'),
            prv=CACreationMixin._encode_private_key(key_pem),
            serial=0,
            caref=None,
            subject=subject.rfc4514_string(),
            imported_from='external_csr',
            created_by=username,
            path_length=path_length,
            hsm_key_id=hsm_key.id if hsm_key else None,
        )

        db.session.add(ca)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to persist pending external CA: {e}")
            raise

        hsm_note = f' (HSM key: {hsm_key.label})' if hsm_key else ''
        AuditService.log_ca(
            'ca_created', ca,
            f'Created external-CSR CA: {descr}{hsm_note} (awaiting certificate)'
        )

        # Only the key goes on disk at this stage; the certificate file is
        # written by complete_external_ca. No CDP/OCSP until activation.
        if key_pem is not None:
            save_ca_key_file(ca, key_pem)

        return ca

    @staticmethod
    def complete_external_ca(
        ca: CA,
        cert_pem: bytes,
        username: str = 'system',
    ) -> Tuple[CA, List[str]]:
        """Install the externally signed certificate on an external-CSR CA.

        Serves both the first activation of a pending CA and a renewal on an
        already-active one — the invariant is identical: the certificate's
        public key MUST match the stored private key. Raises ValueError with
        a user-safe message on every rejection.

        Returns (ca, warnings, superseded) — superseded is None on first
        activation, else {'serial', 'valid_to'} for the replaced certificate,
        which stays valid until its notAfter unless revoked at the external
        root (UCM cannot publish that revocation: the issuer's key is not
        held here, see #298).
        """
        from services.hsm.ca_key_loader import get_ca_signing_key
        from utils.ca_profile import validate_ca_certificate
        from utils.key_match import certificate_matches_private_key

        warnings: List[str] = []
        was_pending = ca.is_pending

        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

        # 1. The uploaded certificate must belong to this CA's key — checked
        #    before anything else so a certificate for the wrong CA can never
        #    be attached, whatever else it looks like.
        try:
            # The key proves possession, it issues nothing: a CA under a revoked
            # ancestor must still be able to install a certificate from a healthy
            # issuer, the one way out of a revoked chain (review of #343)
            private_key = get_ca_signing_key(ca, allow_revoked=True)
        except Exception as e:
            logger.error(f"Cannot load signing key for CA {ca.id}: {e}", exc_info=True)
            raise ValueError("CA private key is not available")
        if not certificate_matches_private_key(cert, private_key):
            raise ValueError("Certificate public key does not match this CA's private key")

        # 2. CA constraints (same rules as CA import)
        ca_warning = validate_ca_certificate(cert)
        if ca_warning:
            warnings.append(ca_warning)

        # 3. Validity window
        now = utc_now()
        if to_naive_utc(cert.not_valid_after_utc) <= now:
            raise ValueError("Certificate has already expired")
        if to_naive_utc(cert.not_valid_before_utc) > now + timedelta(hours=24):
            warnings.append("Certificate is not valid yet (notBefore is in the future)")

        # 4. The signer is authoritative on the subject
        cert_subject = cert.subject.rfc4514_string()
        if ca.subject and cert_subject != ca.subject:
            warnings.append("Certificate subject differs from the CSR subject")

        # 5. SKI (uppercase — CA convention) and effective pathLen from the cert
        new_ski = None
        try:
            ski_ext = cert.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_KEY_IDENTIFIER
            )
            new_ski = ski_ext.value.key_identifier.hex(':').upper()
        except x509.ExtensionNotFound:
            pass
        new_path_length = None
        try:
            bc = cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
            new_path_length = bc.value.path_length
        except x509.ExtensionNotFound:
            pass

        # 6. Chain to the issuing CA when it is known to UCM (AKI→SKI, then
        #    issuer DN). Absence is non-blocking — the offline root may be
        #    imported later, and chain-repair re-links orphans.
        caref = None
        parent = None
        try:
            aki_ext = cert.extensions.get_extension_for_oid(
                ExtensionOID.AUTHORITY_KEY_IDENTIFIER
            )
            if aki_ext.value.key_identifier:
                aki_hex = aki_ext.value.key_identifier.hex(':').upper()
                parent = CA.query.filter(CA.ski == aki_hex, CA.id != ca.id).first()
        except x509.ExtensionNotFound:
            pass
        if parent is None:
            parent = CA.query.filter(
                CA.subject == cert.issuer.rfc4514_string(), CA.id != ca.id
            ).first()
        if parent is not None and parent.crt:
            try:
                parent_cert = x509.load_pem_x509_certificate(
                    base64.b64decode(parent.crt), default_backend()
                )
                cert.verify_directly_issued_by(parent_cert)
                caref = parent.refid
            except Exception:
                warnings.append(
                    "A CA matching the issuer was found but signature verification failed"
                )
        elif parent is None:
            warnings.append(
                "Issuing CA not found in UCM — import the external root "
                "(certificate only) to complete the chain"
            )

        # 7. Install — on renewal, remember the certificate being replaced so
        #    the operator can revoke it at the external root
        superseded = None
        if not was_pending and ca.serial_number \
                and ca.serial_number != str(cert.serial_number):
            old_serial_int = serial_to_int(ca.serial_number)
            superseded = {
                'serial': format(old_serial_int, 'x')
                          if old_serial_int is not None else ca.serial_number,
                'valid_to': utc_isoformat(ca.valid_to),
            }
        ca.crt = base64.b64encode(cert_pem).decode('utf-8')
        ca.subject = cert_subject
        ca.issuer = cert.issuer.rfc4514_string()
        ca.serial_number = str(cert.serial_number)
        ca.ski = new_ski
        ca.valid_from = cert.not_valid_before_utc
        ca.valid_to = cert.not_valid_after_utc
        ca.path_length = new_path_length
        if caref:
            ca.caref = caref
        ca.csr = None  # the outstanding CSR is fulfilled

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to install certificate on CA {ca.id}: {e}", exc_info=True)
            raise ValueError("Failed to install CA certificate")

        # First activation: auto-enable CDP like create_internal_ca does
        if was_pending:
            try:
                from utils.protocol_url import get_protocol_base_url
                base_url = get_protocol_base_url()
                if base_url:
                    ca.cdp_enabled = True
                    ca.set_cdp_urls([f"{base_url}/cdp/{ca.url_ref}.crl"])
                    db.session.commit()
            except Exception:
                pass

        AuditService.log_ca(
            'ca_certificate_installed', ca,
            f'External certificate installed (issuer: {cert.issuer.rfc4514_string()}, '
            f'chained: {bool(ca.caref)}, renewal: {not was_pending}'
            + (f", superseded serial: {superseded['serial']}" if superseded else '')
            + ')'
        )

        save_ca_files(ca, cert_pem, None)

        return ca, warnings, superseded

    @staticmethod
    def regenerate_ca_csr(
        ca: CA,
        digest: Optional[str] = None,
        username: str = 'system',
    ) -> bytes:
        """Re-issue a CA CSR from the CA's existing key (renewal, #298).

        Same-key by construction: the CSR is signed with the stored (or
        HSM-backed) private key, so the SKI stays stable across renewals.
        Subject/KeyUsage/pathLen mirror the current certificate when one is
        installed, else the outstanding CSR.
        """
        from services.hsm.ca_key_loader import get_ca_signing_key
        from utils.ca_profile import KU_NAME_TO_ATTR

        private_key = get_ca_signing_key(ca, allow_revoked=True)  # a CSR issues nothing

        subject = None
        key_usage = None
        path_length = ca.path_length
        if ca.crt:
            cert = x509.load_pem_x509_certificate(
                base64.b64decode(ca.crt), default_backend()
            )
            subject = cert.subject
            try:
                ku = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
                key_usage = []
                for name, attr in KU_NAME_TO_ATTR.items():
                    if name == 'nonRepudiation':
                        continue  # alias of contentCommitment
                    try:
                        # encipher_only/decipher_only raise unless
                        # key_agreement is set — treat as absent.
                        if getattr(ku, attr):
                            key_usage.append(name)
                    except ValueError:
                        pass
            except x509.ExtensionNotFound:
                pass
            try:
                bc = cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
                path_length = bc.value.path_length
            except x509.ExtensionNotFound:
                pass
        elif ca.csr:
            subject = x509.load_pem_x509_csr(
                base64.b64decode(ca.csr), default_backend()
            ).subject
        if subject is None:
            raise ValueError("CA has neither a certificate nor a CSR to derive the subject from")

        csr_pem = TrustStoreService.generate_ca_csr(
            subject, private_key, digest=digest or 'sha256',
            path_length=path_length, key_usage=key_usage,
        )
        ca.csr = base64.b64encode(csr_pem).decode('utf-8')

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to store renewed CSR for CA {ca.id}: {e}", exc_info=True)
            raise ValueError("Failed to store renewed CSR")

        AuditService.log_ca('ca_csr_renewed', ca, f'CA CSR re-issued from existing key: {ca.descr}')
        return csr_pem
