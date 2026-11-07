"""Externally-signed CRL upload for key-less / offline CAs (#302).

UCM can hold a CA it cannot sign for: an offline CA whose key was
file-exported and wiped, the certificate-only import of an external root,
or the (externally held) parent of an external-CSR intermediate. Revocations
decided next to that CA's offline key are published by generating the CRL
in the air-gapped environment and uploading it here; UCM validates it and
serves it on the CA's existing CDP path, and OCSP consults it for that
issuer's serials.
"""
import base64
import logging
import threading
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from models import db, CA
from models.crl import CRLMetadata

logger = logging.getLogger(__name__)


class ExternalCRLConflict(ValueError):
    """Upload refused because of CA state or CRL monotonicity, not content."""


# Parsed-entry cache for OCSP lookups: ca_id -> (crl_metadata_id, {serial: (revoked_at, reason)}).
# Invalidated when a newer CRL row is served (id mismatch) or on upload.
_ENTRY_CACHE_GUARD = threading.Lock()
_ENTRY_CACHE = {}
_ENTRY_CACHE_MAX_CAS = 32


def _naive_utc(value):
    """DB stores naive UTC — align aware datetimes from cryptography."""
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo else value


def _load_crl(raw: bytes) -> x509.CertificateRevocationList:
    try:
        return x509.load_pem_x509_crl(raw, default_backend())
    except Exception:
        pass
    return x509.load_der_x509_crl(raw, default_backend())


def _crl_number(crl: x509.CertificateRevocationList) -> Optional[int]:
    try:
        return crl.extensions.get_extension_for_class(x509.CRLNumber).value.crl_number
    except x509.ExtensionNotFound:
        return None


def _entry_reason(entry) -> Optional[x509.ReasonFlags]:
    try:
        return entry.extensions.get_extension_for_class(x509.CRLReason).value.reason
    except x509.ExtensionNotFound:
        return None


