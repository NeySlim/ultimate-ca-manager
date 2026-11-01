"""Certificates bound by RFC 9763: B carries id-pe-relatedCert naming A.

``related_certificate_id`` on B names A; on A it names B once the pair is
mutual (the hybrid issue form, or the newest B a request ties to A through
Sign CSR, ACME, EST or WSTEP). The pair revokes and renews together only when
the link is mutual.
"""
import base64
import logging
from datetime import timedelta

from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtensionOID

from models import Certificate, db
from services.policy_service import APPROVAL_REQUEST_LIFETIME, PolicyViolation
from utils import key_algorithms, related_cert
from utils.ca_signing_window import IssuerWindowError, check_issuer_window
from utils.datetime_utils import utc_now
from utils.leaf_key_usage import key_usage_for_key
from utils.serial_format import serial_variants

logger = logging.getLogger(__name__)

# RFC 9763 §3.2 leaves freshness to local policy: a stored request may wait
# for its approval as long as approval requests live
REQUEST_MAX_AGE = APPROVAL_REQUEST_LIFETIME
REQUEST_CLOCK_SKEW = timedelta(minutes=5)

ROLE_CLASSICAL = 'classical'
ROLE_PQ = 'pq'

# Never copied from A onto B: B's own key, CT proof and link are recomputed
_NOT_COPIED = frozenset({
    ExtensionOID.SUBJECT_KEY_IDENTIFIER,
    ExtensionOID.KEY_USAGE,
    ExtensionOID.PRECERT_SIGNED_CERTIFICATE_TIMESTAMPS,
    ExtensionOID.PRECERT_POISON,
    related_cert.RELATED_CERT_EXTENSION_OID,
})


class RelatedCertificateRefused(PolicyViolation):
    """A relatedCertRequest the CA will not honour; answered 400 with its message."""


def role_for_public_key(public_key) -> str:
    label = key_algorithms.label_for_public_key(public_key)
    return ROLE_PQ if label and key_algorithms.is_post_quantum(label) else ROLE_CLASSICAL


def row_certificate(row):
    """The parsed certificate of *row*, None when it holds none."""
    if row is None or not row.crt:
        return None
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


def find_requested(req):
    """``(row, certificate)`` of the certificate a request names by issuer and
    serial; refused when none or several distinct ones match."""
    serial = related_cert.requested_serial(req)
    issuer = asn1_x509.Name.load(related_cert.requested_issuer_der(req))
    if serial < 0:
        raise RelatedCertificateRefused('The related certificate serial is negative')
    matches = {}
    rows = Certificate.query.filter(Certificate.serial_number.in_(serial_variants(serial)),
                                    Certificate.crt.isnot(None)).order_by(Certificate.id).all()
    for row in rows:
        try:
            cert = row_certificate(row)
        except Exception:  # an unreadable row names nothing
            continue
        if cert.serial_number == serial and asn1_x509.Name.load(cert.issuer.public_bytes()) == issuer:
            matches.setdefault(cert.fingerprint(hashes.SHA256()), (row, cert))
    if not matches:
        raise RelatedCertificateRefused(
            'The related certificate named by the request is not held by this instance')
    if len(matches) > 1:
        raise RelatedCertificateRefused(
            'Several certificates match the related certificate issuer and serial')
    return next(iter(matches.values()))


def verify_request(req, now=None):
    """Certificate A of a relatedCertRequest, once found, valid, unrevoked,
    issued by a CA held here, fresh and signed by A's key (RFC 9763 §3.2)."""
    from services.cert.renewal import resolve_issuing_ca
    from utils.cert_issuer import certificate_signed_by
    now = now or utc_now()
    asked_at = related_cert.request_time(req)
    if asked_at > now + REQUEST_CLOCK_SKEW:
        raise RelatedCertificateRefused('The relatedCertRequest time is in the future')
    if now - asked_at > REQUEST_MAX_AGE:
        raise RelatedCertificateRefused('The relatedCertRequest is too old; sign a new one')
    row, cert_a = find_requested(req)
    if row.revoked:
        raise RelatedCertificateRefused('The related certificate is revoked')
    if cert_a.not_valid_after_utc.replace(tzinfo=None) < now:
        raise RelatedCertificateRefused('The related certificate has expired')
    if cert_a.not_valid_before_utc.replace(tzinfo=None) > now + REQUEST_CLOCK_SKEW:
        raise RelatedCertificateRefused('The related certificate is not valid yet')
    try:
        if cert_a.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise RelatedCertificateRefused('The related certificate must be an end-entity certificate')
    except x509.ExtensionNotFound:
        pass
    ca = resolve_issuing_ca(row)
    ca_cert = row_certificate(ca) if ca is not None else None
    if ca_cert is None or not certificate_signed_by(cert_a, ca_cert):
        raise RelatedCertificateRefused('The related certificate was not issued by a CA of this instance')
    if ca.revoked_in_chain:
        raise RelatedCertificateRefused('The CA of the related certificate is revoked')
    _check_chain_validity(ca, now)
    _check_location(req, cert_a)
    if not related_cert.request_signature_valid(req, cert_a.public_key()):
        raise RelatedCertificateRefused(
            'The relatedCertRequest signature does not verify with the related certificate key')
    return row, cert_a


