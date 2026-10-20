"""Certificate lifecycle mixin — create, revoke, delete, list, get"""
import base64
import uuid
import json
import logging
from datetime import timedelta
from types import SimpleNamespace
from typing import Dict, List, Optional

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from models import db, CA, CertificateTemplate, Certificate, SystemConfig
from utils.validity import DEFAULT_CERTIFICATE_VALIDITY_DAYS
from utils.key_type import issue_key_type_from_template
from services.file_regen_service import mirror_private_key
from services.ocsp_service import OCSPService
from services.trust_store import TrustStoreService
from utils.ct_client import embed_scts_in_certificate
from utils.file_naming import cert_cert_path, cert_key_path, cert_csr_path, cleanup_old_files
from utils.datetime_utils import utc_now, to_naive_utc

logger = logging.getLogger(__name__)

from security.encryption import decrypt_private_key, encrypt_private_key

_HOLD_REASONS = ('certificateHold', 'certificate_hold')
_REVOCATION_FIELDS = ('revoked', 'revoked_at', 'revoke_reason', 'invalidity_at')


def _request_user_id(username):
    """Id of the request's user when it is the one named, else None."""
    from flask import g, has_request_context
    user = getattr(g, 'current_user', None) if has_request_context() else None
    if user is not None and getattr(user, 'username', None) == username:
        return getattr(user, 'id', None)
    return None


def _audit_actor(username):
    """None inside an operator's request (the ledger names that operator), else ``username``."""
    from flask import g, has_request_context
    if has_request_context() and getattr(g, 'current_user', None):
        return None
    return username


def _restore_revocation_state(cert_id, previous):
    """Write back the revocation columns as they were before a failed commit."""
    try:
        certificate = db.session.get(Certificate, cert_id)
        if certificate is None:
            return
        for field, value in previous.items():
            setattr(certificate, field, value)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Certificate {cert_id}: previous revocation state not restored: {e}")