class ExternalCRLMixin:

    @staticmethod
    def install_external_crl(ca_id: int, raw: bytes, username: str = 'system') -> CRLMetadata:
        """Validate and store an externally-generated CRL for a key-less/offline CA.

        Raises ValueError on invalid content (parse/issuer/signature/profile)
        and ExternalCRLConflict when the CA can sign for itself or the CRL is
        not newer than the one currently served.
        """
        ca = db.session.get(CA, ca_id)
        if not ca:
            raise ValueError(f"CA with id {ca_id} not found")

        if not ca.crt:
            raise ExternalCRLConflict(
                "CA is awaiting its certificate: cannot validate a CRL without it"
            )
        if ca.has_private_key and not ca.offline:
            raise ExternalCRLConflict(
                "CA holds its private key and signs its own CRLs: "
                "external CRL upload is only for key-less or offline CAs"
            )

        try:
            crl = _load_crl(raw)
        except Exception:
            raise ValueError("Invalid CRL file: expected PEM or DER")

        ca_cert_pem = base64.b64decode(ca.crt)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())

        if crl.issuer != ca_cert.subject:
            raise ValueError(
                "CRL issuer does not match this CA's subject "
                f"({crl.issuer.rfc4514_string()!r} != {ca_cert.subject.rfc4514_string()!r})"
            )

        try:
            signature_valid = crl.is_signature_valid(ca_cert.public_key())
        except Exception as e:
            logger.warning(f"External CRL signature check failed for CA {ca_id}: {e}")
            signature_valid = False
        if not signature_valid:
            raise ValueError("CRL signature does not verify against this CA's certificate")

        try:
            crl.extensions.get_extension_for_class(x509.DeltaCRLIndicator)
            raise ValueError(
                "Delta CRLs are not supported for external upload: upload the complete CRL"
            )
        except x509.ExtensionNotFound:
            pass

        this_update = _naive_utc(crl.last_update_utc)
        next_update = _naive_utc(crl.next_update_utc)
        if not next_update:
            raise ValueError(
                "CRL has no nextUpdate: conforming CRL issuers must include it (RFC 5280 §5.1.2.5)"
            )

        number = _crl_number(crl)
        latest = CRLMetadata.query.filter_by(ca_id=ca.id, is_delta=False).order_by(
            CRLMetadata.crl_number.desc()
        ).first()
        if latest:
            if this_update < latest.this_update:
                raise ExternalCRLConflict(
                    "CRL is older than the currently served one "
                    f"(thisUpdate {this_update.isoformat()} < {latest.this_update.isoformat()})"
                )
            if number is not None:
                if number < latest.crl_number:
                    raise ExternalCRLConflict(
                        f"CRL number {number} is lower than the currently served "
                        f"CRL number {latest.crl_number}: numbers must increase monotonically"
                    )
                if number == latest.crl_number and this_update == latest.this_update:
                    raise ExternalCRLConflict("This CRL is already being served")

        # No CRLNumber extension (e.g. plain `openssl ca -gencrl`): keep the
        # internal counter monotonic so ordering and future self-signed CRLs
        # (after a restore) stay consistent.
        from .numbering import allocate_crl_number, raise_crl_number_floor
        if number is None:
            stored_number = allocate_crl_number(ca, ca_cert)
        else:
            raise_crl_number_floor(ca, ca_cert, number)
            if CRLMetadata.query.filter_by(ca_id=ca.id, crl_number=number).first() is not None:
                db.session.rollback()
                # RFC 5280 §5.2.3: two CRLs of one issuer MUST NOT share a number
                raise ExternalCRLConflict(
                    f"CRL number {number} is already used by another CRL of this CA")
            stored_number = number

        entries = len(crl)
        crl_metadata = CRLMetadata(
            ca_id=ca.id,
            crl_number=stored_number,
            this_update=this_update,
            next_update=next_update,
            crl_pem=crl.public_bytes(serialization.Encoding.PEM).decode('utf-8'),
            crl_der=crl.public_bytes(serialization.Encoding.DER),
            revoked_count=entries,
            generated_by=username,
            is_delta=False,
            base_crl_number=None,
            is_external=True,
        )
        db.session.add(crl_metadata)

        # Drop the CA's cached OCSP responses in the same transaction: a
        # pre-generated 'good' answer must not outlive a CRL that revokes the
        # serial (RFC 6960 freshness — same rule as revocation elsewhere).
        from models import OCSPResponse
        purged = OCSPResponse.query.filter_by(ca_id=ca.id).delete(synchronize_session=False)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        # After the commit: written before it, an audit failure rolled back
        # the installed CRL and the purge of the cached responses with it,
        # while the caller was told the CRL was in place.
        from services.audit_service import AuditService
        AuditService.log_ca(
            'install_external_crl', ca,
            f"Installed externally-signed CRL #{stored_number} for CA {ca.descr} "
            f"({entries} entries, nextUpdate {next_update.isoformat()}, "
            f"{purged} cached OCSP response(s) invalidated)",
            username=username,
        )

        with _ENTRY_CACHE_GUARD:
            _ENTRY_CACHE.pop(ca.id, None)

        logger.info(
            f"Installed external CRL #{stored_number} for CA {ca.descr} ({entries} entries)"
        )
        from services.events import event_bus
        event_bus.emit(
            'crl.updated',
            {'crl': {
                'id': crl_metadata.id,
                'ca_id': ca.id,
                'crl_number': stored_number,
                'is_external': True,
            }},
            ca_refid=ca.refid,
            meta={'actor': username},
        )
        return crl_metadata

    @staticmethod
    def get_external_revocation(ca_id: int, serial_int: int) -> Optional[Tuple]:
        """Revocation info for a serial from the CA's served external CRL.

        Returns (revoked_at, reason ReasonFlags or None) when the latest served
        CRL for this CA is an external upload containing the serial, else None.
        Entries are parsed once per CRL row and cached for OCSP lookups.
        """
        row = db.session.query(
            CRLMetadata.id, CRLMetadata.is_external
        ).filter_by(ca_id=ca_id, is_delta=False).order_by(
            CRLMetadata.crl_number.desc()
        ).first()
        if not row or not row.is_external:
            return None

        with _ENTRY_CACHE_GUARD:
            cached = _ENTRY_CACHE.get(ca_id)
        if not cached or cached[0] != row.id:
            full = db.session.get(CRLMetadata, row.id)
            if not full or not full.crl_der:
                return None
            try:
                crl = x509.load_der_x509_crl(full.crl_der, default_backend())
            except Exception as e:
                logger.error(f"Failed to parse stored external CRL {row.id}: {e}")
                return None
            mapping = {
                entry.serial_number: (
                    _naive_utc(entry.revocation_date_utc), _entry_reason(entry)
                )
                for entry in crl
            }
            cached = (row.id, mapping)
            with _ENTRY_CACHE_GUARD:
                if len(_ENTRY_CACHE) >= _ENTRY_CACHE_MAX_CAS:
                    _ENTRY_CACHE.clear()
                _ENTRY_CACHE[ca_id] = cached

        return cached[1].get(serial_int)
