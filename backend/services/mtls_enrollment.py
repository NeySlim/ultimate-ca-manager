"""What an mTLS enrolment (an ``AuthCertificate`` row) is bound to.

An enrolment names a certificate; the private key that may travel with it
(PKCS#12, PEM or JKS export) belongs to exactly one ``Certificate`` row. Every
route that joins the two used to do so by serial number alone, so any
authenticated user could enrol a forged certificate bearing another record's
serial and export that record's key. The lookup here is shared by the mTLS
account routes and the user-certificates routes so the rule cannot drift.
"""

import base64
import hashlib
import logging
import re
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from models import CA, Certificate
from utils.serial_format import serial_variants

logger = logging.getLogger(__name__)


def normalized_fingerprint(value) -> Optional[Tuple[str, str]]:
    """``(algorithm, HEX)`` for a stored or presented fingerprint, or None.

    Proxies present SHA-1 (nginx ``$ssl_client_fingerprint``, 40 hex digits)
    as readily as SHA-256 (64); colons and case vary. Anything else is
    ignored rather than trusted.
    """
    if not value:
        return None
    digits = ''.join(ch for ch in str(value) if ch not in ': ').upper()
    if len(digits) == 40:
        return 'sha1', digits
    if len(digits) == 64:
        return 'sha256', digits
    return None


# Names proxies write that RFC 4514 does not define, to their OID
_DN_ALIASES = {
    '2.5.4.3': ('commonName',), '2.5.4.6': ('countryName',), '2.5.4.7': ('localityName',),
    '2.5.4.8': ('S', 'stateOrProvinceName'), '2.5.4.9': ('streetAddress',),
    '2.5.4.10': ('organizationName',), '2.5.4.11': ('organizationalUnitName',),
    '2.5.4.12': ('title', 'T'), '2.5.4.4': ('SN', 'surname'), '2.5.4.5': ('serialNumber',),
    '2.5.4.42': ('GN', 'G', 'givenName'), '2.5.4.43': ('initials', 'I'),
    '2.5.4.44': ('generationQualifier',), '2.5.4.46': ('dnQualifier',), '2.5.4.65': ('pseudonym',),
    '2.5.4.17': ('postalCode',), '2.5.4.15': ('businessCategory',), '2.5.4.97': ('organizationIdentifier',),
    '2.5.4.13': ('description',), '2.5.4.41': ('name',), '2.5.4.20': ('telephoneNumber',),
    '1.3.6.1.4.1.311.60.2.1.3': ('jurisdictionC', 'jurisdictionCountryName'),
    '1.3.6.1.4.1.311.60.2.1.2': ('jurisdictionST', 'jurisdictionStateOrProvinceName'),
    '1.3.6.1.4.1.311.60.2.1.1': ('jurisdictionL', 'jurisdictionLocalityName'),
    '0.9.2342.19200300.100.1.25': ('domainComponent',), '0.9.2342.19200300.100.1.1': ('userId', 'userID'),
    '1.2.840.113549.1.9.1': ('emailAddress', 'E', 'email', 'Email', 'EMAIL'),
}
_NAME_OVERRIDES = {}
for _dotted, _names in _DN_ALIASES.items():
    for _name in _names:
        for _spelling in {_name, _name.upper(), _name.lower()}:
            _NAME_OVERRIDES[_spelling] = x509.ObjectIdentifier(_dotted)
# DER tags of the string types a '#hex' value carries
_DER_STRINGS = {0x0c: 'utf-8', 0x13: 'ascii', 0x16: 'ascii', 0x14: 'latin-1', 0x1e: 'utf-16-be', 0x1c: 'utf-32-be'}


def _legacy_to_rfc4514(text: str) -> str:
    """OpenSSL's ``/C=FR/O=Soci\xC3\xA9t\xC3\xA9`` (nginx ``_legacy``, Apache ``LegacyDNStringFormat``) as RFC 4514."""
    parts, current, i = [], '', 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text):
            current += text[i:i + 2]
            i += 2
        elif text[i] == '/':
            parts.append(current)
            current, i = '', i + 1
        else:
            current, i = current + text[i], i + 1
    parts.append(current)
    rdns = []
    for part in filter(None, parts):
        avas = []
        # A multi-valued RDN prints as /CN=R+O=O1: an unescaped '+' before another type separates its values
        for ava in re.split(r'(?<!\\)\+(?=[A-Za-z][A-Za-z0-9-]*=|(?:OID\.)?\d+(?:\.\d+)+=)', part):
            name, sep, value = ava.partition('=')
            if not sep:
                raise ValueError(part)
            raw = re.sub(rb'\\x([0-9a-fA-F]{2})', lambda m: bytes([int(m.group(1), 16)]),
                         value.encode('utf-8')).decode('utf-8')
            raw = re.sub(r'\\(.)', r'\1', raw)      # OpenSSL 3 escapes '+' and '/' in values
            escaped = re.sub(r'([,+"\\<>;=])', r'\\\1', raw)
            if escaped[:1] in ('#', ' '):
                escaped = '\\' + escaped
            if escaped.endswith(' '):
                escaped = escaped[:-1] + '\\ '
            avas.append(f'{name.strip()}={escaped}')
        rdns.append('+'.join(avas))
    return ','.join(reversed(rdns))


