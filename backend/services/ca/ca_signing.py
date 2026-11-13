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
from utils.ca_serial_counter import (
    log_commit_failure, next_ca_serial, retry_on_serial_collision,
    rollback_unless_serial_collision)
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


class SubjectTaken(Exception):
    """RFC 5280 §4.1.2.6: the subject is already carried by a certificate of the CA issued to
    another entity; *serial* is that certificate's."""

    def __init__(self, subject, serial):
        super().__init__(f'the subject {subject} is already carried by certificate serial {serial}')
        self.subject, self.serial = subject, serial


def _subject_holder(ca, cert, requester_sid, own_id):
    """The serial of a certificate of *ca*, whatever its status, whose subject equals *cert*'s
    (RFC 5280 §7.1) and whose SID extension does not name *requester_sid*; else None."""
    from services.trust_store.csr_operations_mixin import ad_security_extension_sid
    from utils.dn_match import name_key, same_name
    rows = (db.session.query(Certificate.crt, Certificate.serial_number)
            .filter(Certificate.caref == ca.refid, Certificate.subject_key == name_key(cert.subject),
                    Certificate.id != own_id, Certificate.crt.isnot(None))
            .order_by(Certificate.id))
    for crt, serial in rows:
        try:
            held = x509.load_pem_x509_certificate(base64.b64decode(crt))
        except Exception:
            continue
        if not same_name(held.subject, cert.subject):
            continue
        # Without the extension nothing proves the same entity: never a yes without proof
        if requester_sid is None or ad_security_extension_sid(held) != requester_sid:
            return serial
    return None


