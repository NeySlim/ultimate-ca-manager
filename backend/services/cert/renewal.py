"""In-place renewal of a certificate whose private key the server holds.

One routine serves the renew route, the bulk route, the scheduler and the
execution of an approved renewal: the row keeps its id and refid, gets a new
serial, and the serial it replaces is recorded as superseded in the same
commit. A device-held key renews through its enrollment protocol.
"""
import json
import logging
from base64 import b64decode, b64encode
from datetime import timedelta

import cryptography.x509 as x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtensionOID, NameOID
from sqlalchemy.exc import InvalidRequestError, SQLAlchemyError

from models import db, CA, Certificate, RevokedSerial, SystemConfig
from security.encryption import encrypt_private_key
from services.file_regen_service import mirror_private_key
from utils.key_codec import eddsa_key_name, load_pem_bytes, private_key_to_pem
from utils import key_algorithms
from utils.key_algorithms import (
    family_for_public_key,
    generate_ec,
    generate_rsa,
    key_algo_for_public_key,
    label_for_public_key,
)
from utils.key_type import validate_enrollment_public_key
import fips_mode
from fips_mode import FipsRestricted
from utils.eku_validation import add_ocsp_nocheck_if_responder
from utils.validity import DEFAULT_CERTIFICATE_VALIDITY_DAYS, MAX_VALIDITY_DAYS as MAX_RENEWAL_DAYS
from utils.x509_aki import authority_key_identifier_from_issuer
from utils.ca_pointer_extensions import add_ca_pointer_extensions
from utils.qc_statements import carried_policy_oids, template_policy_oids
from utils.leaf_key_usage import constrain_builder_key_usage
from utils.spki_digest import certificate_key_sha256
from utils.datetime_utils import cert_not_before, utc_isoformat, utc_now
from utils.serial_format import canonical_serial
from utils.ca_signing_window import IssuerWindowError, check_issuer_window, clamp_not_after
from utils.db_transaction import commit_or_rollback
from utils.ca_serial_counter import next_ca_serial
from utils.file_naming import cert_cert_path, cert_key_path
from utils.upn_san import extract_upns_from_san_list
from utils import notices as notices_mod
from utils.signing_hash import rsa_padding_for
from utils.related_cert import RELATED_CERT_EXTENSION_OID

from utils.issuance_defaults import log_renewal_digest, renewal_digest

logger = logging.getLogger(__name__)


_SCT_LIST_OID = x509.ObjectIdentifier('1.3.6.1.4.1.11129.2.4.2')
_ISSUER_OWNED_EXTENSION_OIDS = frozenset({
    ExtensionOID.AUTHORITY_KEY_IDENTIFIER,
    ExtensionOID.SUBJECT_KEY_IDENTIFIER,
    ExtensionOID.CRL_DISTRIBUTION_POINTS,
    ExtensionOID.AUTHORITY_INFORMATION_ACCESS,
    ExtensionOID.CERTIFICATE_POLICIES,
    _SCT_LIST_OID,
    RELATED_CERT_EXTENSION_OID,  # recomputed: A's hash changes when A is renewed
})

# How long the CRL keeps a superseded serial whose expiry is unknown
_SUPERSEDED_FALLBACK = timedelta(days=365)


# ``known_serial`` default: the caller passes nothing, the instance's own
# serial is the reference (None is a real value: a row that gained a serial
# meanwhile was renewed)
SERIAL_UNSET = object()


def _renewed_meanwhile_message(trigger: str) -> str:
    """The 409 message: the retry advice is for an operator, not a batch."""
    if trigger == 'auto':
        return 'Certificate was renewed by another request'
    return 'Certificate was renewed by another request; reload it and retry'


class RenewalError(Exception):
    """A renewal refused or failed: ``status`` is the HTTP code to answer,
    ``problem_type`` the FIPS problem type when FIPS mode refused it."""

    def __init__(self, message: str, status: int = 400, problem_type=None):
        super().__init__(message)
        self.message = str(message)
        self.status = int(status)
        self.problem_type = problem_type

    def __str__(self) -> str:
        return self.message

    @classmethod
    def from_fips(cls, exc: FipsRestricted) -> 'RenewalError':
        return cls(str(exc), 400, problem_type=fips_mode.PROBLEM_TYPE)