_TYPE_OIDS = {name.casefold(): oid for name, oid in _NAME_OVERRIDES.items()}
_TYPE_OIDS.update({name.casefold(): x509.ObjectIdentifier(dotted) for name, dotted in {
    'CN': '2.5.4.3', 'C': '2.5.4.6', 'L': '2.5.4.7', 'ST': '2.5.4.8', 'STREET': '2.5.4.9',
    'O': '2.5.4.10', 'OU': '2.5.4.11', 'DC': '0.9.2342.19200300.100.1.25',
    'UID': '0.9.2342.19200300.100.1.1'}.items()})
_HEX = frozenset('0123456789abcdefABCDEF')


def _type_oid(name: str):
    """An attribute type in any case, or a dotted OID with or without RFC 1779's ``OID.``."""
    if name[:4].casefold() == 'oid.':
        name = name[4:]
    if re.fullmatch(r'\d+(\.\d+)+', name):
        return x509.ObjectIdentifier(name)
    return _TYPE_OIDS.get(name.casefold())


def _lenient_attributes(text: str) -> Optional[frozenset]:
    """A DN as written by proxies RFC 4514 does not describe, or None.

    Spaces around ``,`` ``;`` ``+`` ``=`` (RFC 1779, OpenSSL ``XN_FLAG_ONELINE``,
    Java, IIS), quoted values, ``;`` separators and type names in any case.
    """
    avas, i, n = [], 0, len(text)
    while True:
        j = i
        while j < n and text[j] not in '=,;+':
            j += 1
        oid = _type_oid(text[i:j].strip()) if j < n and text[j] == '=' else None
        if oid is None:
            return None
        i = j + 1
        while i < n and text[i] == ' ':
            i += 1
        raw = bytearray()
        if i < n and text[i] == '"':
            i += 1
            while i < n and text[i] != '"':
                if text[i] == '\\' and i + 1 < n:
                    i += 1
                raw += text[i].encode('utf-8')
                i += 1
            if i >= n:
                return None
            i += 1
            while i < n and text[i] == ' ':
                i += 1
            value = raw.decode('utf-8', 'replace')
        elif i < n and text[i] == '#':
            j = i + 1
            while j < n and text[j] in _HEX:
                j += 1
            try:
                value = bytes.fromhex(text[i + 1:j]).decode('latin-1')   # read as the strict parser does
            except ValueError:
                return None
            i = j
            while i < n and text[i] == ' ':
                i += 1
        else:
            # Spaces before the separator stay in the value: _attribute_value folds them
            while i < n and text[i] not in ',;+':
                if text[i] == '\\' and i + 1 < n:
                    pair = text[i + 1:i + 3]
                    if len(pair) == 2 and set(pair) <= _HEX:
                        raw.append(int(pair, 16))
                        i += 3
                    else:
                        raw += text[i + 1].encode('utf-8')
                        i += 2
                elif text[i] == '"':
                    return None
                else:
                    raw += text[i].encode('utf-8')
                    i += 1
            try:
                value = raw.decode('utf-8')
            except UnicodeDecodeError:
                return None
        avas.append((oid.dotted_string, _attribute_value(value)))
        if i >= n:
            return frozenset(avas)
        if text[i] not in ',;+':
            return None
        i += 1
        while i < n and text[i] == ' ':
            i += 1


def _attribute_value(value) -> str:
    """An attribute value compared caselessly, a '#hex' string type read back as its text."""
    if isinstance(value, bytes):
        return value.hex()
    if len(value) >= 2 and ord(value[0]) in _DER_STRINGS and ord(value[1]) == len(value) - 2:
        try:
            value = value[2:].encode('latin-1').decode(_DER_STRINGS[ord(value[0])])
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
    return ' '.join(value.split()).casefold()