class LifecycleMixin:

    @staticmethod
    def create_certificate(
        descr: str,
        caref: str,
        dn: Dict[str, str],
        cert_type: str = 'server_cert',
        key_type: Optional[str] = None,
        validity_days: Optional[int] = None,
        digest: Optional[str] = None,
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
        # Apply template if provided.
        #
        # These three used to default to a real value and then treat that
        # value as "the caller said nothing" -- `validity_days != 397`,
        # `key_type != '2048'`, `digest != 'sha256'`. So asking for exactly
        # the published TLS maximum, or for RSA-2048, or for SHA-256, was
        # indistinguishable from asking for nothing and was silently
        # replaced by the template's value. `None` is the only thing that
        # can mean "nothing said" without also being an answer.
        template = None
        if template_id:
            template = db.session.get(CertificateTemplate, template_id)
            if template:
                if key_type is None:
                    key_type = (issue_key_type_from_template(template.key_type)
                                or key_type)
                if validity_days is None:
                    validity_days = template.validity_days or validity_days
                if digest is None:
                    digest = template.digest or digest
                from services.template_service import bucket_san_refusal
                san_refusal = bucket_san_refusal(template, {
                    'san_dns': san_dns, 'san_ip': san_ip, 'san_uri': san_uri, 'san_email': san_email})
                if san_refusal:
                    from services.policy_service import PolicyViolation
                    raise PolicyViolation(san_refusal)

        if key_type is None:
            key_type = '2048'
        if validity_days is None:
            validity_days = DEFAULT_CERTIFICATE_VALIDITY_DAYS
        # A digest asked for (or the template's) is checked; the default yields
        digest_explicit = digest is not None
        if digest is None:
            digest = 'sha256'

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
        from fips_mode import FipsRestricted
        try:
            ca_private_key = get_ca_signing_key(ca)
        except FipsRestricted:
            raise
        except Exception as e:
            raise ValueError(f"Failed to load CA signing key: {e}")

        # Issuance policies (#397): key type and signature hash
        from services.policy_service import PolicyEvaluationService, PolicyViolation
        from services.template_service import _normalize_key_type_label
        sign_hash, violations = PolicyEvaluationService.checked_signing_hash(
            PolicyEvaluationService.applicable_policies(
                ca.id, template_id, (dn or {}).get('CN'), san_dns),
            ca_private_key, digest, explicit=digest_explicit,
            context={'operation': 'issuance', 'subject': (dn or {}).get('CN'), 'ca_id': ca.id},
            key_type=_normalize_key_type_label(key_type) or key_type)
        if violations:
            raise PolicyViolation('Policy violation: ' + '; '.join(violations))
        if sign_hash is not None:
            digest = sign_hash.name

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
            logger.error(f"Certificate creation not committed: {_commit_err}", exc_info=True)
            raise

        # Audit log
        from services.audit_service import AuditService
        AuditService.log_certificate('cert_created', certificate, f'Created certificate: {descr}')

        # Persist the SCTs that apply_ct_policy embedded or submitted.
        try:
            scts_to_store = embedded_scts
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
    def revoke_certificate(
        cert_id: int,
        reason: str = 'unspecified',
        username: str = 'system',
        invalidity_at=None,
    ) -> Certificate:
        """
        Revoke a certificate

        Args:
            cert_id: Certificate ID
            reason: Revocation reason
            username: User revoking
            invalidity_at: Optional RFC 5280 §5.3.2 invalidityDate (datetime)

        Returns:
            Updated certificate
        """
        from models import RevokedSerial
        from services.approval_gate import resolve_moot_requests, request_snapshots

        certificate = db.session.get(Certificate, cert_id)
        if not certificate:
            raise ValueError("Certificate not found")
        if certificate.revoked:
            raise ValueError("Certificate already revoked")

        ca = CA.query.filter_by(refid=certificate.caref).first() if certificate.caref else None
        is_hold = reason in _HOLD_REASONS
        previous = {field: getattr(certificate, field) for field in _REVOCATION_FIELDS}
        now = utc_now()
        rejected_renewals = []
        try:
            certificate.revoked = True
            certificate.revoked_at = now
            certificate.revoke_reason = reason
            if invalidity_at is not None:
                certificate.invalidity_at = invalidity_at

            # A Microsoft certificate has no caref: nothing for a UCM CRL to publish
            if ca is not None:
                valid_to = to_naive_utc(certificate.valid_to) or now + timedelta(days=365)
                record = RevokedSerial.query.filter_by(
                    caref=certificate.caref, serial_number=certificate.serial_number).first()
                if record is None:
                    record = RevokedSerial(caref=certificate.caref,
                                           serial_number=certificate.serial_number)
                    db.session.add(record)
                record.revoked_at = now
                record.revoke_reason = reason
                record.invalidity_at = certificate.invalidity_at
                record.valid_to = valid_to
                record.certificate_id = certificate.id
            elif certificate.caref:
                logger.warning("Certificate %s: CA %s not found, no revocation record written",
                               cert_id, certificate.caref)

            # A hold is temporary: the requests about the certificate stay open
            if not is_hold:
                rejected_renewals = resolve_moot_requests(
                    'renewal', 'certificate_id', certificate.id, outcome='rejected',
                    username=username, user_id=_request_user_id(username),
                    reason='Certificate revoked', commit=False)
                resolve_moot_requests(
                    'revocation', 'certificate_id', certificate.id, outcome='approved',
                    username=username, user_id=_request_user_id(username),
                    certificate_id=certificate.id, reason='Revoked directly', commit=False)
            db.session.flush()
        except Exception:
            db.session.rollback()
            logger.error("Revocation of certificate %s not staged", cert_id, exc_info=True)
            raise
        rejected_snapshots = request_snapshots(rejected_renewals)

        try:
            db.session.commit()
        except Exception as commit_err:
            db.session.rollback()
            _restore_revocation_state(cert_id, previous)
            logger.error(f"Revocation failed for cert {cert_id}: {commit_err}", exc_info=True)
            raise RuntimeError(
                f"Revocation failed for cert {cert_id}: unable to persist revocation "
                f"record: {commit_err}") from commit_err

        # Snapshot before any audit or emit: their commits expire the instance
        cert_dict = certificate.to_dict()
        ca_id = ca.id if ca is not None else None
        name = certificate.descr or certificate.subject or f'Cert #{cert_id}'
        serial = certificate.serial_number

        from services.audit_service import AuditService
        from services.approval_gate import record_cancellations, notify_rejected
        AuditService.log_certificate(
            'cert_revoked', certificate, f'Revoked certificate: {name} - Reason: {reason}',
            username=_audit_actor(username))
        record_cancellations()

        if ca is not None and ca.cdp_enabled:
            try:
                from services.crl_service import CRLService
                CRLService.generate_crl(ca_id, username=username)
            except Exception as e:
                logger.warning(f"CRL of CA {ca_id} not regenerated after revoking cert {cert_id}: {e}")
                AuditService.log_ca(
                    'crl_auto_generation_failed', ca,
                    f'Failed to auto-generate CRL after revoking certificate {name}: {e}',
                    success=False)

        if serial:
            OCSPService.invalidate_cached_responses(serial, ca_id=ca_id)
        # A revoked delegated responder must stop vouching for its CA's answers
        for responder_ca_id in OCSPService.responder_cas_for_certificate(cert_id):
            OCSPService.invalidate_ca_cache(responder_ca_id)

        from services.webhook_service import emit_cert_revoked
        emit_cert_revoked(cert_dict, reason=reason, ca_refid=cert_dict.get('caref'), actor=username)
        notify_rejected(rejected_snapshots, reason='Certificate revoked', actor=username)

        return db.session.get(Certificate, cert_id)

    @staticmethod
    def delete_certificate(cert_id: int, username: str = 'system') -> bool:
        """
        Delete a certificate

        Args:
            cert_id: Certificate ID
            username: User deleting

        Returns:
            True if deleted
        """
        from models import RevokedSerial, DeployBinding, DeployDelivery
        from models.acme_models import AcmeOrder, AcmeClientOrder
        from models.msca import MSCARequest
        from models.policy import ApprovalRequest
        from services.approval_gate import resolve_moot_requests, request_snapshots
        from services.audit_service import AuditService

        certificate = db.session.get(Certificate, cert_id)
        if not certificate:
            return False

        snapshot = certificate.to_dict()
        name = certificate.descr or certificate.subject or f'Cert #{cert_id}'
        ca_refid = certificate.caref
        actor_id = _request_user_id(username)

        # Approvals and deploy bindings go in the same transaction as the row
        try:
            closed_csr = resolve_moot_requests(
                'csr', 'csr_id', cert_id, outcome='rejected', username=username,
                user_id=actor_id, reason='Request deleted', commit=False)
            closed_cert = []
            for request_type in ('renewal', 'revocation'):
                closed_cert += resolve_moot_requests(
                    request_type, 'certificate_id', cert_id, outcome='rejected',
                    username=username, user_id=actor_id, reason='Certificate deleted',
                    commit=False)
            csr_snapshots = request_snapshots(closed_csr)
            cert_snapshots = request_snapshots(closed_cert)
            ApprovalRequest.query.filter(ApprovalRequest.certificate_id == cert_id).delete(
                synchronize_session='fetch')

            binding_ids = [row.id for row in DeployBinding.query.filter_by(certificate_id=cert_id)]
            if binding_ids:
                DeployDelivery.query.filter(
                    DeployDelivery.binding_id.in_(binding_ids),
                    DeployDelivery.binding_type == DeployDelivery.BINDING_CERTIFICATE,
                ).delete(synchronize_session='fetch')
                DeployBinding.query.filter(DeployBinding.id.in_(binding_ids)).delete(
                    synchronize_session='fetch')
        except Exception as e:
            db.session.rollback()
            logger.error(f"Certificate {cert_id} not deleted: detaching its requests failed: {e}",
                         exc_info=True)
            return False

        # The revocation record outlives the certificate: unlinked, never cascaded
        try:
            RevokedSerial.query.filter(RevokedSerial.certificate_id == cert_id).update(
                {RevokedSerial.certificate_id: None}, synchronize_session='fetch')
        except Exception as e:
            logger.error(f"Certificate {cert_id}: revocation records not unlinked: {e}")

        # PostgreSQL refuses the delete while an ACME order points at the row
        try:
            AcmeClientOrder.query.filter(AcmeClientOrder.certificate_id == cert_id).update(
                {AcmeClientOrder.certificate_id: None}, synchronize_session='fetch')
            AcmeClientOrder.query.filter(AcmeClientOrder.source_certificate_id == cert_id).update(
                {AcmeClientOrder.source_certificate_id: None}, synchronize_session='fetch')
            AcmeOrder.query.filter(AcmeOrder.certificate_id == cert_id).update(
                {AcmeOrder.certificate_id: None}, synchronize_session='fetch')
        except Exception as e:
            logger.error(f"Certificate {cert_id}: ACME order references not cleared: {e}")

        # Same for the Microsoft CA requests that name it as CSR or certificate
        try:
            MSCARequest.query.filter(MSCARequest.cert_id == cert_id).update(
                {MSCARequest.cert_id: None}, synchronize_session='fetch')
            MSCARequest.query.filter(MSCARequest.csr_id == cert_id).update(
                {MSCARequest.csr_id: None}, synchronize_session='fetch')
        except Exception as e:
            logger.error(f"Certificate {cert_id}: Microsoft CA request references not cleared: {e}")

        # The disk is touched only once the row is gone: a failed commit keeps both
        file_paths = (cert_cert_path(certificate), cert_csr_path(certificate),
                      cert_key_path(certificate))
        legacy_files = SimpleNamespace(refid=certificate.refid)

        responder_cas = OCSPService.responder_cas_for_certificate(cert_id)
        try:
            for responder_ca_id in responder_cas:
                SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{responder_ca_id}').delete(
                    synchronize_session='fetch')
            db.session.delete(certificate)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete certificate {cert_id}: {e}", exc_info=True)
            # The exception (often SQL) stays in the log, never in the ledger
            AuditService.log_action(
                action='cert_deleted', resource_type='certificate', resource_id=str(cert_id),
                resource_name=name,
                details=f'Failed to delete certificate {name}: the database refused the deletion',
                success=False, username=_audit_actor(username))
            return False

        try:
            cleanup_old_files(certificate=legacy_files)
            for path in file_paths:
                if path.exists():
                    path.unlink()
        except Exception as e:
            logger.error(f"Certificate {cert_id}: files not removed: {e}")

        AuditService.log_action(
            action='cert_deleted', resource_type='certificate', resource_id=str(cert_id),
            resource_name=name, details=f'Deleted certificate: {name}', success=True,
            username=_audit_actor(username))
        for responder_ca_id in responder_cas:
            OCSPService.invalidate_ca_cache(responder_ca_id)

        from services.webhook_service import emit_cert_deleted
        from services.approval_gate import notify_rejected
        emit_cert_deleted(snapshot, ca_refid=ca_refid, actor=username)
        notify_rejected(csr_snapshots, reason='Request deleted', actor=username)
        notify_rejected(cert_snapshots, reason='Certificate deleted', actor=username)
        return True