def resolve_issuing_ca(cert: Certificate) -> 'CA | None':
    """Find the CA that signed ``cert``: by refid, else by signature.

    Names alone used to decide (subject, then the issuer's Common Name
    among every CA): a homonymous CA after a rotation, or a local CA merely
    sharing the CN of an external issuer, re-signed the certificate. The
    CAs carrying the issuer's name are tried first, then every other, and
    only the one whose key verifies the certificate's signature qualifies.
    """
    if cert.caref:
        by_refid = CA.query.filter_by(refid=cert.caref).first()
        if by_refid is not None:
            return by_refid
    if not cert.crt:
        return
    try:
        leaf = x509.load_pem_x509_certificate(b64decode(cert.crt))
    except Exception:
        return
    from utils.cert_issuer import authority_key_identifier_hex, certificate_signed_by, self_signed_first
    named = self_signed_first(CA.query.filter(CA.subject == cert.issuer).order_by(CA.id).all()) if cert.issuer else []
    others = self_signed_first([c for c in CA.query.order_by(CA.id).all() if c not in named])
    leaf_aki = authority_key_identifier_hex(leaf)
    verified = []
    for candidate in named + others:
        if not candidate.crt:
            continue
        try:
            ca_cert = x509.load_pem_x509_certificate(b64decode(candidate.crt))
            if certificate_signed_by(leaf, ca_cert):
                verified.append((candidate, ca_cert))
        except Exception:
            continue
    if not verified:
        return
    # Several CA records for one key (a cross-signed or re-issued CA): the
    # one whose SKI the certificate names as its AKI is the real issuer
    if leaf_aki:
        for candidate, ca_cert in verified:
            try:
                ski = ca_cert.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_KEY_IDENTIFIER).value.key_identifier
            except x509.ExtensionNotFound:  # without its SKI a CA cannot be the one the AKI names
                continue
            if ski.hex(':').upper() == str(leaf_aki).upper():
                return candidate
    return verified[0][0]


def check_renewable(cert: Certificate) -> None:
    """Raise :class:`RenewalError` when ``cert`` cannot be renewed at all
    (no certificate, revoked, issued by a Microsoft CA, key not held by the
    server). Shared by the renewal itself and by the routes, which check it
    before queueing a renewal for approval: a request no renewal could honour
    must not wait for an approver."""
    if not cert.crt:
        raise RenewalError('Certificate data not available', 400)
    # Any revocation, a suspension included: renewing would hand back a good serial
    if cert.revoked:
        raise RenewalError('Cannot renew a revoked certificate. Issue a new certificate instead.', 409)
    # The record outlives the row: a row left unrevoked beside it renews nothing
    from services.cert.issued_lookup import row_persisted_revocation
    if row_persisted_revocation(cert) is not None:
        raise RenewalError('Cannot renew a revoked certificate. Issue a new certificate instead.', 409)
    if cert.source == 'msca':
        raise RenewalError('Microsoft CA certificates must be renewed through the AD CS connector', 400)

    if not cert.prv:
        # The key lives on the device (SCEP, EST, WSTEP, ACME enrolment,
        # certificate imported without its key): a certificate re-signed
        # here could never reach it, and superseding the serial the device
        # still presents only got that device refused by OCSP and the CRL
        raise RenewalError(
            'The server does not hold the private key of this certificate; '
            'renew it through its enrollment protocol, sign a new request or '
            'issue a new certificate',
            409,
        )

    # Read from the stored type, before the certificate's key is ever loaded
    if fips_mode.enabled():
        alg = key_algorithms.get(cert.key_algo)
        name = alg.display if alg else _stored_eddsa_name(cert)
        if name in ('Ed25519', 'Ed448'):
            try:
                fips_mode.refuse_unless_approved(name.upper(), f'{name} key of certificate {cert.id}')
            except FipsRestricted as e:
                raise RenewalError.from_fips(e) from e

    # The template's SAN types bind the renewed names as they bound the issuance
    template_id = getattr(cert, 'template_id', None)
    if template_id:
        from models.certificate_template import CertificateTemplate
        from services.template_service import allowed_san_types, san_type_of, san_type_refusal
        template = db.session.get(CertificateTemplate, template_id)
        allowed = allowed_san_types(template) if template is not None else None
        if allowed is not None:
            try:
                names = x509.load_pem_x509_certificate(b64decode(cert.crt)).extensions \
                    .get_extension_for_class(x509.SubjectAlternativeName).value
            except x509.ExtensionNotFound:  # a certificate without SAN carries no SAN type
                names = []
            refusal = san_type_refusal(allowed, [san_type_of(n) for n in names], template.name)
            if refusal:
                raise RenewalError(f'Policy violation: {refusal}', 400)