def dn_attributes(dn) -> Optional[frozenset]:
    """A DN as a set of (OID, value), order ignored, or None when it cannot be read.

    Takes a ``x509.Name``, an RFC 4514 string (cryptography's, or OpenSSL's
    with names such as ``emailAddress``) or OpenSSL's legacy ``/C=FR/CN=..``.
    """
    if not isinstance(dn, x509.Name):
        text = str(dn or '')   # not stripped: '\ ' at the end is an escaped space
        if not text.strip():
            return None
        try:
            text = _legacy_to_rfc4514(text.strip()) if text.lstrip().startswith('/') else text
        except ValueError:
            return None
        try:
            strict = x509.Name.from_rfc4514_string(text, attr_name_overrides=_NAME_OVERRIDES)
        except Exception:
            strict = None
        read = (frozenset((a.oid.dotted_string, _attribute_value(a.value)) for a in strict)
                if strict is not None else None)
        return read or _lenient_attributes(text)
    return frozenset((a.oid.dotted_string, _attribute_value(a.value)) for a in dn)


def _issuer_match(row, presented) -> Optional[bool]:
    """Whether an enrolment's issuer is the presented one; None when either cannot be read."""
    if presented is None:
        return None
    enrolled = _load(row.cert_pem)
    stored = dn_attributes(enrolled.issuer) if enrolled is not None else dn_attributes(row.cert_issuer)
    return None if stored is None else stored == presented


def records_issuer(row) -> bool:
    """Whether an enrolment recorded its issuer, as text or by its stored certificate."""
    return bool(row.cert_issuer) or _load(row.cert_pem) is not None


def same_issuer(one, other) -> Optional[bool]:
    """Whether two DNs name one issuer: the same text, or the same attributes; None when unreadable."""
    if one and one == other:
        return True
    one, other = dn_attributes(one), dn_attributes(other)
    return None if one is None or other is None else one == other


def _serial_match(row, serial: int) -> Optional[int]:
    """How an enrolment's serial is ``serial``: 0 by its certificate, 1 read as decimal, 2 as hex.

    None when it is not: the stored text is read both ways, its certificate settles it.
    """
    enrolled = _load(row.cert_pem)
    if enrolled is not None:
        return 0 if enrolled.serial_number == serial else None
    raw = str(row.cert_serial or '').replace(':', '').strip()
    for rank, base in ((1, 10), (2, 16)):
        try:
            if int(raw, base) == serial:
                return rank
        except ValueError:
            continue
    return None


def _ranked(serial: int, issuer, pool=None) -> list:
    """(rank, row) of the enrolments that may be certificate (issuer, serial), best first.

    An issuer read on both sides excludes another one; with no issuer given, or one
    recorded here that cannot be read, the row only ranks lower. A given issuer that
    cannot be read leaves only the enrolments that recorded none (``records_issuer``).
    """
    from models.auth_certificate import AuthCertificate
    forms = serial_variants(serial)
    if pool is None:
        rows = AuthCertificate.query.filter(AuthCertificate.cert_serial.in_(forms)).order_by(AuthCertificate.id).all()
    else:
        rows = sorted({row.id: row for form in forms for row in pool.get(form, ())}.values(), key=lambda r: r.id)
    presented = dn_attributes(issuer) if issuer is not None else None
    unreadable = issuer is not None and presented is None
    ranked = []
    for row in rows:
        serial_rank = _serial_match(row, serial)
        if serial_rank is None:
            continue
        if unreadable and records_issuer(row):
            continue      # an issuer that cannot be read is no recorded one
        same = _issuer_match(row, presented) if row.cert_issuer or row.cert_pem else None
        if same is False:
            continue
        ranked.append(((0 if same else 1, serial_rank), row))
    return sorted(ranked, key=lambda item: (item[0], item[1].id))


def enrolments_of(serial: int, issuer=None, pool=None) -> list:
    """The enrolments that may be certificate (``issuer``, ``serial``), best match first.

    A serial is unique per issuer only (RFC 5280 §4.1.2.2). ``issuer`` is a
    ``x509.Name`` or a DN string; ``pool`` maps stored serials to rows, for a caller checking many.
    """
    return [row for _rank, row in _ranked(serial, issuer, pool)]


def presented_identity(cert_info: dict):
    """(serial, issuer) of a presented certificate: from the certificate when it came, else its headers.

    A serial from headers is hexadecimal (nginx, Apache); None when unreadable.
    """
    cert = _load((cert_info.get('cert_pem') or '').encode()) if cert_info.get('cert_pem') else None
    if cert is not None:
        return cert.serial_number, cert.issuer
    try:
        return int(str(cert_info.get('serial')).replace(':', ''), 16), cert_info.get('issuer_dn')
    except (TypeError, ValueError):
        return None, cert_info.get('issuer_dn')


