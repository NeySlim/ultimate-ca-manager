import base64
import logging
from datetime import timedelta
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID

from models import db, CA, Certificate
from models.crl import CRLMetadata
from utils.datetime_utils import utc_now
from ._constants import REASON_MAP
from .query import CRLQueryMixin

logger = logging.getLogger(__name__)


class CRLGenerationMixin:

    DEFAULT_VALIDITY_DAYS = 7

    @staticmethod
    def generate_crl(
        ca_id: int,
        validity_days: int = 7,
        username: str = 'system'
    ) -> CRLMetadata:
        ca = CA.query.get(ca_id)
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

        for cert in revoked_certs:
            if not cert.serial_number:
                continue

            try:
                serial_int = int(cert.serial_number.replace(':', ''), 16)
                if serial_int.bit_length() > 159:
                    logger.warning(
                        f"CRL: serial {cert.serial_number} exceeds 159 bits "
                        f"({serial_int.bit_length()} bits), truncating for CRL entry"
                    )
                    serial_int = serial_int & ((1 << 159) - 1)
            except (ValueError, AttributeError):
                continue

            revoked_builder = x509.RevokedCertificateBuilder()
            revoked_builder = revoked_builder.serial_number(serial_int)
            revoked_builder = revoked_builder.revocation_date(cert.revoked_at or now)

            if cert.revoke_reason:
                reason = REASON_MAP.get(cert.revoke_reason, x509.ReasonFlags.unspecified)
                revoked_builder = revoked_builder.add_extension(
                    x509.CRLReason(reason),
                    critical=False
                )

            builder = builder.add_revoked_certificate(revoked_builder.build())

        builder = builder.add_extension(
            x509.CRLNumber(crl_number),
            critical=False
        )

        try:
            aki = ca_cert.extensions.get_extension_for_oid(
                ExtensionOID.AUTHORITY_KEY_IDENTIFIER
            ).value
            builder = builder.add_extension(aki, critical=False)
        except x509.ExtensionNotFound:
            try:
                ski = ca_cert.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_KEY_IDENTIFIER
                ).value
                aki = x509.AuthorityKeyIdentifier(
                    key_identifier=ski.digest,
                    authority_cert_issuer=None,
                    authority_cert_serial_number=None
                )
                builder = builder.add_extension(aki, critical=False)
            except x509.ExtensionNotFound:
                pass

        if ca.delta_crl_enabled:
            primary_cdp = ca.get_primary_cdp_url()
            if primary_cdp:
                from urllib.parse import urlparse
                parsed = urlparse(primary_cdp.replace('{ca_refid}', ca.refid))
                delta_url = f"{parsed.scheme}://{parsed.netloc}/cdp/{ca.refid}-delta.crl"
            try:
                builder = builder.add_extension(
                    x509.FreshestCRL([
                        x509.DistributionPoint(
                            full_name=[x509.UniformResourceIdentifier(delta_url)],
                            relative_name=None,
                            reasons=None,
                            crl_issuer=None
                        )
                    ]),
                    critical=False
                )
            except Exception as e:
                logger.warning(f"Could not add FreshestCRL extension: {e}")

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
            revoked_count=len(revoked_certs),
            generated_by=username,
            is_delta=False,
            base_crl_number=None
        )

        db.session.add(crl_metadata)

        from services.audit_service import AuditService
        AuditService.log_ca('generate_crl', ca,
                            f"Generated CRL #{crl_number} for CA {ca.descr} with "
                            f"{len(revoked_certs)} revoked certificates",
                            username=username)

        db.session.commit()

        return crl_metadata

    @staticmethod
    def generate_delta_crl(
        ca_id: int,
        validity_hours: int = 24,
        username: str = 'system'
    ) -> CRLMetadata:
        ca = CA.query.get(ca_id)
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

        for cert in revoked_certs:
            if not cert.serial_number:
                continue
            try:
                serial_int = int(cert.serial_number.replace(':', ''), 16)
                if serial_int.bit_length() > 159:
                    serial_int = serial_int & ((1 << 159) - 1)
            except (ValueError, AttributeError):
                continue

            revoked_builder = x509.RevokedCertificateBuilder()
            revoked_builder = revoked_builder.serial_number(serial_int)
            revoked_builder = revoked_builder.revocation_date(cert.revoked_at or now)

            if cert.revoke_reason:
                reason = REASON_MAP.get(cert.revoke_reason, x509.ReasonFlags.unspecified)
                revoked_builder = revoked_builder.add_extension(
                    x509.CRLReason(reason), critical=False
                )

            builder = builder.add_revoked_certificate(revoked_builder.build())

        builder = builder.add_extension(
            x509.CRLNumber(crl_number), critical=False
        )

        builder = builder.add_extension(
            x509.DeltaCRLIndicator(base_crl.crl_number), critical=True
        )

        primary_cdp = ca.get_primary_cdp_url()
        if primary_cdp:
            try:
                cdp_resolved = primary_cdp.replace('{ca_refid}', ca.refid)
                builder = builder.add_extension(
                    x509.IssuingDistributionPoint(
                        full_name=[x509.UniformResourceIdentifier(cdp_resolved)],
                        relative_name=None,
                        only_contains_user_certs=False,
                        only_contains_ca_certs=False,
                        only_some_reasons=None,
                        indirect_crl=False,
                        only_contains_attribute_certs=False
                    ),
                    critical=True
                )
            except Exception as e:
                logger.warning(f"Could not add IssuingDistributionPoint to delta CRL: {e}")

        try:
            aki = ca_cert.extensions.get_extension_for_oid(
                ExtensionOID.AUTHORITY_KEY_IDENTIFIER
            ).value
            builder = builder.add_extension(aki, critical=False)
        except x509.ExtensionNotFound:
            try:
                ski = ca_cert.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_KEY_IDENTIFIER
                ).value
                aki = x509.AuthorityKeyIdentifier(
                    key_identifier=ski.digest,
                    authority_cert_issuer=None,
                    authority_cert_serial_number=None
                )
                builder = builder.add_extension(aki, critical=False)
            except x509.ExtensionNotFound:
                pass

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
                revoked_count=len(revoked_certs),
                generated_by=username,
                is_delta=True,
                base_crl_number=base_crl.crl_number
            )

            db.session.add(crl_metadata)

            from services.audit_service import AuditService
            AuditService.log_ca('generate_delta_crl', ca,
                                f"Generated delta CRL #{crl_number} (base #{base_crl.crl_number}) "
                                f"with {len(revoked_certs)} new revocations",
                                username=username)

            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        logger.info(f"Generated delta CRL #{crl_number} for CA {ca.descr} "
                    f"(base #{base_crl.crl_number}, {len(revoked_certs)} entries)")

        return crl_metadata