def _stored_eddsa_name(cert: Certificate):
    try:
        return eddsa_key_name(load_pem_bytes(cert.prv, context=f'certificate {cert.id}'))
    except ValueError:
        return None


def renew_certificate_in_place(cert: Certificate, ca=None, *, username: str = 'system',
                               actor_user_id=None, rekey: bool = True, regenerate_crl: bool = True,
                               trigger: str = 'manual', known_serial=SERIAL_UNSET,
                               validity_days=None) -> dict:
    """Renew ``cert`` in place and commit; raise :class:`RenewalError` with
    the session rolled back when it cannot be. ``known_serial`` is the serial
    the caller decided on (default: the one ``cert`` carries). The other member
    of a related pair is renewed with it, A first, in the same commit."""
    try:
        members = _renewal_members(cert)
        pair = len(members) == 2
        staged_all, renewed_a = [], None
        for index, member in enumerate(members):
            is_cert = member is cert
            # B names A as renewed a moment ago; a lone certificate names its A as it is
            related_to = renewed_a if pair and index == 1 else _current_related(member)
            try:
                staged_member = _stage_renewal(
                    member, ca if is_cert else None, rekey=rekey, trigger=trigger,
                    known_serial=known_serial if is_cert else SERIAL_UNSET,
                    validity_days=validity_days, related_to=related_to)
            except RenewalError as e:
                if is_cert:
                    raise
                raise RenewalError(f'Related certificate {member.id}: {e.message}', e.status,
                                   e.problem_type) from e
            if pair and index == 0:
                renewed_a = x509.load_pem_x509_certificate(staged_member['cert_pem'])
            staged_all.append(staged_member)
        if not pair and related_to is None:
            # Renewed alone and naming none: the row leaves its pair, as its certificate has
            from services.cert.related_pair import leave_pair
            leave_pair(staged_all[0]['cert'])
        # A renewal is an issuance, counted in its commit; the CA rows are locked last,
        # after every certificate row written, and by id so two pairs never cross
        try:
            db.session.flush()
        except SQLAlchemyError as e:
            logger.error(f'Failed to renew certificate {cert.id}: {e}', exc_info=True)
            raise RenewalError('Failed to renew certificate', 500) from e
        for s in sorted(staged_all, key=lambda s: s['ca'].id):
            next_ca_serial(s['ca'])
    except Exception:
        db.session.rollback()
        raise
    staged = staged_all[members.index(cert)]
    cert, ca = staged['cert'], staged['ca']
    cert_id = staged['cert_id']
    if not commit_or_rollback(logger, f'Failed to renew certificate {cert_id}'):
        raise RenewalError('Failed to renew certificate', 500)

    others = [s for s in staged_all if s is not staged]
    outcome = {
        'cert_id': cert_id,
        'old_serial': staged['old_serial'],
        'new_serial': staged['new_serial'],
        'valid_from': utc_isoformat(staged['valid_from']),
        'valid_to': utc_isoformat(staged['valid_to']),
        'ca_id': ca.id,
        'ca_refid': ca.refid,
        'rekeyed': bool(rekey),
        'notices': staged['notices'],
        'related': [{'cert_id': s['cert_id'], 'ca_id': s['ca'].id, 'new_serial': s['new_serial']}
                    for s in others],
    }
    crl_done = set()
    for s in [staged] + others:
        _after_commit(s['cert'], s['ca'], s, username=username, actor_user_id=actor_user_id,
                      rekey=rekey, regenerate_crl=regenerate_crl and s['ca'].id not in crl_done,
                      trigger=trigger)
        crl_done.add(s['ca'].id)
    return outcome


def _renewal_members(cert):
    """``[cert]``, or both members of its related pair with A first. A partner whose key
    the server does not hold (enrolled by a device) renews through its own protocol, never
    here; an archived one (superseded) is not renewed at all."""
    from services.cert.related_pair import anchor_first, mutual_partner
    try:
        partner = mutual_partner(cert)
    except InvalidRequestError:  # deleted since the caller read it: _reread answers 404
        return [cert]
    if (partner is None or partner.archived or not cert.crt
            or not partner.crt or not partner.prv):
        return [cert]
    from services.cert.issued_lookup import row_revoked
    if row_revoked(partner):  # by its row or by the record of its serial
        return [cert]
    return list(anchor_first(cert, partner))