def presented_enrolment(cert_info: dict):
    """The enrolment of a presented certificate, or None.

    The fingerprint tells same-serial enrolments apart; failing it, the best
    match must be the only one of its rank, never a guess between two. A
    serial without a readable issuer opens only enrolments that recorded none.
    """
    serial, issuer = presented_identity(cert_info)
    if serial is None:
        return None
    readable = dn_attributes(issuer) is not None
    ranked = _ranked(serial, issuer if readable else None)
    presented = normalized_fingerprint(cert_info.get('fingerprint'))
    if presented:
        for _rank, row in ranked:
            if normalized_fingerprint(row.cert_fingerprint) == presented:
                return row
    if not readable:
        # A serial is unique per issuer only: without one, it opens no enrolment that recorded one
        refused = [row.id for _rank, row in ranked if records_issuer(row)]
        if refused:
            logger.warning("mTLS: serial %X presented without a readable issuer; enrolments %s "
                           "record one and are refused (forward X-SSL-Client-I-DN or X-SSL-Client-Cert)",
                           serial, ', '.join(str(i) for i in refused))
            ranked = [(rank, row) for rank, row in ranked if not records_issuer(row)]
    best = [row for rank, row in ranked if ranked and rank == ranked[0][0]]
    if len(best) > 1:
        logger.warning("mTLS: %d enrolments compete for serial %X (ids %s), none chosen",
                       len(best), serial, ', '.join(str(row.id) for row in best))
        return None
    return best[0] if best else None


def _fingerprint(der: bytes, algorithm: str) -> str:
    # SHA-1 only to match what a proxy presents; the DER is compared first when stored
    if algorithm == 'sha1':
        digest = hashlib.sha1(der)  # nosec B324
        return digest.hexdigest().upper()
    return hashlib.sha256(der).hexdigest().upper()


def _load(pem) -> Optional[x509.Certificate]:
    if not pem:
        return None
    try:
        return x509.load_pem_x509_certificate(bytes(pem), default_backend())
    except Exception:
        return None


def parse_validity_days(value, default: int = 365) -> Optional[int]:
    """An integer number of days within the issuance bounds, or None when the
    value is not exactly that (booleans, fractions and free text included).

    The shape rule lives in :mod:`utils.validity` now, where the other
    issuance doors read it from too: this was the only one that refused a
    JSON boolean, so the same body was a 400 here and a one-day certificate
    at ``POST /api/v2/certificates``."""
    from utils.validity import coerce_validity_days, validity_days_in_range

    if value is None:
        value = default
    days = coerce_validity_days(value)
    if days is None or not validity_days_in_range(days):
        return None
    return days


def issuing_ca_for(cert: x509.Certificate) -> Optional[CA]:
    """The CA row that really signed ``cert`` (signature verified), or None.

    Enrolling a certificate no CA of this server issued proves nothing and
    only serves to squat a serial number: the mTLS trusted CA is always one
    of the server's CAs, so such a certificate could never authenticate.
    """
    issuer_dn = cert.issuer.rfc4514_string()
    from utils.cert_issuer import self_signed_first
    for ca in self_signed_first(CA.query.filter(CA.subject == issuer_dn).order_by(CA.id).all()):
        ca_cert = _load(base64.b64decode(ca.crt)) if ca.crt else None
        if ca_cert is None:
            continue
        try:
            cert.verify_directly_issued_by(ca_cert)
            return ca
        except Exception:
            continue
    return None


def certificate_row_for(auth_cert) -> Optional[Certificate]:
    """The ``Certificate`` row an enrolment is bound to, or None.

    The row must be the very certificate that was enrolled: byte-identical
    to the stored PEM when the enrolment kept one, else matching its
    fingerprint, else (enrolments made before either was stored) carrying
    the same serial number AND issuer, the serial being read back from the
    row's own certificate so that a decimal string and a hexadecimal one
    never designate two different certificates. The stored serial is read
    as decimal first; hexadecimal is tried only when no row exists for the
    decimal reading.
    """
    raw = (auth_cert.cert_serial or '').strip()
    enrolled = _load(auth_cert.cert_pem)
    enrolled_der = enrolled.public_bytes(serialization.Encoding.DER) if enrolled else None
    fingerprint = normalized_fingerprint(auth_cert.cert_fingerprint)

    readings = []
    for base in (10, 16):
        try:
            serial = int(raw, base)
        except ValueError:
            continue
        readings.append((serial, serial_variants(serial)))
    if not readings:
        return None
    # Both readings in one query, then split back so decimal still wins
    candidates = Certificate.query.filter(
        Certificate.serial_number.in_(set().union(*(v for _, v in readings)))
    ).order_by(Certificate.id).all()

    for serial, variants in readings:
        rows = [row for row in candidates if row.serial_number in variants]
        if not rows:
            continue
        for row in rows:
            row_cert = _load(base64.b64decode(row.crt)) if row.crt else None
            if row_cert is None:
                continue
            row_der = row_cert.public_bytes(serialization.Encoding.DER)
            if enrolled_der is not None:
                if row_der == enrolled_der:
                    return row
                continue
            if fingerprint is not None:
                if _fingerprint(row_der, fingerprint[0]) == fingerprint[1]:
                    return row
                continue
            if (row_cert.serial_number == serial and auth_cert.cert_issuer
                    and row.issuer == auth_cert.cert_issuer):
                return row
        return None
    return None


