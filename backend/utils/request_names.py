"""What a request may put in a certificate's subject and SAN, whatever path
it takes (issue form, Sign CSR, EST, SCEP, ACME, WSTEP)."""
from __future__ import annotations

import re

from cryptography import x509
from cryptography.x509.name import _ASN1Type
from cryptography.x509.oid import NameOID


class RequestRejected(ValueError):
    """A request the CA refuses for its content; its message is safe to show."""


# RFC 5280 annex A upper bounds, in characters
_SUBJECT_BOUNDS = {
    NameOID.COMMON_NAME: ('CN', 64),
    NameOID.ORGANIZATION_NAME: ('O', 64),
    NameOID.ORGANIZATIONAL_UNIT_NAME: ('OU', 64),
    NameOID.LOCALITY_NAME: ('L', 128),
    NameOID.STATE_OR_PROVINCE_NAME: ('ST', 128),
    NameOID.SERIAL_NUMBER: ('serialNumber', 64),
    NameOID.TITLE: ('title', 64),
    NameOID.PSEUDONYM: ('pseudonym', 128),
    NameOID.EMAIL_ADDRESS: ('emailAddress', 255),
}
_COUNTRY_RE = re.compile(r'[A-Za-z]{2}')
# A CN made of hostname characters only: meant as a host, so worth a word when it gives none
_HOST_TOKEN_RE = re.compile(r'(\*\.)?[A-Za-z0-9_-]{1,63}(\.[A-Za-z0-9_-]{1,63})*\.?')


def subject_bounds_error(subject: x509.Name) -> str | None:
    """First attribute outside RFC 5280 annex A (C: two letters, RFC 4519 §2.2)."""
    for attr in subject:
        value = attr.value if isinstance(attr.value, str) else ''
        if attr.oid == NameOID.COUNTRY_NAME:
            if not _COUNTRY_RE.fullmatch(value):
                return f'C must be a two-letter country code (ISO 3166), got {value!r}'
            if attr._type != _ASN1Type.PrintableString:
                return 'C must be encoded as a PrintableString (RFC 5280 annex A)'
            continue
        bound = _SUBJECT_BOUNDS.get(attr.oid)
        if bound and len(value) > bound[1]:
            return f'{bound[0]} must be {bound[1]} characters or less'
    return None


def subject_email_names(subject: x509.Name) -> list:
    """rfc822Names of the subject's emailAddress values (RFC 5280 §4.1.2.6); an
    address off the ASCII mailbox syntax is left out (RFC 8398 is not rfc822Name)."""
    from utils.san_parse import is_valid_san_email
    names = []
    for attr in subject.get_attributes_for_oid(NameOID.EMAIL_ADDRESS):
        value = attr.value.strip() if isinstance(attr.value, str) else ''
        if is_valid_san_email(value) and x509.RFC822Name(value) not in names:
            names.append(x509.RFC822Name(value))
    return names


def _common_name(subject: x509.Name) -> str:
    cns = subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return (cns[0].value or '').strip() if cns else ''


def _cn_dns_name(cn: str) -> str | None:
    """The dNSName a CN stands for: any name of the RFC 5280 syntax, one label
    included, and a dotted name with an underscore, so that it is refused."""
    from utils.san_parse import dns_name_syntax_error
    name = cn[:-1] if cn.endswith('.') else cn
    if name and dns_name_syntax_error(name) is None:
        return name
    if '.' in (name[2:] if name.startswith('*.') else name) and '_' in name \
            and _HOST_TOKEN_RE.fullmatch(name):
        return name
    return None


def cn_implied_names(subject: x509.Name, cert_type: str) -> list:
    """SAN entries a subject implies: an IP, address or DNS name CN and every
    valid emailAddress (RFC 5280 §4.1.2.6); none for a CA."""
    from ipaddress import ip_address

    from utils.san_parse import cn_looks_like_email, cn_looks_like_ip
    if cert_type == 'intermediate_ca':
        return []
    names = []
    cn = _common_name(subject)
    if cn_looks_like_ip(cn):
        names.append(x509.IPAddress(ip_address(cn)))
    elif cn_looks_like_email(cn):
        names.append(x509.RFC822Name(cn))
    elif _cn_dns_name(cn):
        names.append(x509.DNSName(_cn_dns_name(cn)))
    names += [n for n in subject_email_names(subject) if n not in names]
    return names


def cn_without_name_notice(subject: x509.Name, cert_type: str) -> str | None:
    """Notice for a CN shaped like a host name that gives no SAN entry."""
    from utils.san_parse import cn_looks_like_ip
    cn = _common_name(subject)
    if (cert_type == 'intermediate_ca' or not _HOST_TOKEN_RE.fullmatch(cn)
            or cn_looks_like_ip(cn) or _cn_dns_name(cn)):
        return None
    return (f'CN {cn!r} is not a DNS name (RFC 5280 §4.2.1.6): '
            'the certificate carries no DNS name for it')


def malformed_dns_names(names) -> list:
    """dNSName values outside the RFC 5280 §4.2.1.6 preferred name syntax."""
    from utils.san_parse import dns_name_syntax_error
    return [n.value for n in names or ()
            if isinstance(n, x509.DNSName) and dns_name_syntax_error(n.value)]


def refuse_malformed_request(subject, names, renewal_of=None) -> None:
    """Refuse a subject past RFC 5280 annex A (``subject`` None: not checked) or
    a dNSName off the preferred syntax; what a renewed certificate holds stays."""
    if subject is not None and not (renewal_of is not None and renewal_of.subject == subject):
        err = subject_bounds_error(subject)
        if err:
            raise RequestRejected(f'CSR subject rejected: {err}')
    prior = set()
    if renewal_of is not None:
        try:
            prior = set(renewal_of.extensions.get_extension_for_class(
                x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName))
        except x509.ExtensionNotFound:
            pass
    malformed = [v for v in malformed_dns_names(names) if v not in prior]
    if malformed:
        raise RequestRejected(
            'Invalid DNS name(s) in the request: ' + ', '.join(repr(v) for v in malformed))
