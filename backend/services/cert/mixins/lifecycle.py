"""Certificate lifecycle mixin — create, revoke, delete, list, get"""
import base64
import uuid
import json
import logging
from datetime import datetime, timedelta, timezone as _tz
from typing import Dict, List, Optional

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from models import db, CA, Certificate, CertificateTemplate, SystemConfig, RevokedSerial
from services.file_regen_service import mirror_private_key
from services.ocsp_service import OCSPService
from services.trust_store import TrustStoreService
from utils.ct_client import collect_scts, embed_scts_in_certificate
from utils.file_naming import cert_cert_path, cert_key_path, cert_csr_path, cleanup_old_files
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

try:
    from security.encryption import decrypt_private_key, encrypt_private_key
    HAS_ENCRYPTION = True
except ImportError:
    HAS_ENCRYPTION = False

    def decrypt_private_key(data):
        return data

    def encrypt_private_key(data):
        return data


class LifecycleMixin:

    @staticmethod
    def create_certificate(
        descr: str,
        caref: str,
        dn: Dict[str, str],
        cert_type: str = 'server_cert',
        key_type: str = '2048',
        validity_days: int = 397,
        digest: str = 'sha256',
        san_dns: Optional[List[str]] = None,
        san_ip: Optional[List[str]] = None,
        san_uri: Optional[List[str]] = None,
        san_email: Optional[List[str]] = None,
        ocsp_uri: Optional[str] = None,
        private_key_location: str = 'stored',
        template_id: Optional[int] = None,
        username: str = 'system',
        ocsp_must_staple: bool = False,
    ) -> Certificate:
        """
        Create a certificate signed by a CA

        Args:
            descr: Description
            caref: CA refid
            dn: Distinguished Name
            cert_type: usr_cert, server_cert, combined_server_client, ca_cert
            key_type: Key type
            validity_days: Validity in days
            digest: Hash algorithm
            san_dns: DNS SANs
            san_ip: IP SANs
            san_uri: URI SANs
            san_email: Email SANs
            ocsp_uri: OCSP responder URI
            private_key_location: 'stored' or 'download_only'
            template_id: Certificate template ID (optional)
            username: User creating certificate
            ocsp_must_staple: Enable OCSP Must-Staple extension

        Returns:
            Certificate model instance
        """
        # Apply template if provided
        template = None
        if template_id:
            template = db.session.get(CertificateTemplate, template_id)
            if template:
                # Use template defaults if values not explicitly provided
                key_type = key_type if key_type != '2048' else template.key_type or key_type
                validity_days = validity_days if validity_days != 397 else template.validity_days or validity_days
                digest = digest if digest != 'sha256' else template.digest or digest

        # Record divergences from the template on the final effective values
        # (#258) — inherited-as-default values compare equal and are not
        # flagged; an explicit override is.
        from services.template_service import compute_template_overrides
        template_overrides = compute_template_overrides(
            template, key_type=key_type, validity_days=validity_days, digest=digest)

        # Validate SAN emails if provided
        if san_email:
            from services.cert.mixins.inspection import InspectionMixin
            invalid_emails = [email for email in san_email if not InspectionMixin.validate_email(email)]
            if invalid_emails:
                raise ValueError(f"Invalid email address(es) in SAN: {', '.join(invalid_emails)}")

        # Get CA
        ca = CA.query.filter_by(refid=caref).first()
        if not ca:
            raise ValueError(f"CA not found: {caref}")

        if not ca.has_private_key:
            raise ValueError("CA has no private key - cannot sign certificates")

        if not ca.crt:
            raise ValueError("CA is awaiting its certificate - cannot sign certificates")
        if ca.offline:
            raise ValueError("CA is offline; restore it before issuing")
        if ca.revoked_in_chain:
            raise ValueError("CA is revoked and can no longer sign")

        # Load CA certificate
        ca_cert_pem = base64.b64decode(ca.crt)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
        from utils.ca_signing_window import check_issuer_window
        check_issuer_window(ca_cert)

        # Load CA signing key (local or HSM-backed)
        from services.hsm.ca_key_loader import get_ca_signing_key
        try:
            ca_private_key = get_ca_signing_key(ca)
        except Exception as e:
            raise ValueError(f"Failed to load CA signing key: {e}")

        # Build subject
        subject = TrustStoreService.build_subject(dn)

        # Prepare CDP URLs if CA has it enabled
        cdp_urls = None
        if ca.cdp_enabled:
            cdp_urls = [url.replace('{ca_refid}', ca.url_ref) for url in ca.get_cdp_urls()]
            if not cdp_urls:
                cdp_urls = None

        # Prepare OCSP URLs if CA has it enabled
        ocsp_urls = None
        if ca.ocsp_enabled:
            ocsp_urls = ca.get_ocsp_urls()
            if not ocsp_urls:
                ocsp_urls = None

        # Prepare AIA CA Issuers URLs if CA has it enabled
        aia_ca_issuers_urls = None
        if ca.aia_ca_issuers_enabled:
            aia_ca_issuers_urls = [url.replace('{ca_refid}', ca.url_ref) for url in ca.get_aia_urls()]
            if not aia_ca_issuers_urls:
                aia_ca_issuers_urls = None

        # CPS
        cps_uri = ca.cps_uri if ca.cps_enabled and ca.cps_uri else None
        cps_oid = ca.cps_oid if cps_uri else None

        # The leaf's expiry is clamped to the CA's own by
        # TrustStoreService.create_certificate (to the instant, not the day)

        # Create certificate
        cert_pem, key_pem = TrustStoreService.create_certificate(
            subject=subject,
            ca_cert=ca_cert,
            ca_private_key=ca_private_key,
            cert_type=cert_type,
            validity_days=validity_days,
            digest=digest,
            key_type=key_type,
            san_dns=san_dns,
            san_ip=san_ip,
            san_uri=san_uri,
            san_email=san_email,
            ocsp_uris=ocsp_urls,
            cdp_urls=cdp_urls,
            aia_ca_issuers_urls=aia_ca_issuers_urls,
            cps_uri=cps_uri,
            cps_oid=cps_oid,
            ocsp_must_staple=ocsp_must_staple,
        )

        # Parse certificate
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

        # RFC 6962 pre-certificate flow. The first signature above is an
        # internal template: when enabled it is replaced by a CA-signed
        # pre-certificate for CT submission, then by the final SCT-bearing
        # certificate before anything is persisted or returned.
        from utils.ct_client import apply_ct_policy
        ct_embed = SystemConfig.query.filter_by(key='ct_embed_sct').first()
        signed_cert, embedded_scts = apply_ct_policy(cert, ca_cert, ca_private_key)
        if signed_cert is not cert:
            cert = signed_cert
            cert_pem = cert.public_bytes(serialization.Encoding.PEM)

        # Increment CA serial
        ca.serial = (ca.serial or 0) + 1

        # Encrypt private key if encryption is enabled and key is stored
        prv_encoded = None
        if private_key_location == 'stored':
            prv_encoded = base64.b64encode(key_pem).decode('utf-8')
            prv_encoded = encrypt_private_key(prv_encoded)

        # Create certificate record
        certificate = Certificate(
            refid=str(uuid.uuid4()),
            descr=descr,
            caref=caref,
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=prv_encoded,
            cert_type=cert_type,
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            serial_number=str(cert.serial_number),
            valid_from=cert.not_valid_before_utc,
            valid_to=cert.not_valid_after_utc,
            # SANs
            san_dns=json.dumps(san_dns) if san_dns else None,
            san_ip=json.dumps(san_ip) if san_ip else None,
            san_email=json.dumps(san_email) if san_email else None,
            san_uri=json.dumps(san_uri) if san_uri else None,
            # OCSP and key location
            ocsp_uri=ocsp_uri,
            ocsp_must_staple=ocsp_must_staple,
            private_key_location=private_key_location,
            # Template reference
            template_id=template_id,
            template_overrides=template_overrides,
            # Other fields
            revoked=False,
            imported_from='generated',
            created_by=username
        )

        db.session.add(certificate)
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/cert/mixins/lifecycle.py: {_commit_err}", exc_info=True)
            raise

        # Audit log
        from services.audit_service import AuditService
        AuditService.log_certificate('cert_created', certificate, f'Created certificate: {descr}')

        # Persist embedded SCT metadata. If embedding is disabled, preserve the
        # legacy post-issuance add-chain auto-submission behavior.
        try:
            scts_to_store = embedded_scts
            if not scts_to_store:
                ct_enabled = SystemConfig.query.filter_by(key='ct_enabled').first()
                ct_auto = SystemConfig.query.filter_by(key='ct_auto_submit').first()
                if (
                    not (ct_embed and str(ct_embed.value).lower() == 'true')
                    and ct_enabled and ct_enabled.value == 'true'
                    and ct_auto and ct_auto.value == 'true'
                ):
                    ct_log_urls_config = SystemConfig.query.filter_by(key='ct_log_urls').first()
                    ct_log_urls = json.loads(ct_log_urls_config.value) \
                        if ct_log_urls_config and ct_log_urls_config.value else None
                    chain = [cert_pem.decode('utf-8') if isinstance(cert_pem, bytes) else cert_pem]
                    chain.append(
                        ca_cert_pem.decode('utf-8')
                        if isinstance(ca_cert_pem, bytes) else ca_cert_pem
                    )
                    scts_to_store = collect_scts(chain, ct_log_urls)

            if scts_to_store:
                config = SystemConfig(
                    key=f'cert_scts_{certificate.id}',
                    value=json.dumps(scts_to_store),
                )
                db.session.add(config)
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    logger.warning(
                        f"Failed to store SCT metadata for cert "
                        f"{certificate.id}: {e}"
                    )
                else:
                    logger.info(
                        f"Certificate {certificate.id} recorded "
                        f"{len(scts_to_store)} SCT(s)"
                    )
        except Exception as e:
            logger.warning(f"CT metadata handling failed for cert {certificate.id}: {e}")

        # Save files
        cert_path = cert_cert_path(certificate)
        with open(cert_path, 'wb') as f:
            f.write(cert_pem)

        mirror_private_key(
            cert_key_path(certificate),
            key_pem,
            context=f"certificate {certificate.id}",
        )

        from services.webhook_service import emit_cert_issued
        emit_cert_issued(certificate.to_dict(), ca_refid=certificate.caref, actor=username)

        return certificate

    @staticmethod
    def _restore_revocation_state(certificate, previous: dict, cert_id: int) -> None:
        """Undo an in-memory revocation after the RevokedSerial write failed.

        Restores the exact prior values (including a pre-existing
        invalidityDate) instead of blanking the columns — a certificate that
        was never successfully revoked must look untouched.
        """
        certificate.revoked = previous['revoked']
        certificate.revoked_at = previous['revoked_at']
        certificate.revoke_reason = previous['revoke_reason']
        certificate.invalidity_at = previous['invalidity_at']
        try:
            db.session.commit()
        except Exception as _rollback_err:
            db.session.rollback()
            logger.error(
                f"Failed to roll back revocation for cert {cert_id}: {_rollback_err}",
                exc_info=True,
            )

    @staticmethod
    def revoke_certificate(
        cert_id: int,
        reason: str = 'unspecified',
        username: str = 'system',
        invalidity_at=None,
        _suppress_events: bool = False,
    ) -> Certificate:
        """
        Revoke a certificate

        Args:
            cert_id: Certificate ID
            reason: Revocation reason
            username: User revoking
            invalidity_at: Optional RFC 5280 §5.3.2 invalidityDate (datetime)
            _suppress_events: Skip audit log, webhook, CRL generation, and
                OCSP cache invalidation. Used by the renewal flow which emits
                a single `cert_renewed` event instead of cert_revoked +
                cert_deleted + cert_renewed.

        Returns:
            Updated certificate
        """
        certificate = db.session.get(Certificate, cert_id)
        if not certificate:
            raise ValueError("Certificate not found")

        if certificate.revoked:
            raise ValueError("Certificate already revoked")

        # Snapshot the pre-revocation state so a failed RevokedSerial write
        # can be undone exactly (see _restore_revocation_state).
        previous_state = {
            'revoked': certificate.revoked,
            'revoked_at': certificate.revoked_at,
            'revoke_reason': certificate.revoke_reason,
            'invalidity_at': certificate.invalidity_at,
        }

        certificate.revoked = True
        certificate.revoked_at = utc_now()
        certificate.revoke_reason = reason
        if invalidity_at is not None:
            certificate.invalidity_at = invalidity_at

        # Flush so the in-memory changes are visible to the RevokedSerial
        # query below, but do NOT commit yet — the certificate revocation and
        # the RevokedSerial record must be persisted atomically so a worker
        # can never observe a revoked cert without its persistent record.
        try:
            db.session.flush()
        except Exception as _flush_err:
            db.session.rollback()
            logger.error(
                f"Flush failed in revoke_certificate for cert {cert_id}: {_flush_err}",
                exc_info=True,
            )
            raise

        # Persist a revocation record that survives certificate deletion.
        # CRL generation and OCSP both consult this table as a fallback when
        # the certificate row is gone (e.g. after renewal replaces the old cert).
        # Skip for certs without a local CA (e.g. MSCA-issued) — there is no
        # local CRL to carry the entry, and RevokedSerial.caref is NOT NULL.
        if not certificate.caref:
            logger.info(
                f"Skipping RevokedSerial insert for cert {cert_id} "
                f"(no local CA / caref is NULL)"
            )
        else:
            existing_rs = RevokedSerial.query.filter_by(
                caref=certificate.caref,
                serial_number=certificate.serial_number,
            ).first()
            if existing_rs:
                # Update the existing row so the CRL carries the latest
                # revoked_at/reason (e.g. hold → unhold → re-revoke with a
                # different reason). Skipping would leave the original
                # hold date/reason on the CRL forever.
                existing_rs.revoked_at = certificate.revoked_at
                existing_rs.revoke_reason = certificate.revoke_reason
                existing_rs.invalidity_at = certificate.invalidity_at
                existing_rs.valid_to = certificate.valid_to or (utc_now() + timedelta(days=365))
                existing_rs.certificate_id = certificate.id
            else:
                revoked_record = RevokedSerial(
                    caref=certificate.caref,
                    serial_number=certificate.serial_number,
                    revoked_at=certificate.revoked_at,
                    revoke_reason=certificate.revoke_reason,
                    invalidity_at=certificate.invalidity_at,
                    valid_to=certificate.valid_to or (utc_now() + timedelta(days=365)),
                    certificate_id=certificate.id,
                )
                db.session.add(revoked_record)

        # Single atomic commit — certificate revocation + RevokedSerial
        # either both persist or both roll back.
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            LifecycleMixin._restore_revocation_state(
                certificate, previous_state, cert_id)
            logger.error(
                f"Revocation failed for cert {cert_id}: unable to persist "
                f"revocation record: {_commit_err}",
                exc_info=True,
            )
            raise RuntimeError(
                f"Revocation failed for cert {cert_id}: unable to persist "
                f"revocation record: {_commit_err}"
            ) from _commit_err

        if certificate.caref:
            logger.info(
                f"RevokedSerial persisted for cert {cert_id} "
                f"(serial={certificate.serial_number})."
            )

        if not _suppress_events:
            # Audit log
            from services.audit_service import AuditService
            AuditService.log_certificate('cert_revoked', certificate, f'Revoked certificate: {certificate.descr} - Reason: {reason}')

            # Auto-generate CRL if CA has CDP enabled
            ca = CA.query.filter_by(refid=certificate.caref).first() if certificate.caref else None
            if ca and ca.cdp_enabled:
                from services.crl_service import CRLService
                try:
                    CRLService.generate_crl(ca.id, username=username)
                except Exception as e:
                    # Log error but don't fail revocation
                    AuditService.log_ca('crl_auto_generation_failed', ca, f'Failed to auto-generate CRL after revocation: {str(e)}', success=False)

            # RFC 6960 §2.2: revocation MUST take effect immediately for new
            # responses, regardless of which CertID hash algorithm was requested.
            if ca:
                OCSPService.invalidate_cached_responses(
                    certificate.serial_number, ca_id=ca.id)
            # A revoked delegated responder stops signing at once, and the
            # answers it signed so far stop being served (#347 review)
            for responder_ca_id in OCSPService.responder_cas_for_certificate(cert_id):
                OCSPService.invalidate_ca_cache(responder_ca_id)

            from services.webhook_service import emit_cert_revoked
            emit_cert_revoked(certificate.to_dict(), reason=reason, ca_refid=certificate.caref, actor=username)
        else:
            # Even in suppressed mode, invalidate OCSP cache so the old
            # serial is immediately reported as revoked.
            ca = CA.query.filter_by(refid=certificate.caref).first() if certificate.caref else None
            if ca:
                OCSPService.invalidate_cached_responses(
                    certificate.serial_number, ca_id=ca.id)

        return certificate

    @staticmethod
    def delete_certificate(cert_id: int, username: str = 'system', _suppress_events: bool = False) -> bool:
        """
        Delete a certificate

        Args:
            cert_id: Certificate ID
            username: User deleting
            _suppress_events: Skip audit log and webhook emit. Used by the
                renewal flow which emits a single `cert_renewed` event.

        Returns:
            True if deleted
        """
        certificate = db.session.get(Certificate, cert_id)
        if not certificate:
            return False

        # Snapshot for the webhook payload before the row is gone
        _cert_snapshot = certificate.to_dict()
        _cert_caref = certificate.caref

        # Clean up FK dependencies (ApprovalRequest.certificate_id has no cascade)
        try:
            from models import ApprovalRequest
            ApprovalRequest.query.filter_by(certificate_id=cert_id).delete()
        except Exception as e:
            logger.error(f"Failed to clean approval requests for cert {cert_id}: {e}")
            db.session.rollback()
            return False

        # Deploy bindings (#299): remove the cert's bindings and their delivery
        # history — DeployBinding.certificate_id is a real FK with no cascade.
        try:
            from models import DeployBinding, DeployDelivery
            binding_ids = [b.id for b in DeployBinding.query.filter_by(certificate_id=cert_id)]
            if binding_ids:
                DeployDelivery.query.filter(
                    DeployDelivery.binding_id.in_(binding_ids)).delete(synchronize_session=False)
                DeployBinding.query.filter(
                    DeployBinding.id.in_(binding_ids)).delete(synchronize_session=False)
        except Exception as e:
            logger.error(f"Failed to clean deploy bindings for cert {cert_id}: {e}")
            db.session.rollback()
            return False

        # Null out the certificate_id FK on RevokedSerial rows so the CRL/OCSP
        # query treats them as orphaned (the cert row is about to be deleted,
        # but the revocation data must persist).
        try:
            RevokedSerial.query.filter_by(certificate_id=cert_id).update(
                {RevokedSerial.certificate_id: None}
            )
        except Exception as e:
            logger.warning(f"Failed to null out RevokedSerial.certificate_id for cert {cert_id}: {e}")

        # Detach ACME order FKs (AcmeClientOrder.certificate_id,
        # AcmeClientOrder.source_certificate_id, AcmeOrder.certificate_id)
        # — these are real FKs to certificates.id with no cascade. Without
        # detaching, PostgreSQL raises IntegrityError on delete; SQLite leaves
        # dangling references.
        try:
            from models.acme_models import AcmeClientOrder, AcmeOrder
            AcmeClientOrder.query.filter_by(certificate_id=cert_id).update(
                {AcmeClientOrder.certificate_id: None}
            )
            AcmeClientOrder.query.filter_by(source_certificate_id=cert_id).update(
                {AcmeClientOrder.source_certificate_id: None}
            )
            AcmeOrder.query.filter_by(certificate_id=cert_id).update(
                {AcmeOrder.certificate_id: None}
            )
        except Exception as e:
            logger.warning(f"Failed to detach ACME order FKs for cert {cert_id}: {e}")

        # Delete files (cleanup old UUID names first, then new names)
        cleanup_old_files(certificate=certificate)
        cert_path = cert_cert_path(certificate)
        csr_path = cert_csr_path(certificate)
        key_path = cert_key_path(certificate)

        for path in [cert_path, csr_path, key_path]:
            if path.exists():
                path.unlink()

        # Audit log
        if not _suppress_events:
            from services.audit_service import AuditService
            AuditService.log_certificate('cert_deleted', certificate, f'Deleted certificate: {certificate.descr}')

        # A responder binding must not outlive its certificate: the next
        # certificate to reuse the id would become the responder unseen
        # (self-review of #347)
        from services.ocsp_service import OCSPService
        for bound_ca_id in OCSPService.responder_cas_for_certificate(cert_id):
            SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{bound_ca_id}').delete()
            OCSPService.invalidate_ca_cache(bound_ca_id)

        # Delete from database
        try:
            db.session.delete(certificate)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete certificate {cert_id}: {e}")
            return False

        if not _suppress_events:
            from services.webhook_service import emit_cert_deleted
            emit_cert_deleted(_cert_snapshot, ca_refid=_cert_caref, actor=username)

        return True