def renewal_partner(cert):
    """The other member of the pair renewed with ``cert``, None when it renews alone."""
    return next((m for m in _renewal_members(cert) if m is not cert), None)


def _current_related(row):
    """The certificate A that *row*'s certificate names, while A is held, valid,
    unrevoked and not superseded; None otherwise (the renewed certificate then names nothing)."""
    from services.cert.related_pair import row_certificate
    try:
        if not row.related_certificate_id or not row.crt:
            return None
    except InvalidRequestError:  # deleted since the caller read it: _reread answers 404
        return None
    original = x509.load_pem_x509_certificate(b64decode(row.crt))
    try:
        original.extensions.get_extension_for_oid(RELATED_CERT_EXTENSION_OID)
    except x509.ExtensionNotFound:
        return None
    a_row = db.session.get(Certificate, row.related_certificate_id)
    if a_row is None or a_row.archived or not a_row.crt:
        return None
    from services.cert.issued_lookup import row_revoked
    if row_revoked(a_row):  # by its row or by the record of its serial
        return None
    cert_a = row_certificate(a_row)
    if cert_a.not_valid_after_utc.replace(tzinfo=None) < utc_now():
        return None
    return cert_a


def _stage_renewal(cert, ca, *, rekey, trigger, known_serial, validity_days, related_to=None) -> dict:
    """Every check, the signature and the writes, left uncommitted; *related_to*
    is the certificate A the renewed one names (RFC 9763)."""
    cert = _reread(cert, known_serial, trigger)
    check_renewable(cert)
    ca, ca_cert, ca_key = _signing_ca(cert, ca)

    original = x509.load_pem_x509_certificate(b64decode(cert.crt))
    public_key = original.public_key()
    _check_key(public_key, rekey)

    days = _requested_days(original, validity_days)
    sign_hash, granted, notices = _apply_policies(cert, ca, ca_key, original, days,
                                                  pq_hybrid=related_to is not None)
    now = utc_now()
    wanted = now + timedelta(days=granted)
    not_after = clamp_not_after(wanted, ca_cert)
    if not_after < wanted:
        notices.append(notices_mod.validity_shortened(
            granted, max((not_after - now).days, 0), notices_mod.issuer_expiry_reason(not_after)))
    _check_name_constraints(ca_cert, original)

    new_key = None
    if rekey:
        try:
            new_key = _generate_like(public_key)
        except FipsRestricted as e:
            raise RenewalError.from_fips(e) from e
        public_key = new_key.public_key()

    builder = _builder(original, ca, ca_cert, public_key, not_after,
                       _template_policy_oids(getattr(cert, 'template_id', None)), related_to,
                       _template_custom_extensions(getattr(cert, 'template_id', None)))
    renewed = builder.sign(private_key=ca_key, algorithm=sign_hash,
                           rsa_padding=rsa_padding_for(ca_key, sign_hash))
    renewed, scts = _apply_ct(renewed, ca_cert, ca_key)

    old_serial, old_valid_to = cert.serial_number, cert.valid_to
    old_digest = certificate_key_sha256(cert.crt)  # read before the row takes the new key
    new_serial = canonical_serial(renewed.serial_number)  # query.update skips the validator
    _take_serial(cert.id, old_serial, new_serial, trigger)

    cert_pem = renewed.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key_to_pem(new_key) if new_key is not None else None
    _write_row(cert, ca, ca_cert, renewed, cert_pem, key_pem, new_serial, now)
    _record_superseded(cert.id, ca, old_serial, old_valid_to, now, old_digest)
    _record_scts(cert.id, scts)
    return {
        'cert': cert, 'cert_id': cert.id, 'ca': ca, 'old_serial': old_serial,
        'new_serial': new_serial, 'valid_from': cert.valid_from, 'valid_to': cert.valid_to,
        'notices': notices, 'cert_pem': cert_pem, 'key_pem': key_pem,
    }