def made_for_account(certificate, user) -> bool:
    """Whether ``created_by`` names this very account: a record older than the
    account was made for an earlier holder of the name, and an undated one
    proves nothing; an administrator still assigns either."""
    from utils.datetime_utils import to_naive_utc
    if certificate.created_by != user.username:
        return False
    made, opened = to_naive_utc(certificate.created_at), to_naive_utc(user.created_at)
    return made is not None and opened is not None and made >= opened


# Withdrawing a certificate from service, RFC 5280 §5.3.1.
REMOVAL_REASON = 'cessationOfOperation'


def _revocation_held(actor) -> bool:
    """Whether the revocation policies apply: to anyone but an administrator,
    the certificate's holder included."""
    return actor is not None and getattr(actor, 'role', None) != 'admin'


def remove_enrolment(auth_cert, username: str = 'system', actor=None):
    """Revoke the certificate an enrolment names, then delete both.

    Returns ``(True, None)`` or ``(False, response)``. Deleting the
    ``AuthCertificate`` row is what withdraws access to UCM, and that is all
    these routes used to do: the certificate stayed valid for every other
    service trusting the same authority, with nothing on the CRL or at the
    responder to say otherwise. It is revoked first so the withdrawal is
    published, and the operator keeps a single gesture.
    """
    from models import db
    from services.cert_service import CertificateService
    from utils.datetime_utils import utc_now
    from utils.db_transaction import safe_commit
    from utils.response import error_response
    from services.cert.issued_lookup import row_revoked

    certificate = certificate_row_for(auth_cert)
    certificate_id = certificate.id if certificate else None

    needs_revoking = bool(
        certificate is not None
        and certificate.crt
        and not row_revoked(certificate)  # by its row or by its CA's record of its serial
        and (not certificate.valid_to or certificate.valid_to >= utc_now())
    )
    if needs_revoking and _revocation_held(actor):
        try:
            from services.approval_gate import revocation_policy_for
            policy = revocation_policy_for(certificate)
        except Exception as error:
            logger.error('Enrolment %s: policy evaluation failed: %s', auth_cert.id, error)
            return False, error_response(
                'Policy evaluation failed; the enrolment was not removed', 500)
        if policy is not None:
            return False, error_response(
                f'Revoking this certificate requires approval per policy "{policy.name}": '
                'request its revocation, then remove the enrolment once it is revoked', 409)
    if needs_revoking:
        try:
            # The enrolled certificate only: its pair partner is not part of the enrolment
            CertificateService.revoke_certificate(
                cert_id=certificate_id, reason=REMOVAL_REASON, username=username,
                revoke_related=False)
        except Exception as error:
            # An authority that cannot sign right now is not a reason to make
            # the certificate disappear without a trace; say so instead.
            logger.error('Enrolment %s: revocation refused: %s',
                         auth_cert.id, error)
            db.session.rollback()
            return False, error_response(
                'The certificate could not be revoked, so it was not deleted: '
                'it would stay valid for anything else trusting its authority. '
                'Check that the issuing CA can sign, then try again', 409)

    # The enrolment goes first: it is what mTLS authenticates against.
    db.session.delete(auth_cert)
    committed, failure = safe_commit(
        logger, 'Failed to delete the certificate enrolment')
    if not committed:
        return False, failure

    if certificate_id and not CertificateService.delete_certificate(
            certificate_id, username=username):
        # The access is withdrawn either way; saying it all worked would put
        # a success in the ledger for a certificate that is still there.
        return False, error_response(
            'The enrolment was removed but its certificate could not be '
            'deleted; it is still listed under Certificates', 500)
    return True, None