def _check_chain_validity(ca, now):
    """RFC 5280 §6.1.3: every CA certificate of A's path held here is valid at *now*."""
    depth = 0
    while ca is not None and depth <= ca.MAX_CHAIN_DEPTH:
        try:
            check_issuer_window(row_certificate(ca), now)
        except IssuerWindowError as e:
            raise RelatedCertificateRefused(
                f'The CA certificate {ca.descr!r} of the related certificate is not valid now') from e
        ca, depth = ca.issuing_ca(), depth + 1


def _check_location(req, cert_a):
    """RFC 9763 §3.2: a data: locationInfo must hold A, in any position. Any other
    URI is not fetched: the copy held here, found by issuer and serial, stands in for it."""
    for uri in related_cert.location_uris(req):
        if uri[:5].lower() != 'data:':
            continue
        try:
            located = related_cert.data_url_certificates(uri)
        except related_cert.RelatedCertError as e:
            raise RelatedCertificateRefused(str(e)) from e
        if cert_a not in located:
            raise RelatedCertificateRefused(
                'The certificate in the relatedCertRequest locationInfo is not the related certificate')


def builder_purposes(builder):
    """``(KeyUsage or None, EKU list or None)`` a certificate builder asserts."""
    ku = eku = None
    for ext in builder._extensions:
        if ext.oid == ExtensionOID.KEY_USAGE:
            ku = ext.value
        elif ext.oid == ExtensionOID.EXTENDED_KEY_USAGE:
            eku = list(ext.value)
    return ku, eku


def check_purposes(cert_a, key_usage, ekus) -> None:
    """Refuse a B asserting a key usage bit or an EKU that A does not carry."""
    outside = related_cert.usages_outside(cert_a, key_usage, ekus)
    if outside:
        raise RelatedCertificateRefused(
            'The related certificate does not carry what this one asserts: ' + ', '.join(outside))


def linked_builder(builder, cert_a):
    """*builder* checked against A's key purposes, with id-pe-relatedCert naming A (non-critical)."""
    check_purposes(cert_a, *builder_purposes(builder))
    return builder.add_extension(related_cert.related_certificate_extension(cert_a), critical=False)


def pq_builder_from(cert_a, public_key):
    """Certificate B for *public_key*: A's subject, validity and extensions, its
    own key identifier and key usage, and the link to A."""
    builder = (x509.CertificateBuilder()
               .subject_name(cert_a.subject)
               .issuer_name(cert_a.issuer)
               .public_key(public_key)
               .serial_number(x509.random_serial_number())
               .not_valid_before(cert_a.not_valid_before_utc)
               .not_valid_after(cert_a.not_valid_after_utc))
    ekus = []
    for ext in cert_a.extensions:
        if ext.oid in _NOT_COPIED:
            continue
        if ext.oid == ExtensionOID.EXTENDED_KEY_USAGE:
            ekus = list(ext.value)
        builder = builder.add_extension(ext.value, critical=ext.critical)
    try:
        a_usage = cert_a.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE)
        builder = builder.add_extension(
            key_usage_for_key(public_key, a_usage.value, ekus), critical=a_usage.critical)
    except x509.ExtensionNotFound:
        pass
    builder = builder.add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
    return linked_builder(builder, cert_a)