def _reread(cert, known_serial, trigger):
    """The row as stored now, locked until the commit on PostgreSQL. A row renewed or
    archived since the caller read it is refused: an archived row is renewed only by a
    caller that read it archived, never revived behind another renewal's back."""
    try:
        expected = cert.serial_number if known_serial is SERIAL_UNSET else known_serial
        was_archived = bool(cert.archived)
        fresh = db.session.get(Certificate, cert.id, populate_existing=True, with_for_update=True)
    except InvalidRequestError:  # deleted since the caller read it
        fresh = None
    if fresh is None:
        raise RenewalError('Certificate no longer exists', 404)
    if fresh.serial_number != expected or bool(fresh.archived) != was_archived:
        raise RenewalError(_renewed_meanwhile_message(trigger), 409)
    return fresh


def _signing_ca(cert, ca):
    """``(ca, ca certificate, signing key)`` of the CA that really signed ``cert``."""
    if ca is None:
        ca = resolve_issuing_ca(cert)
    if ca is None:
        raise RenewalError(
            'Issuing CA not found. The CA that signed this certificate is not in the system.', 404)
    if not ca.has_private_key:
        raise RenewalError('CA private key not available. Cannot renew without CA private key.', 400)
    if not ca.crt:
        raise RenewalError('Issuing CA is awaiting its certificate', 400)
    if ca.offline:
        raise RenewalError('CA is offline; restore it before renewing', 400)
    if ca.revoked_in_chain:
        raise RenewalError('CA is revoked and can no longer renew certificates', 400)
    # The row's caref is not proof of issuance: only a certificate this CA signed renews under it
    from utils.cert_issuer import ca_signed
    if not ca_signed(ca, x509.load_pem_x509_certificate(b64decode(cert.crt))):
        raise RenewalError(
            f'This certificate\'s signature does not verify with the current key of CA "{ca.descr}" '
            '(re-keyed or replaced): it cannot be renewed under it, issue a new certificate instead', 400)
    # Under the CA that really signed it, which a row without caref only now names
    from services.cert.issued_lookup import row_persisted_revocation
    if row_persisted_revocation(cert, ca) is not None:
        raise RenewalError('Cannot renew a revoked certificate. Issue a new certificate instead.', 409)

    from services.hsm.ca_key_loader import get_ca_signing_key
    try:
        ca_key = get_ca_signing_key(ca)
    except FipsRestricted as e:
        raise RenewalError.from_fips(e) from e
    except Exception as e:
        logger.error(f"Failed to load the signing key of CA {ca.id}: {e}", exc_info=True)
        raise RenewalError('Failed to load CA signing key', 500) from e

    ca_cert = x509.load_pem_x509_certificate(b64decode(ca.crt))
    try:
        check_issuer_window(ca_cert)
    except IssuerWindowError as e:
        raise RenewalError(str(e), 400) from e
    return ca, ca_cert, ca_key


def _check_key(public_key, rekey: bool) -> None:
    """Refuse a family no generator reproduces, then a key issuance would refuse."""
    if rekey and family_for_public_key(public_key) is None:
        raise RenewalError(
            f'Cannot renew: a {type(public_key).__name__} key cannot be regenerated; '
            'issue a new certificate instead', 400)
    weakness = validate_enrollment_public_key(public_key)
    if weakness:
        raise RenewalError(f'Cannot renew: {weakness}', 400)


def _requested_days(original, validity_days) -> int:
    """The duration asked for, else the original's in whole days, within the ceiling."""
    if validity_days is None:
        span = (original.not_valid_after_utc - original.not_valid_before_utc).days
        days = span if span >= 1 else DEFAULT_CERTIFICATE_VALIDITY_DAYS
    else:
        days = int(validity_days)
    return min(days, MAX_RENEWAL_DAYS)


def _common_name(certificate):
    attrs = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return str(attrs[0].value) if attrs else None


def _san_entries(certificate) -> list:
    try:
        return list(certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value)
    except x509.ExtensionNotFound:
        return []


def _dns_names(certificate) -> list:
    """Distinct DNS names of the SAN, in order (case does not make a name distinct)."""
    seen, names = set(), []
    for entry in _san_entries(certificate):
        if isinstance(entry, x509.DNSName) and entry.value.lower() not in seen:
            seen.add(entry.value.lower())
            names.append(entry.value)
    return names


def _has_time_stamping(certificate):
    try:
        eku = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    except x509.ExtensionNotFound:
        return False
    return x509.ExtendedKeyUsageOID.TIME_STAMPING in eku


