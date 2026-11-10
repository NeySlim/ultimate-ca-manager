"""Certificates bound by RFC 9763: B carries id-pe-relatedCert naming A.

``related_certificate_id`` on B names A; on A it names B once the pair is
mutual (the hybrid issue form, or the newest B a request ties to A through
Sign CSR, ACME, EST or WSTEP). The pair revokes together only when the link is
mutual, and renews together only when the server also holds both keys.
"""
import base64
import hashlib
import logging
from datetime import timedelta

from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.x509.oid import ExtensionOID
from sqlalchemy.exc import IntegrityError

from models import Certificate, db
from models.related_cert_request import RelatedCertRequestUse
from services.policy_service import APPROVAL_REQUEST_LIFETIME, PolicyViolation
from utils import key_algorithms, related_cert
from utils.ca_signing_window import IssuerWindowError, check_issuer_window
from utils.cert_issuer import is_self_signed
from utils.datetime_utils import utc_now
from utils.leaf_key_usage import key_usage_for_key
from utils.serial_format import canonical_serial

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
    rows = Certificate.query.filter(Certificate.serial_number == canonical_serial(serial),
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
    """Certificate A of a relatedCertRequest, once found, signed by A's key, valid,
    unrevoked, issued by a CA held here and fresh (RFC 9763 §3.2)."""
    from services.cert.renewal import resolve_issuing_ca
    from utils.cert_issuer import certificate_signed_by
    now = now or utc_now()
    asked_at = related_cert.request_time(req)
    if asked_at > now + REQUEST_CLOCK_SKEW:
        raise RelatedCertificateRefused('The relatedCertRequest time is in the future')
    if now - asked_at > REQUEST_MAX_AGE:
        raise RelatedCertificateRefused('The relatedCertRequest is too old; sign a new one')
    row, cert_a = find_requested(req)
    # Proof of A's key first: what follows names A's state and its CA, for its holder only
    if not related_cert.request_signature_valid(req, cert_a.public_key()):
        raise RelatedCertificateRefused(
            'The relatedCertRequest signature does not verify with the related certificate key')
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
    _check_chain(ca, now)
    _check_location(req, cert_a)
    return row, cert_a


REPLAYED = ('This relatedCertRequest was already used with another key; '
            'sign a new one with the related certificate')


def _request_digest(req, public_key) -> str:
    """SHA-256 of what the requester signed and of its signature in a form only A's key
    can vary: r alone for ECDSA, as (r, n - s) verifies too, the integer for RSA."""
    signature = req['signature'].native
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        signature = _integer_bytes(decode_dss_signature(signature)[0])
    elif isinstance(public_key, rsa.RSAPublicKey):
        signature = _integer_bytes(int.from_bytes(signature, 'big'))
    digest = hashlib.sha256(related_cert.signed_content(req['cert_id'], req['request_time'].native))
    digest.update(signature)
    return digest.hexdigest()


def _integer_bytes(value: int) -> bytes:
    return value.to_bytes((value.bit_length() + 7) // 8 or 1, 'big')


def _key_digest(csr_der) -> str:
    try:
        return hashlib.sha256(related_cert.csr_spki_der(csr_der)).hexdigest()
    except related_cert.RelatedCertError as e:
        raise RelatedCertificateRefused(str(e)) from e


def _bound_key(digest):
    row = RelatedCertRequestUse.query.filter_by(request_sha256=digest).first()
    return row.spki_sha256 if row is not None else None


def check_request_key(req, cert_a, csr_der) -> None:
    """Refuse a request already honoured for another key B; the same key (a retry) passes."""
    bound = _bound_key(_request_digest(req, cert_a.public_key()))
    if bound is not None and bound != _key_digest(csr_der):
        raise RelatedCertificateRefused(REPLAYED)


def record_request_key(csr_der, requested) -> None:
    """Bind the CSR's relatedCertRequest (naming *requested*, from ``requested_by_csr``) to
    its key B in the caller's transaction, which commits it with the certificate; a
    concurrent binding to another key refuses."""
    if requested is None:
        return
    try:
        req = related_cert.request_from_csr_der(csr_der)
    except related_cert.RelatedCertError as e:
        raise RelatedCertificateRefused(str(e)) from e
    digest, key = _request_digest(req, requested[1].public_key()), _key_digest(csr_der)
    # Requests older than this are refused anyway: their bindings are dropped as we go
    RelatedCertRequestUse.query.filter(
        RelatedCertRequestUse.request_time < utc_now() - REQUEST_MAX_AGE
    ).delete(synchronize_session=False)
    bound = _bound_key(digest)
    if bound is None:
        try:
            with db.session.begin_nested():
                db.session.add(RelatedCertRequestUse(request_sha256=digest, spki_sha256=key,
                                                     request_time=related_cert.request_time(req)))
            return
        except IntegrityError:
            bound = _bound_key(digest)
    if bound != key:
        raise RelatedCertificateRefused(REPLAYED)


def _extension(cert, kind):
    try:
        return cert.extensions.get_extension_for_class(kind).value
    except x509.ExtensionNotFound:
        return None


def _check_chain(ca, now):
    """RFC 5280 §6.1.3-§6.1.4 on every CA certificate of A's path held here, the root
    included: valid at *now*, cA set (k), within its pathLenConstraint (l, m), and
    keyCertSign set when it carries keyUsage (n). (k) does not reach the trust anchor:
    a self-signed root without basicConstraints passes when it is v1 or carries keyUsage,
    as OpenSSL's X509_check_ca has it. Certificate policies are not checked."""
    depth = below = 0  # below: CA certificates between this one and A, self-issued ones aside
    while ca is not None and depth <= ca.MAX_CHAIN_DEPTH:
        cert, issuer = row_certificate(ca), ca.issuing_ca()
        prefix = f'The CA certificate {ca.descr!r} of the related certificate'
        try:
            check_issuer_window(cert, now)
        except IssuerWindowError as e:
            raise RelatedCertificateRefused(f'{prefix} is not valid now') from e
        constraints = _extension(cert, x509.BasicConstraints)
        usage = _extension(cert, x509.KeyUsage)
        if constraints is None:
            anchor = issuer is None and is_self_signed(cert)
            if not (anchor and (cert.version == x509.Version.v1 or usage is not None)):
                raise RelatedCertificateRefused(f'{prefix} is not a CA certificate')
        elif not constraints.ca:
            raise RelatedCertificateRefused(f'{prefix} is not a CA certificate')
        elif constraints.path_length is not None and below > constraints.path_length:
            raise RelatedCertificateRefused(f'{prefix} has a path length constraint the path exceeds')
        if usage is not None and not usage.key_cert_sign:
            raise RelatedCertificateRefused(f'{prefix} may not sign certificates (keyUsage)')
        if cert.subject != cert.issuer:
            below += 1
        ca, depth = issuer, depth + 1


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


def _live_rows_linked_to(row_id, *excluded):
    """Rows linked to *row_id* whose certificate is still current (unrevoked, unarchived,
    unexpired), newest first."""
    return (Certificate.query.filter(Certificate.related_certificate_id == row_id,
                                     Certificate.id.notin_([row_id, *excluded]),
                                     Certificate.revoked.isnot(True),
                                     Certificate.archived.isnot(True),
                                     Certificate.valid_to > utc_now(),
                                     Certificate.crt.isnot(None))
            .order_by(Certificate.id.desc()).all())


def hand_over_link(revoked_row):
    """When *revoked_row*, the newest B of a valid A, is revoked alone, A returns to
    the newest older B still current and naming A; the moved-to row or None."""
    a_row = mutual_partner(revoked_row)
    if a_row is None or a_row.revoked:
        return None
    cert_a = row_certificate(a_row)
    if not related_cert.references(row_certificate(revoked_row), cert_a):
        return None
    for b_row in _live_rows_linked_to(a_row.id, revoked_row.id):
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
    """*row* was linked to *gone_id*: its way back moves to the newest current
    certificate still naming it, else it leaves its pair (no link, no role)."""
    cert = _readable(row)
    for b_row in _live_rows_linked_to(row.id, gone_id):
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
