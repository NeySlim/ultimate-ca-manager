"""
CA CSR signing operations
"""
import base64
import json
import logging
import uuid
from typing import Tuple

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from models import CA, Certificate, db
from utils.ca_serial_counter import next_ca_serial
from models.certificate_template import CertificateTemplate
from services.audit_service import AuditService
from services.trust_store import TrustStoreService
from .helpers import get_ca_cert_pem

logger = logging.getLogger(__name__)


class CAOfflineError(Exception):
    """Raised when an operation is attempted on an offline CA."""
    pass


class AlreadySuperseded(Exception):
    """The certificate being renewed was superseded by a concurrent renewal."""


def _claim_superseded(row):
    """Archive every live row holding *row*'s certificate (same DER, under any CA: it is
    replaced everywhere); False when another renewal got there first. One row at a time
    in id order, so two concurrent claims never lock in opposite orders."""
    from sqlalchemy import update
    from sqlalchemy.orm.attributes import set_committed_value
    from services.cert.issued_lookup import _rows_holding
    held = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
    live = sorted(r.id for r in _rows_holding(held, Certificate.archived.isnot(True)))
    if row.id not in live:
        return False
    for row_id in live:
        result = db.session.execute(
            update(Certificate)
            .where(Certificate.id == row_id, Certificate.archived.isnot(True))
            .values(archived=True)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return False
    set_committed_value(row, 'archived', True)
    return True


class CASigningMixin:
    """CA CSR signing operations"""

    @staticmethod
    def _check_ca_offline(ca: CA) -> None:
        """Raise CAOfflineError if the CA cannot sign (offline, revoked or pending)."""
        if ca.offline:
            raise CAOfflineError(
                f"CA '{ca.descr}' is offline: {ca.offline_reason or 'no reason provided'}"
            )
        if ca.revoked_in_chain:
            raise CAOfflineError(f"CA '{ca.descr}' is revoked and can no longer sign")
        if ca.is_pending:
            raise CAOfflineError(
                f"CA '{ca.descr}' is awaiting its certificate and cannot sign"
            )

    @staticmethod
    def sign_csr_from_crypto(
        ca: CA,
        csr: x509.CertificateSigningRequest,
        validity_days: int = 365,
        source: str = 'manual',
        renewal_of: x509.Certificate = None,
        require_pop: bool = True,
        ms_certificate_template_oid: str = None,
        override_subject: x509.Name = None,
        override_san: list = None,
        requester_sid: str = None,
        cert_type: str = 'server_cert',
        extra_ekus: list = None,
        supersedes=None,
        policy_template_id: int = None,
        template_ekus: list = None,
        template_id: int = None,
        template_key_usage: list = None,
    ) -> Tuple[str, str]:
        """
        Sign a CSR (x509 object) using a CA.
        Bridge between EST/auto-renewal and TrustStoreService.sign_csr().

        Args:
            ca: CA model instance
            csr: x509 CertificateSigningRequest object
            validity_days: Certificate validity in days
            source: Origin of the request (est, auto-renewal, etc.)
            renewal_of: Certificate being renewed, if any — its names and
                EKUs are graced (renewal at par must not silently narrow
                what the device already has)
            require_pop: forwarded to TrustStoreService.sign_csr — see its
                docstring. Only WSTEP passes False.
            ms_certificate_template_oid: forwarded to TrustStoreService.sign_csr
                — see its docstring. Only WSTEP passes this.
            override_subject: forwarded to TrustStoreService.sign_csr — see
                its docstring. Only WSTEP's Kerberos binding passes this.
            override_san: forwarded to TrustStoreService.sign_csr — see its
                docstring. Only WSTEP's Kerberos binding passes this.
            requester_sid: forwarded to TrustStoreService.sign_csr — see its
                docstring. Only WSTEP's Kerberos binding passes this.
            cert_type: Signing profile for TrustStoreService.sign_csr —
                decides the EKU ceiling. EST passes 'device_cert'; WSTEP
                overrides this too for its own matched-template flow; the
                default keeps every other caller on the TLS profile. Recorded on
                the certificate's row.
            extra_ekus: forwarded to TrustStoreService.sign_csr — see its
                docstring. Only WSTEP passes this, for a matched template's
                own configured EKUs (e.g. Smartcard Logon) that a CSR-EKU
                cap keyed off cert_type could otherwise never let through.
            policy_template_id: template scoping the issuance policies (the
                WSTEP matched template), none for EST; its SAN types bind
                the request's names and its digest is the preferred one
                (``issuance_defaults.template_digest``).
            template_ekus: EKUs that replace the CSR's, as a bound template's
                do (WSTEP renewal); protocol-forbidden ones still dropped.
            template_id: template the certificate is issued under, recorded on
                its row (WSTEP: the one whose OID it carries).
            template_key_usage: Key Usage names that replace the CSR's, as a
                bound template's do (WSTEP, for a request that carries none).

        Returns:
            Tuple of (cert_pem_string, serial_number_string)
        """
        CASigningMixin._check_ca_offline(ca)

        # Convert CSR object to PEM bytes
        csr_pem = csr.public_bytes(serialization.Encoding.PEM)
        # RFC 9763: A is found before signing, so linking after it cannot fail
        from services.cert.related_pair import link_issued, record_request_key, requested_by_csr
        related_a = requested_by_csr(csr.public_bytes(serialization.Encoding.DER))

        # Load CA cert and key (local or HSM-backed)
        ca_cert_pem = get_ca_cert_pem(ca)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())

        from services.hsm.ca_key_loader import get_ca_signing_key
        ca_private_key = get_ca_signing_key(ca)

        # Resolve CDP/OCSP/AIA URLs
        cdp_urls = [url.replace('{ca_refid}', ca.url_ref) for url in ca.get_cdp_urls()] if ca.cdp_enabled else None
        ocsp_urls = ca.get_ocsp_urls() if ca.ocsp_enabled else None
        aia_ca_issuers_urls = [url.replace('{ca_refid}', ca.url_ref) for url in ca.get_aia_urls()] if ca.aia_ca_issuers_enabled else None
        cps_uri = ca.cps_uri if ca.cps_enabled and ca.cps_uri else None
        cps_oid = ca.cps_oid if cps_uri else None

        # The matched template (WSTEP) adds its custom extensions (#437)
        policy_template = (db.session.get(CertificateTemplate, policy_template_id)
                           if policy_template_id else None)
        from utils.custom_extensions import template_custom_extensions
        from utils.issuance_defaults import template_digest as _template_digest
        template_digest = _template_digest(policy_template, ca_private_key)

        # Sign via TrustStoreService
        cert_pem_bytes = TrustStoreService.sign_csr(
            csr_pem=csr_pem,
            ca_cert=ca_cert,
            ca_private_key=ca_private_key,
            validity_days=validity_days,
            digest=template_digest,
            cert_type=cert_type,
            cdp_urls=cdp_urls,
            ocsp_urls=ocsp_urls,
            aia_ca_issuers_urls=aia_ca_issuers_urls,
            cps_uri=cps_uri,
            cps_oid=cps_oid,
            renewal_of=renewal_of,
            require_pop=require_pop,
            ms_certificate_template_oid=ms_certificate_template_oid,
            override_subject=override_subject,
            override_san=override_san,
            requester_sid=requester_sid,
            extra_ekus=extra_ekus,
            template_ext={k: list(v) for k, v in (('extended_key_usage', template_ekus),
                                                  ('key_usage', template_key_usage)) if v} or None,
            policy_scope={'ca_id': ca.id, 'template_id': policy_template_id,
                          'digest_explicit': False},
            san_template=policy_template,
            custom_extensions=template_custom_extensions(policy_template),
        )

        # Extract serial number
        cert_obj = x509.load_pem_x509_certificate(
            cert_pem_bytes if isinstance(cert_pem_bytes, bytes) else cert_pem_bytes.encode(),
            default_backend()
        )
        serial = format(cert_obj.serial_number, 'X')  # legacy hex form, kept for return tuple
        serial_decimal = str(cert_obj.serial_number)  # canonical DB form

        # Store certificate in database
        cert_pem_str = cert_pem_bytes.decode('utf-8') if isinstance(cert_pem_bytes, bytes) else cert_pem_bytes

        # Extract CN from the issued certificate's own subject, not the
        # CSR's -- for WSTEP's Kerberos binding, override_subject can mean
        # the two differ entirely (a naked CSR issued with a server-derived
        # subject), and the issued cert's subject is what's actually true.
        # [-1] (the last/most-specific CN), not [0]: a directory-path
        # subject like an AD-derived user's has more than one CN RDN
        # (``CN=Roy Hagland,CN=Users,DC=hagland,DC=domain``), and in the
        # root-to-leaf DER order x509.Name encodes, the person's own name
        # is the last one, not the container ("Users") that happens first.
        cn = ''
        try:
            cn = cert_obj.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[-1].value
        except (IndexError, Exception):
            cn = cert_obj.subject.rfc4514_string()

        cert_pem_raw = cert_pem_bytes if isinstance(cert_pem_bytes, bytes) else cert_pem_bytes.encode()

        # Extract SANs
        from utils.upn_san import extract_upns_from_san_list
        san_dns, san_ip, san_email, san_upn = [], [], [], []
        try:
            san_ext = cert_obj.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            san_dns = list(san_ext.value.get_values_for_type(x509.DNSName))
            san_ip = [str(n) for n in san_ext.value.get_values_for_type(x509.IPAddress)]
            san_email = list(san_ext.value.get_values_for_type(x509.RFC822Name))
            san_upn = extract_upns_from_san_list(list(san_ext.value))
        except x509.ExtensionNotFound:
            pass

        not_before = cert_obj.not_valid_before_utc if hasattr(cert_obj, 'not_valid_before_utc') else cert_obj.not_valid_before
        not_after = cert_obj.not_valid_after_utc if hasattr(cert_obj, 'not_valid_after_utc') else cert_obj.not_valid_after

        new_cert = Certificate(
            refid=str(uuid.uuid4())[:8],
            descr=cn,
            caref=ca.refid,
            crt=base64.b64encode(cert_pem_raw).decode(),
            csr=base64.b64encode(csr_pem).decode(),
            cert_type=cert_type,
            subject=cert_obj.subject.rfc4514_string(),
            subject_cn=cn,
            issuer=cert_obj.issuer.rfc4514_string(),
            serial_number=serial_decimal,
            # aki/ski come from the crt listener, in the form CA lookups match
            valid_from=not_before,
            valid_to=not_after,
            san_dns=json.dumps(san_dns) if san_dns else None,
            san_ip=json.dumps(san_ip) if san_ip else None,
            san_email=json.dumps(san_email) if san_email else None,
            san_upn=json.dumps(san_upn) if san_upn else None,
            source=source,
            template_id=template_id,
        )
        db.session.add(new_cert)

        # Increment CA serial
        next_ca_serial(ca)
        try:
            db.session.flush()
            # The renewed row is archived in the commit that stores its successor,
            # compare-and-set: of two concurrent renewals, only one stores a certificate
            if supersedes is not None and not _claim_superseded(supersedes):
                db.session.rollback()
                raise AlreadySuperseded('the renewed certificate is already superseded')
            link_issued(new_cert, cert_obj, related_a)
            # RFC 9763: the request binds to this key B in the commit that stores B
            record_request_key(csr.public_bytes(serialization.Encoding.DER), related_a)
            db.session.commit()
        except AlreadySuperseded:
            raise
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Storing the certificate signed via {source} failed: {_commit_err}", exc_info=True)
            raise

        logger.info(f"Signed CSR via {source}: CN={cn}, serial={serial}, CA={ca.descr}")

        # Renewal flows pass source like '<orig>-renewal'; everything else
        # (EST enrollment, etc.) is a fresh issuance.
        from services.webhook_service import emit_cert_renewed, emit_cert_issued
        if renewal_of is not None or 'renewal' in (source or ''):
            emit_cert_renewed(new_cert.to_dict(), ca_refid=ca.refid)
        else:
            emit_cert_issued(new_cert.to_dict(), ca_refid=ca.refid)

        return cert_pem_str, serial