def _apply_policies(cert, ca, ca_key, original, days, pq_hybrid=False):
    """``(signing hash, granted days, notices)``; every violation in one 400."""
    from services.policy_service import (
        PolicyEvaluationService, RENEWAL_OPERATIONS, key_label_for_public_key)
    cn = _common_name(original)
    dns = _dns_names(original)
    policies = PolicyEvaluationService.applicable_policies(
        ca.id, getattr(cert, 'template_id', None), cn, dns, operation=RENEWAL_OPERATIONS)
    context = {'operation': 'renewal', 'ca_id': ca.id, 'subject': cn or cert.descr}
    key_label = key_label_for_public_key(original.public_key())
    advisories = []
    tsa_signer = _has_time_stamping(original)
    # The original's hash while it is at least the CA key's and the policies allow it
    sign_hash, violations = PolicyEvaluationService.checked_signing_hash(
        policies, ca_key, renewal_digest(original, ca_key), explicit=False,
        key_type=key_label, context=context, tsa_signer=tsa_signer, notices=advisories,
        pq_hybrid=pq_hybrid)
    if not violations:
        log_renewal_digest(logger, original, sign_hash, cn or cert.descr)
    rule_violations, granted, capped_by = PolicyEvaluationService.enforce_rules(
        policies, key_type=key_label, dns_name_count=len(dns), validity_days=days,
        context=context, tsa_signer=tsa_signer, notices=advisories, pq_hybrid=pq_hybrid)
    violations = list(dict.fromkeys(list(violations) + list(rule_violations)))
    if violations:
        raise RenewalError('Policy violation: ' + '; '.join(violations), 400)
    notices = []
    if capped_by and granted < days:
        notices.append(notices_mod.validity_shortened(
            days, granted, notices_mod.policy_validity_reason(capped_by, granted)))
    notices += advisories
    return sign_hash, granted, notices


def _check_name_constraints(ca_cert, original) -> None:
    from services.trust_store.constraints_mixin import validate_name_constraints
    try:
        validate_name_constraints(ca_cert, original.subject, _san_entries(original) or None,
                                  renewal_of=original)
    except ValueError as e:
        raise RenewalError(f'Renewal violates CA name constraints: {e}', 400) from e


def _generate_like(public_key):
    """A new private key of the same family and size or curve as ``public_key``."""
    family = family_for_public_key(public_key)
    if family == 'RSA':
        return generate_rsa(public_key.key_size)
    if family == 'EC':
        return generate_ec(public_key.curve)
    label = label_for_public_key(public_key)
    if label is None:
        raise ValueError(f'No generator reproduces a {type(public_key).__name__} key')
    return key_algorithms.generate(label)


def _template_policy_oids(template_id):
    """Policy OIDs the certificate's template lists today ([] without a template)."""
    if not template_id:
        return []
    from models.certificate_template import CertificateTemplate
    from services.template_service import template_extensions
    template = db.session.get(CertificateTemplate, template_id)
    return template_policy_oids(template_extensions(template)) if template is not None else []


def _template_custom_extensions(template_id):
    """The custom extensions the certificate's template lists today ([] without one)."""
    if not template_id:
        return []
    from models.certificate_template import CertificateTemplate
    from utils.custom_extensions import TemplateConfigError, template_custom_extensions
    try:
        return template_custom_extensions(db.session.get(CertificateTemplate, template_id))
    except TemplateConfigError as e:
        raise RenewalError(str(e), 400) from e


from services.trust_store.csr_operations_mixin import _SID_SECURITY_EXT_OID as _SID_EXT  # noqa: E402
_SID_SECURITY_EXT_OID = _SID_EXT.dotted_string


def _signed_by(cert, ca_cert) -> bool:
    from utils.cert_issuer import UnsupportedIssuerKey, certificate_signed_by
    try:
        return certificate_signed_by(cert, ca_cert)
    except UnsupportedIssuerKey:
        return False