def mutual_partner(row):
    """The other member of *row*'s pair when both name each other, else None."""
    if row is None or not row.related_certificate_id:
        return None
    partner = db.session.get(Certificate, row.related_certificate_id)
    if partner is None or partner.related_certificate_id != row.id:
        return None
    return partner


def anchor_first(row, partner):
    """``(A, B)``: B is the one whose certificate names the other, else the one carrying the link."""
    cert, other = row_certificate(row), row_certificate(partner)
    if related_cert.references(cert, other):
        return partner, row
    if related_cert.references(other, cert):
        return row, partner
    if related_cert.read_related_certificate(cert) is not None:
        return partner, row
    return row, partner


def requested_by_csr(csr_der):
    """``(row, certificate)`` of the A a CSR's relatedCertRequest names, None without one."""
    try:
        req = related_cert.request_from_csr_der(csr_der)
    except related_cert.RelatedCertError as e:
        raise RelatedCertificateRefused(str(e)) from e
    return find_requested(req) if req is not None else None


def _names_its_link(row, cert):
    """True when *row*'s certificate names the row it links to: it is that row's B."""
    linked = db.session.get(Certificate, row.related_certificate_id) if row.related_certificate_id else None
    other = _readable(linked) if linked is not None else None
    return other is not None and related_cert.references(cert, other)


def link_issued(b_row, cert_b, requested):
    """Record on *b_row* the A (*requested*, from ``requested_by_csr``) its
    certificate names, and on A the way back: the newest B takes A from the
    previous one, unless A is itself the B of the row it links to."""
    if requested is None or related_cert.read_related_certificate(cert_b) is None:
        return None
    a_row, cert_a = requested
    if not related_cert.references(cert_b, cert_a):
        return None
    b_row.related_certificate_id = a_row.id
    b_row.hybrid_role = role_for_public_key(cert_b.public_key())
    if not _names_its_link(a_row, cert_a):
        a_row.related_certificate_id = b_row.id
        a_row.hybrid_role = role_for_public_key(cert_a.public_key())
    return a_row


def hand_over_link(revoked_row):
    """When *revoked_row* was the B of a valid A, A's link moves to the newest
    unrevoked B naming A (a superseded B revoked alone); the moved-to row or None."""
    a_row = mutual_partner(revoked_row)
    if a_row is None or a_row.revoked:
        return None
    cert_a = row_certificate(a_row)
    if not related_cert.references(row_certificate(revoked_row), cert_a):
        return None
    for b_row in (Certificate.query.filter(Certificate.related_certificate_id == a_row.id,
                                           Certificate.id != revoked_row.id,
                                           Certificate.revoked.isnot(True),
                                           Certificate.crt.isnot(None))
                  .order_by(Certificate.id.desc()).all()):
        if related_cert.references(row_certificate(b_row), cert_a):
            a_row.related_certificate_id = b_row.id
            return b_row
    return None


def _readable(row):
    """``row_certificate`` that names nothing for an unreadable row instead of raising."""
    try:
        return row_certificate(row)
    except Exception:
        return None


def _relink_or_leave(row, gone_id):
    """*row* was linked to *gone_id*: its way back moves to the newest unrevoked
    certificate still naming it, else it leaves its pair (no link, no role)."""
    cert = _readable(row)
    for b_row in (Certificate.query.filter(Certificate.related_certificate_id == row.id,
                                           Certificate.id.notin_([row.id, gone_id]),
                                           Certificate.revoked.isnot(True),
                                           Certificate.crt.isnot(None))
                  .order_by(Certificate.id.desc()).all()):
        b_cert = _readable(b_row)
        if cert is not None and b_cert is not None and related_cert.references(b_cert, cert):
            row.related_certificate_id = b_row.id
            return
    row.related_certificate_id = None
    row.hybrid_role = None


def unlink_rows_naming(row_id):
    """Rows linked to *row_id*, whose certificate is gone or replaced, relink or leave their pair."""
    for other in Certificate.query.filter(Certificate.related_certificate_id == row_id,
                                          Certificate.id != row_id).all():
        _relink_or_leave(other, row_id)


def leave_pair(row):
    """*row* now holds a certificate that names none and none names: link and role
    go, and the rows linked to it relink or leave their pair."""
    row.related_certificate_id = None
    row.hybrid_role = None
    unlink_rows_naming(row.id)
