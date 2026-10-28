"""Cross-sign a held CA's key with another held CA (#400).

The certificate carries the subject CA's name and public key (its private key is never
needed) under the issuer's signature, and is stored beside the subject's own certificate.
"""
import base64
import logging
from datetime import timedelta
from typing import List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from models import CA
from models.ca_cross_certificate import CACrossCertificate
from services.ca import cross_certs
from services.ca.cross_certs import CrossCertError
from utils import notices as notices_mod
from utils.datetime_utils import to_naive_utc, utc_now

logger = logging.getLogger(__name__)

MAX_VALIDITY_DAYS = 3650
DEFAULT_VALIDITY_DAYS = 1825
_UNSET = object()


def _int_in(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise CrossCertError(f'{label} must be an integer between {low} and {high}')
    return value


def _own_certificate(ca: CA, role: str) -> x509.Certificate:
    if not ca.crt:
        raise CrossCertError(f'The {role} CA is awaiting its certificate', 409, 'ca_pending')
    cert = cross_certs._load_record(ca)
    if cert is None:
        raise CrossCertError(f'The {role} CA certificate could not be read', 500, 'corrupt')
    return cert


def _urls(issuer: CA):
    ref = issuer.url_ref
    cdp = [u.replace('{ca_refid}', ref) for u in issuer.get_cdp_urls()] if issuer.cdp_enabled else None
    ocsp = issuer.get_ocsp_urls() if issuer.ocsp_enabled else None
    aia = [u.replace('{ca_refid}', ref) for u in issuer.get_aia_urls()] if issuer.aia_ca_issuers_enabled else None
    return cdp, ocsp, aia


def _chain_has_key(start: CA, key_spki: bytes, include_start: bool) -> bool:
    from utils.ca_chain import walk_ca_chain
    for ca in walk_ca_chain(start, include_start=include_start):
        cert = cross_certs._load_record(ca) if ca.crt else None
        if cert is not None and cross_certs._spki(cert) == key_spki:
            return True
    return False


def _refuse_degenerate_pair(issuer: CA, subject: CA) -> None:
    """A cross-certificate must join two hierarchies: not a parent re-certifying its child, nor the reverse."""
    if _chain_has_key(subject, cross_certs._spki(_own_certificate(issuer, 'issuing')), include_start=False):
        raise CrossCertError('The issuing CA is already an ancestor of the subject CA', 409, 'issuer_is_ancestor')
    if _chain_has_key(issuer, cross_certs._spki(_own_certificate(subject, 'subject')), include_start=False):
        raise CrossCertError('The subject CA is an ancestor of the issuing CA', 409, 'subject_is_ancestor')


_COPIED = (x509.NameConstraints, x509.PolicyConstraints, x509.InhibitAnyPolicy, x509.ExtendedKeyUsage)


def _constraints_of(cert: x509.Certificate) -> list:
    """The extensions of the subject's own certificate that restrict what its chains may certify."""
    return [ext for ext in cert.extensions if isinstance(ext.value, _COPIED)]


def cross_sign(issuer: CA, subject: CA, validity_days=DEFAULT_VALIDITY_DAYS, path_length=_UNSET,
               username: str = 'system') -> Tuple[CACrossCertificate, List[str]]:
    """Issue and store ``subject``'s cross-certificate under ``issuer``; returns (row, warnings)."""
    from services.ca.ca_signing import CAOfflineError, CASigningMixin
    from services.hsm.ca_key_loader import get_ca_signing_key
    from services.policy_service import PolicyEvaluationService, key_label_for_public_key
    from services.ca.ca_creation import _refuse_on_violations
    from services.trust_store import TrustStoreService
    from utils.ca_signing_window import IssuerWindowError, check_issuer_window

    validity_days = _int_in(validity_days, 1, MAX_VALIDITY_DAYS, 'validity_days')
    if path_length is not _UNSET and path_length is not None:
        _int_in(path_length, 0, 255, 'path_length')
    issuer_cert = _own_certificate(issuer, 'issuing')
    subject_cert = _own_certificate(subject, 'subject')
    if cross_certs._spki(issuer_cert) == cross_certs._spki(subject_cert):
        raise CrossCertError('Both CAs share one key: a certificate over it would not be a cross-certificate')
    if subject.revoked_in_chain:
        raise CrossCertError('The subject CA is revoked, or sits under a revoked CA', 409, 'subject_revoked')
    _refuse_degenerate_pair(issuer, subject)
    try:
        subject_length = subject_cert.extensions.get_extension_for_class(x509.BasicConstraints).value.path_length
    except x509.ExtensionNotFound:
        subject_length = None

    try:
        CASigningMixin._check_ca_offline(issuer)
    except CAOfflineError as e:
        raise CrossCertError(str(e), 409, 'issuer_offline')
    try:
        check_issuer_window(issuer_cert)
        if path_length is _UNSET:
            path_length = subject_length
    except (IssuerWindowError, ValueError) as e:
        raise CrossCertError(str(e))

    policies = PolicyEvaluationService.applicable_policies(issuer.id, None, subject.common_name)
    key_label = key_label_for_public_key(subject_cert.public_key())
    context = {'operation': 'ca_cross_signing', 'subject': subject.common_name}
    requested_days = validity_days
    _, validity_days, capped_by = PolicyEvaluationService.enforce_rules(
        policies, key_type=key_label, validity_days=validity_days, context=context, signer=issuer, notify=False)

    issuer_key = get_ca_signing_key(issuer)
    sign_hash, violations = PolicyEvaluationService.checked_signing_hash(
        policies, issuer_key, None, explicit=False, key_type=key_label, context=context,
        validity_days=validity_days)
    _refuse_on_violations(violations)

    cdp, ocsp, aia = _urls(issuer)
    try:
        ski = subject_cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value
    except x509.ExtensionNotFound:
        ski = None
    cps = issuer.cps_uri if issuer.cps_enabled and issuer.cps_uri else None
    pem, _ = TrustStoreService.create_ca_certificate(
        subject=subject_cert.subject, private_key=None, subject_public_key=subject_cert.public_key(),
        issuer=issuer_cert.subject, issuer_private_key=issuer_key, issuer_cert=issuer_cert,
        validity_days=validity_days, digest=sign_hash.name if sign_hash is not None else 'sha256',
        ocsp_uris=ocsp, cdp_urls=cdp, aia_ca_issuers_urls=aia,
        cps_uri=cps, cps_oid=issuer.cps_oid if cps else None, path_length=path_length,
        not_valid_after_max=to_naive_utc(issuer_cert.not_valid_after_utc),
        copied_extensions=_constraints_of(subject_cert), subject_key_identifier=ski)
    cert = x509.load_pem_x509_certificate(pem)
    row, warnings = cross_certs.attach_certificate(subject, cert, username)
    notices = []
    if capped_by and validity_days < requested_days:
        notices.append(notices_mod.validity_shortened(
            requested_days, validity_days, notices_mod.policy_validity_reason(capped_by, validity_days)))
    elif to_naive_utc(issuer_cert.not_valid_after_utc) < utc_now() + timedelta(days=validity_days):
        granted = max((to_naive_utc(cert.not_valid_after_utc) - utc_now()).days, 0)
        notices.append(notices_mod.validity_shortened(
            validity_days, granted, notices_mod.issuer_expiry_reason(issuer_cert.not_valid_after_utc)))
    return row, warnings + notices