def _claim_superseded(row, presented=None, successor=None):
    """Archive every live row holding *presented*, the certificate the client renews (by
    default *row*'s), same DER under any CA: it is replaced everywhere. False when another
    renewal got there first. One row at a time in id order, so two claims never cross.
    With *successor*, the archived rows' bindings move to it in the same transaction."""
    from sqlalchemy import update
    from sqlalchemy.orm.attributes import set_committed_value
    from services.cert.issued_lookup import _rows_holding
    from utils.serial_format import serial_variants
    held = presented if presented is not None else \
        x509.load_pem_x509_certificate(base64.b64decode(row.crt))
    live = sorted(r.id for r in _rows_holding(held, Certificate.archived.isnot(True)))
    if row.id not in live:
        return False
    for row_id in live:
        # Re-checked after any lock wait: a row renewed in place meanwhile holds another serial
        result = db.session.execute(
            update(Certificate)
            .where(Certificate.id == row_id, Certificate.archived.isnot(True),
                   Certificate.serial_number.in_(serial_variants(held.serial_number)))
            .values(archived=True)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            return False
    set_committed_value(row, 'archived', True)
    if successor is not None:
        _bindings_follow(live, successor)
    return True


def _pushes_key(binding):
    """An SSH binding with a key_path, or an HTTP binding whose target template names
    key_pem (same predicate as DeployService.validate_http_binding)."""
    if binding.key_path:
        return True
    target = binding.target
    if target is None or not target.is_http:
        return False
    from services.deploy import http as deploy_http
    try:
        names = deploy_http.template_names(target)
    except ValueError:
        return True  # an unreadable template must not move a binding or abort the renewal
    return 'key_pem' in names


def _bindings_follow(old_ids, successor):
    """Deploy bindings and the HTTPS listener binding of the archived rows *old_ids*, and
    those left behind waiting for one of them, now name *successor*; a target keeps one
    binding per certificate (lowest id wins). A binding that pushes the key, and the
    HTTPS binding, follow only a successor holding one, and otherwise wait for it."""
    from sqlalchemy import or_
    from models import DeployBinding, SystemConfig
    from services import binding_attention
    from services.https_binding import BOUND_REFID_KEY
    if successor.id is None:
        db.session.flush()
    keyed = successor.has_private_key
    taken = {t for (t,) in db.session.query(DeployBinding.target_id)
             .filter(DeployBinding.certificate_id == successor.id)}
    stayed = []
    for binding in (DeployBinding.query.filter(or_(
            DeployBinding.certificate_id.in_(old_ids),
            DeployBinding.attention_successor_id.in_(old_ids)))
            .order_by(DeployBinding.id)):
        if not keyed and _pushes_key(binding):
            stayed.append(f'deploy binding {binding.id}')
            binding_attention.mark_deploy(binding, successor)
            continue
        binding_attention.clear(binding)
        if binding.target_id not in taken:
            binding.certificate_id = successor.id
            taken.add(binding.target_id)
    refids = [r for (r,) in db.session.query(Certificate.refid).filter(Certificate.id.in_(old_ids))]
    https = SystemConfig.query.filter(SystemConfig.key == BOUND_REFID_KEY).first()
    awaited = binding_attention.https_left_behind_for() in refids
    if https is None or not (https.value in refids or awaited):
        https = None
    if https is not None and keyed:
        https.value = successor.refid
        if awaited:
            binding_attention.clear_https()
    elif https is not None:
        stayed.append('the HTTPS listener binding')
        binding_attention.mark_https(successor)
    if stayed:
        logger.warning(
            f"Renewed certificate {successor.refid} has no private key in UCM: "
            f"{', '.join(stayed)} {'stays' if len(stayed) == 1 else 'stay'} on the previous certificate")


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
    @retry_on_serial_collision
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
        on_stored=None,
        windows_profile_id: int = None,
        unique_subject: bool = False,
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
                docstring. WSTEP passes it at Kerberos issuance, WSTEP and EST
                at renewal.
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
            on_stored: called with the new row once flushed, so what it
                writes is committed with the certificate (an approval's link).
            windows_profile_id: the Windows enrollment profile a WSTEP issuance
                or renewal served, recorded on the row; None for other protocols.
            unique_subject: raise SubjectTaken when another entity's certificate of
                the CA carries the issued subject (``_subject_holder``); WSTEP passes
                it for a subject built by a common name pattern.

        Returns:
            Tuple of (cert_pem_string, serial_number_string)
        """
        CASigningMixin._check_ca_offline(ca)

        # Convert CSR object to PEM bytes
        csr_pem = csr.public_bytes(serialization.Encoding.PEM)
        # RFC 9763: A is found before signing; linking refuses only an A renewed since
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
            windows_profile_id=windows_profile_id,
        )
        db.session.add(new_cert)

        try:
            db.session.flush()
            # A (RFC 9763) is locked before the renewed row: an in-place renewal of A
            # locks A, then the rows it unlinks, this one among them
            if related_a is not None:
                db.session.query(Certificate.id).filter(
                    Certificate.id == related_a[0].id).with_for_update().first()
            # The renewed row is archived in the commit that stores its successor,
            # compare-and-set: of two concurrent renewals, only one stores a certificate
            if supersedes is not None and not _claim_superseded(supersedes, renewal_of, new_cert):
                db.session.rollback()
                raise AlreadySuperseded('the renewed certificate is already superseded')
            link_issued(new_cert, cert_obj, related_a)
            # RFC 9763: the request binds to this key B in the commit that stores B
            record_request_key(csr.public_bytes(serialization.Encoding.DER), related_a)
            if on_stored is not None:
                on_stored(new_cert)
            # Every row written (A's link included) is locked before the CA row, last
            db.session.flush()
            next_ca_serial(ca)
            # Read once the CA row is locked (PostgreSQL) or the database write lock held
            # (SQLite, since the flush): a concurrent issuance under this CA commits before or after
            if unique_subject:
                holder = _subject_holder(ca, cert_obj, requester_sid, new_cert.id)
                if holder is not None:
                    db.session.rollback()
                    raise SubjectTaken(cert_obj.subject.rfc4514_string(), holder)
            db.session.commit()
        except (AlreadySuperseded, SubjectTaken):
            raise
        except Exception as _commit_err:
            rollback_unless_serial_collision(_commit_err)
            log_commit_failure(logger, f"Storing the certificate signed via {source} failed", _commit_err)
            raise

        logger.info(f"Signed CSR via {source}: CN={cn}, serial={serial}, CA={ca.descr}")

        # Renewal flows pass source like '<orig>-renewal'; everything else
        # (EST enrollment, etc.) is a fresh issuance.
        from services.webhook_service import emit_cert_renewed, emit_cert_issued
        if renewal_of is not None or 'renewal' in (source or ''):
            emit_cert_renewed(new_cert.to_dict(), ca_refid=ca.refid)
        else:
            emit_cert_issued(new_cert.to_dict(), ca_refid=ca.refid)
        from services.binding_attention import emit_pending
        emit_pending()

        return cert_pem_str, serial
