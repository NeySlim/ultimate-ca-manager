import base64
import logging
from datetime import timedelta
from typing import Optional
from urllib.parse import urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend

from models import db, CA, Certificate
from models.crl import CRLMetadata
from utils.datetime_utils import utc_now
from utils.serial_format import serial_to_int
from utils.x509_aki import authority_key_identifier_from_issuer
from ._constants import REASON_MAP
from .query import CRLQueryMixin

logger = logging.getLogger(__name__)


def _authority_key_identifier_for_crl(ca_cert: x509.Certificate) -> x509.AuthorityKeyIdentifier:
    """RFC 5280 §5.2.1 — CRL AKI must identify the signing CA key (its SKI)."""
    return authority_key_identifier_from_issuer(ca_cert)


def _apply_invalidity_date(
    revoked_builder: x509.RevokedCertificateBuilder,
    cert: Certificate,
) -> x509.RevokedCertificateBuilder:
    """RFC 5280 §5.3.2 — emit invalidityDate when known (optional)."""
    invalidity_at = getattr(cert, 'invalidity_at', None)
    if not invalidity_at:
        return revoked_builder
    try:
        return revoked_builder.add_extension(
            x509.InvalidityDate(invalidity_at),
            critical=False,
        )
    except Exception as e:
        logger.warning(
            f"CRL: omitting invalidityDate for cert {cert.id}: {e}"
        )
        return revoked_builder


def _apply_revoke_reason(
    revoked_builder: x509.RevokedCertificateBuilder,
    revoke_reason: Optional[str],
    *,
    is_delta: bool,
) -> x509.RevokedCertificateBuilder:
    """Attach CRLReason when RFC-conformant.

    RFC 5280 §5.3.1:
    - omit the extension instead of emitting ``unspecified``
    - ``removeFromCRL`` may only appear on delta CRLs
    """
    if not revoke_reason:
        return revoked_builder

    if revoke_reason == 'unspecified':
        return revoked_builder

    if revoke_reason == 'removeFromCRL' and not is_delta:
        logger.warning(
            "CRL: omitting removeFromCRL reason on full CRL (RFC 5280 §5.3.1 — delta only)"
        )
        return revoked_builder

    reason = REASON_MAP.get(revoke_reason)
    if reason is None or reason is x509.ReasonFlags.unspecified:
        logger.warning(f"CRL: omitting unknown/unspecified revoke_reason={revoke_reason!r}")
        return revoked_builder

    return revoked_builder.add_extension(x509.CRLReason(reason), critical=False)


def _add_freshest_crl(builder: x509.CertificateRevocationListBuilder, ca: CA):
    """RFC 5280 §5.2.6 — non-critical pointer to the delta CRL (complete CRLs only)."""
    if not ca.delta_crl_enabled:
        return builder

    primary_cdp = ca.get_primary_cdp_url()
    if not primary_cdp:
        return builder

    try:
        parsed = urlparse(primary_cdp.replace('{ca_refid}', ca.refid))
        delta_url = f"{parsed.scheme}://{parsed.netloc}/cdp/{ca.refid}-delta.crl"
        return builder.add_extension(
            x509.FreshestCRL([
                x509.DistributionPoint(
                    full_name=[x509.UniformResourceIdentifier(delta_url)],
                    relative_name=None,
                    reasons=None,
                    crl_issuer=None,
                )
            ]),
            critical=False,
        )
    except Exception as e:
        logger.warning(f"Could not add FreshestCRL extension: {e}")
        return builder


def _parse_revoked_serial(cert: Certificate, *, context: str) -> Optional[int]:
    if not cert.serial_number:
        return None
    serial_int = serial_to_int(cert.serial_number)
    if serial_int is None or serial_int <= 0:
        logger.warning(
            f"{context}: skipping cert {cert.id} with unparseable serial {cert.serial_number!r}"
        )
        return None
    if serial_int.bit_length() > 159:
        # RFC 5280 §4.1.2.2 caps serials at 20 octets (≤159 bits effective).
        logger.error(
            f"{context}: cert {cert.id} serial exceeds 159 bits "
            f"({serial_int.bit_length()} bits); skipping — revocation NOT in CRL"
        )
        return None
    return serial_int