def _builder(original, ca, ca_cert, public_key, not_after, template_oids=(),
             related_to=None, template_extensions=()) -> x509.CertificateBuilder:
    """The original's subject and extensions; the issuer's own rebuilt from the CA,
    and the link to *related_to* (A) from A as it is now. The template's custom
    extensions replace the original's of the same OID and join the others."""
    from utils.custom_extensions import add_custom_extensions
    replaced = {e['oid'] for e in template_extensions}
    # An import sets the issuer without checking: a SID the CA never signed is not carried over
    dropped = set() if _signed_by(original, ca_cert) else {_SID_SECURITY_EXT_OID}
    builder = (
        x509.CertificateBuilder()
        .subject_name(original.subject)
        .issuer_name(ca_cert.subject)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(cert_not_before())
        .not_valid_after(not_after)
    )
    ekus = []
    for ext in original.extensions:
        if ext.oid in _ISSUER_OWNED_EXTENSION_OIDS or ext.oid.dotted_string in replaced:
            continue
        if ext.oid.dotted_string in dropped:
            logger.warning('In-place renewal: serial %x was not signed by CA %s, its SID is not carried over',
                           original.serial_number, ca.refid)
            continue
        if ext.oid == ExtensionOID.EXTENDED_KEY_USAGE:
            ekus = list(ext.value)
        try:
            builder = builder.add_extension(ext.value, critical=ext.critical)
        except Exception as e:
            raise RenewalError(
                f'Cannot carry extension {ext.oid.dotted_string} over to the renewed '
                f'certificate: {e}', 400) from e
    builder = add_custom_extensions(builder, template_extensions)
    builder = add_ca_pointer_extensions(
        builder, ca, carried_policy_oids(original, ca.cps_oid if ca.cps_enabled else None, template_oids))
    builder = builder.add_extension(
        x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
    builder = builder.add_extension(authority_key_identifier_from_issuer(ca_cert), critical=False)
    builder = constrain_builder_key_usage(builder)
    builder = add_ocsp_nocheck_if_responder(builder, ekus)
    if related_to is not None:
        from services.cert.related_pair import RelatedCertificateRefused, linked_builder
        try:
            builder = linked_builder(builder, related_to)
        except RelatedCertificateRefused as e:
            raise RenewalError(f'Cannot renew: {e}', 400) from e
    return builder


def _apply_ct(renewed, ca_cert, ca_key):
    # Looked up at call time: the policy is the ct_client module's
    from utils import ct_client
    try:
        return ct_client.apply_ct_policy(renewed, ca_cert, ca_key)
    except FipsRestricted as e:
        raise RenewalError.from_fips(e) from e
    except ValueError as e:
        raise RenewalError(f'Cannot renew: {e}', 400) from e


def _take_serial(cert_id, old_serial, new_serial, trigger) -> None:
    """Swap the serial only if the row still carries the one this renewal read."""
    holds_old = (Certificate.serial_number.is_(None) if old_serial is None
                 else Certificate.serial_number == old_serial)
    taken = db.session.query(Certificate).filter(Certificate.id == cert_id, holds_old).update(
        {Certificate.serial_number: new_serial}, synchronize_session=False)
    if taken != 1:
        raise RenewalError(_renewed_meanwhile_message(trigger), 409)


def _write_row(cert, ca, ca_cert, renewed, cert_pem, key_pem, new_serial, now) -> None:
    cert.crt = b64encode(cert_pem).decode('utf-8')
    if key_pem is not None:
        cert.prv = encrypt_private_key(b64encode(key_pem).decode('utf-8'))
    cert.serial_number = new_serial
    cert.key_algo = key_algo_for_public_key(renewed.public_key())
    cert.caref = ca.refid
    cert.issuer = ca_cert.subject.rfc4514_string()
    cert.valid_from = renewed.not_valid_before_utc.replace(tzinfo=None)
    cert.valid_to = renewed.not_valid_after_utc.replace(tzinfo=None)

    entries = _san_entries(renewed)
    columns = {
        'san_dns': [e.value for e in entries if isinstance(e, x509.DNSName)],
        'san_ip': [str(e.value) for e in entries if isinstance(e, x509.IPAddress)],
        'san_email': [e.value for e in entries if isinstance(e, x509.RFC822Name)],
        'san_uri': [e.value for e in entries if isinstance(e, x509.UniformResourceIdentifier)],
        'san_upn': extract_upns_from_san_list(entries),
    }
    for column, values in columns.items():
        setattr(cert, column, json.dumps(values) if values else None)

    # Defensive: a renewed certificate is a good, current one
    cert.revoked = False
    cert.revoked_at = None
    cert.revoke_reason = None
    cert.invalidity_at = None
    cert.archived = False
    cert.renewed_at = now
    cert.renewed_times = (cert.renewed_times or 0) + 1


def _record_superseded(cert_id, ca, old_serial, old_valid_to, now, old_digest=None) -> None:
    """Keep the replaced serial on the CA's CRL until it would have expired."""
    from services.cert.issued_lookup import record_reason_replaceable
    if not old_serial or ca is None:
        return
    row = RevokedSerial.query.filter_by(caref=ca.refid, serial_number=canonical_serial(old_serial)).first()
    fresh = row is None
    if fresh:
        row = RevokedSerial(caref=ca.refid, serial_number=old_serial)
        db.session.add(row)
    # A final revocation already recorded keeps its reason and date (keyCompromise is never superseded)
    if fresh or record_reason_replaceable(row, 'superseded'):
        row.revoked_at = now
        row.revoke_reason = 'superseded'
    row.valid_to = old_valid_to or now + _SUPERSEDED_FALLBACK
    row.certificate_id = cert_id
    row.public_key_sha256 = old_digest


def _record_scts(cert_id, scts) -> None:
    """The SCTs of the renewed certificate replace those of the one it supersedes."""
    key = f'cert_scts_{cert_id}'
    row = SystemConfig.query.filter_by(key=key).first()
    if scts:
        row = row or SystemConfig(key=key)
        row.value = json.dumps(scts)
        db.session.add(row)
    elif row is not None:
        db.session.delete(row)


def _after_commit(cert, ca, staged, *, username, actor_user_id, rekey, regenerate_crl, trigger) -> None:
    """Each effect is tried on its own: a failure is logged, never raised."""
    cert_id = staged['cert_id']
    old_serial = staged['old_serial']

    try:
        from services.approval_gate import resolve_moot_requests
        resolve_moot_requests(
            'renewal', 'certificate_id', cert_id, outcome='approved', username=username,
            user_id=actor_user_id, certificate_id=cert_id,
            reason='Renewed by the scheduler' if trigger == 'auto' else 'Renewed directly')
    except Exception as e:
        logger.warning(f"Pending renewal requests of certificate {cert_id} not closed: {e}")

    try:
        _write_files(cert, staged['cert_pem'], staged['key_pem'])
    except Exception as e:
        logger.warning(f"Files of renewed certificate {cert_id} not written: {e}")

    try:
        from services.ocsp_service import OCSPService
        for responder_ca_id in OCSPService.responder_cas_for_certificate(cert_id):
            OCSPService.invalidate_ca_cache(responder_ca_id)
    except Exception as e:
        logger.warning(f"OCSP cache of the CAs certificate {cert_id} answers for not cleared: {e}")

    try:
        if old_serial:
            from services.ocsp_service import OCSPService
            OCSPService.invalidate_cached_responses(old_serial, ca_id=ca.id)
    except Exception as e:
        logger.warning(f"OCSP cache of superseded serial {old_serial} not cleared: {e}")

    try:
        if regenerate_crl and ca.cdp_enabled:
            from services.crl import CRLService
            CRLService.generate_crl(ca.id, username=username)
    except Exception as e:
        logger.warning(f"CRL of CA {ca.id} not regenerated after renewing certificate {cert_id}: {e}")

    try:
        from services.audit_service import AuditService
        valid_to = staged['valid_to']
        AuditService.log_action(
            action='certificate_renewed',
            resource_type='certificate',
            resource_id=str(cert_id),
            resource_name=cert.subject,
            details=(f"Renewed until {utc_isoformat(valid_to)} (trigger: {trigger}, "
                     f"{'rekeyed' if rekey else 'same key'}); serial {old_serial} -> "
                     f"{staged['new_serial']}"),
            success=True,
            username=username,
            user_id=actor_user_id,
        )
    except Exception as e:
        logger.warning(f"Renewal of certificate {cert_id} not audited: {e}")

    try:
        from services.webhook_service import emit_cert_renewed
        emit_cert_renewed(cert.to_dict(), ca_refid=ca.refid, actor=username)
    except Exception as e:
        logger.warning(f"Renewal webhook of certificate {cert_id} not emitted: {e}")


def _write_files(cert, cert_pem: bytes, key_pem) -> None:
    path = cert_cert_path(cert)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(cert_pem)
    if key_pem is None:  # same key: mirror the stored one
        key_pem = load_pem_bytes(cert.prv, context=f'certificate {cert.id}')
    mirror_private_key(cert_key_path(cert), key_pem, context=f'certificate {cert.id}')
