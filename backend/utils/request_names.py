"""What a request may put in a certificate's subject and SAN, whatever path
it takes (issue form, Sign CSR, EST, SCEP, ACME, WSTEP)."""
from __future__ import annotations

import re

from cryptography import x509
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
_COUNTRY_RE = re.compile(r'^[A-Za-z]{2}$')


def subject_bounds_error(subject: x509.Name) -> str | None:
    """First attribute outside RFC 5280 annex A (C: two letters, RFC 4519 §2.2)."""
    for attr in subject:
        value = attr.value if isinstance(attr.value, str) else ''
        if attr.oid == NameOID.COUNTRY_NAME:
            if not _COUNTRY_RE.match(value):
                return f'C must be a two-letter country code (ISO 3166), got {value!r}'
            continue
        bound = _SUBJECT_BOUNDS.get(attr.oid)
        if bound and len(value) > bound[1]:
            return f'{bound[0]} must be {bound[1]} characters or less'
    return None


def cn_implied_names(subject: x509.Name, cert_type: str) -> list:
    """SAN entries a subject implies: a hostname, IP or address CN (the issue
    form's rule) and every emailAddress (RFC 5280 §4.1.2.6); none for a CA."""
    from ipaddress import ip_address

    from utils.san_parse import cn_looks_like_email, cn_looks_like_hostname, cn_looks_like_ip
    if cert_type == 'intermediate_ca':
        return []
    names = []
    cns = subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    cn = (cns[0].value or '').strip() if cns else ''
    if cn_looks_like_ip(cn):
        names.append(x509.IPAddress(ip_address(cn)))
    elif cn_looks_like_email(cn):
        names.append(x509.RFC822Name(cn))
    elif cn_looks_like_hostname(cn):
        names.append(x509.DNSName(cn[:-1] if cn.endswith('.') else cn))
    for attr in subject.get_attributes_for_oid(NameOID.EMAIL_ADDRESS):
        email = x509.RFC822Name(attr.value) if attr.value else None
        if email is not None and email not in names:
            names.append(email)
    return names


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