class CRLGenerationMixin:

    DEFAULT_VALIDITY_DAYS = 7

    @staticmethod
    def generate_crl(
        ca_id: int,
        validity_days: int = 7,
        username: str = 'system'
    ) -> CRLMetadata:
        ca = db.session.get(CA, ca_id)
        if not ca:
            raise ValueError(f"CA with id {ca_id} not found")

        if not ca.has_private_key:
            raise ValueError(f"CA {ca.descr} does not have a private key - cannot sign CRL")

        ca_cert_pem = base64.b64decode(ca.crt).decode('utf-8')
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem.encode(), default_backend())

        from services.hsm.ca_key_loader import get_ca_signing_key
        ca_private_key = get_ca_signing_key(ca)

        revoked_certs = CRLQueryMixin.get_revoked_certificates(ca_id)

        last_crl = CRLMetadata.query.filter_by(ca_id=ca_id).order_by(
            CRLMetadata.crl_number.desc()
        ).first()
        crl_number = 1 if not last_crl else last_crl.crl_number + 1

        now = utc_now()
        builder = x509.CertificateRevocationListBuilder()
        builder = builder.issuer_name(ca_cert.subject)
        builder = builder.last_update(now)
        builder = builder.next_update(now + timedelta(days=validity_days))

        entries = 0
        for cert in revoked_certs:
            serial_int = _parse_revoked_serial(cert, context='CRL')
            if serial_int is None:
                continue

            revoked_builder = x509.RevokedCertificateBuilder()
            revoked_builder = revoked_builder.serial_number(serial_int)
            revoked_builder = revoked_builder.revocation_date(cert.revoked_at or now)
            revoked_builder = _apply_revoke_reason(
                revoked_builder, cert.revoke_reason, is_delta=False
            )
            revoked_builder = _apply_invalidity_date(revoked_builder, cert)
            builder = builder.add_revoked_certificate(revoked_builder.build())
            entries += 1

        builder = builder.add_extension(x509.CRLNumber(crl_number), critical=False)
        builder = builder.add_extension(
            _authority_key_identifier_for_crl(ca_cert), critical=False
        )
        # RFC 5280 §5.2.4: base and delta MUST both omit IDP or carry identical IDP.
        # UCM issues unpartitioned CRLs — omit IDP on both full and delta.
        builder = _add_freshest_crl(builder, ca)

        crl = builder.sign(ca_private_key, hashes.SHA256(), default_backend())

        crl_pem = crl.public_bytes(serialization.Encoding.PEM).decode('utf-8')
        crl_der = crl.public_bytes(serialization.Encoding.DER)

        crl_metadata = CRLMetadata(
            ca_id=ca_id,
            crl_number=crl_number,
            this_update=now,
            next_update=now + timedelta(days=validity_days),
            crl_pem=crl_pem,
            crl_der=crl_der,
            revoked_count=entries,
            generated_by=username,
            is_delta=False,
            base_crl_number=None
        )

        db.session.add(crl_metadata)

        from services.audit_service import AuditService
        AuditService.log_ca(
            'generate_crl', ca,
            f"Generated CRL #{crl_number} for CA {ca.descr} with "
            f"{entries} revoked certificates",
            username=username,
        )

        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(
                f"Commit failed in services/crl/generation.py: {_commit_err}",
                exc_info=True,
            )
            raise

        return crl_metadata

    @staticmethod
    def generate_delta_crl(
        ca_id: int,
        validity_hours: int = 24,
        username: str = 'system'
    ) -> CRLMetadata:
        ca = db.session.get(CA, ca_id)
        if not ca:
            raise ValueError(f"CA with id {ca_id} not found")
        if not ca.has_private_key:
            raise ValueError(f"CA {ca.descr} does not have a private key")
        if not ca.cdp_enabled:
            raise ValueError("CDP is not enabled for this CA")
        if not ca.delta_crl_enabled:
            raise ValueError("Delta CRL is not enabled for this CA")
        if validity_hours < 1 or validity_hours > 720:
            raise ValueError("validity_hours must be between 1 and 720")

        base_crl = CRLMetadata.query.filter_by(
            ca_id=ca_id, is_delta=False
        ).order_by(CRLMetadata.crl_number.desc()).first()

        if not base_crl:
            raise ValueError(f"No base CRL exists for CA {ca.descr} — generate a full CRL first")

        ca_cert_pem = base64.b64decode(ca.crt).decode('utf-8')
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem.encode(), default_backend())

        from services.hsm.ca_key_loader import get_ca_signing_key
        ca_private_key = get_ca_signing_key(ca)

        revoked_certs = Certificate.query.filter(
            Certificate.caref == ca.refid,
            Certificate.revoked == True,
            Certificate.revoked_at > base_crl.this_update
        ).all()

        last_crl = CRLMetadata.query.filter_by(ca_id=ca_id).order_by(
            CRLMetadata.crl_number.desc()
        ).first()
        crl_number = 1 if not last_crl else last_crl.crl_number + 1

        now = utc_now()
        builder = x509.CertificateRevocationListBuilder()
        builder = builder.issuer_name(ca_cert.subject)
        builder = builder.last_update(now)
        builder = builder.next_update(now + timedelta(hours=validity_hours))

        entries = 0
        for cert in revoked_certs:
            serial_int = _parse_revoked_serial(cert, context='Delta CRL')
            if serial_int is None:
                continue

            revoked_builder = x509.RevokedCertificateBuilder()
            revoked_builder = revoked_builder.serial_number(serial_int)
            revoked_builder = revoked_builder.revocation_date(cert.revoked_at or now)
            revoked_builder = _apply_revoke_reason(
                revoked_builder, cert.revoke_reason, is_delta=True
            )
            revoked_builder = _apply_invalidity_date(revoked_builder, cert)
            builder = builder.add_revoked_certificate(revoked_builder.build())
            entries += 1

        builder = builder.add_extension(x509.CRLNumber(crl_number), critical=False)
        builder = builder.add_extension(
            x509.DeltaCRLIndicator(base_crl.crl_number), critical=True
        )
        # No IssuingDistributionPoint — must match the base CRL (both omit).
        builder = builder.add_extension(
            _authority_key_identifier_for_crl(ca_cert), critical=False
        )

        crl = builder.sign(ca_private_key, hashes.SHA256(), default_backend())

        crl_pem = crl.public_bytes(serialization.Encoding.PEM).decode('utf-8')
        crl_der = crl.public_bytes(serialization.Encoding.DER)

        try:
            crl_metadata = CRLMetadata(
                ca_id=ca_id,
                crl_number=crl_number,
                this_update=now,
                next_update=now + timedelta(hours=validity_hours),
                crl_pem=crl_pem,
                crl_der=crl_der,
                revoked_count=entries,
                generated_by=username,
                is_delta=True,
                base_crl_number=base_crl.crl_number
            )

            db.session.add(crl_metadata)

            from services.audit_service import AuditService
            AuditService.log_ca(
                'generate_delta_crl', ca,
                f"Generated delta CRL #{crl_number} (base #{base_crl.crl_number}) "
                f"with {entries} new revocations",
                username=username,
            )

            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        logger.info(
            f"Generated delta CRL #{crl_number} for CA {ca.descr} "
            f"(base #{base_crl.crl_number}, {entries} entries)"
        )

        return crl_metadata
