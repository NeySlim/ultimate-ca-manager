"""Parse and validate Subject Alternative Name entries for CSR creation."""
from __future__ import annotations

import re
from ipaddress import ip_address
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from utils.upn_san import is_valid_upn

SanBuckets = Dict[str, List[str]]

_EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9.!#$%&\'*+\/=?^_`{|}~-]+'
    r'@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
    r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
)


def _empty_buckets() -> SanBuckets:
    return {
        'san_dns': [],
        'san_ip': [],
        'san_email': [],
        'san_uri': [],
        'san_upn': [],
    }


def is_valid_san_email(value: str) -> bool:
    if not value or not isinstance(value, str):
        return False
    return bool(_EMAIL_RE.match(value.strip()))


def is_valid_san_uri(value: str) -> bool:
    """RFC 5280 uniformResourceIdentifier — absolute URI with scheme."""
    v = (value or '').strip()
    if not v:
        return False
    parsed = urlparse(v)
    if not parsed.scheme:
        return False
    return bool(re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*$', parsed.scheme))


def _looks_like_ip(value: str) -> bool:
    try:
        ip_address(value.strip())
        return True
    except ValueError:
        return False


def dns_name_syntax_error(value: str) -> str | None:
    """RFC 5280 §4.2.1.6 preferred name syntax (RFC 1034 §3.5, RFC 1123 §2.1):
    LDH labels of 1 to 63, 253 in all, a wildcard only as the whole first label,
    no trailing dot, never the #.#.#.# form of an IP address."""
    v = value if isinstance(value, str) else ''
    body = v[2:] if v.startswith('*.') else v
    if (not body or len(v) > 253 or v.endswith('.')
            or not all(_HOSTNAME_LABEL_RE.fullmatch(label) for label in body.split('.'))):
        return (f'Invalid DNS name: {v!r} (letters, digits and hyphens in dot-separated '
                'labels, a wildcard only as the first label, no trailing dot)')
    if _looks_like_ip(v):
        return f'Invalid DNS name: {v!r} is an IP address, which goes in an IP SAN'
    return None


def normalize_dns_san(value: str) -> Tuple[str, str | None]:
    """(name to issue, error): a U-label becomes its A-label (RFC 9549 §1)."""
    v = (value or '').strip()
    if _looks_like_ip(v):
        return v, (
            f'Use IP type for IP addresses: {v}. '
            'DNS SAN is for hostnames and FQDNs only.'
        )
    if '@' in v:
        return v, f'Use Email type for addresses like {v}'
    if '://' in v:
        return v, f'Use URI type for URIs like {v}'
    if not v.isascii():
        import idna
        prefix, rest = ('*.', v[2:]) if v.startswith('*.') else ('', v)
        try:
            v = prefix + idna.encode(rest, uts46=True).decode('ascii')
        except (idna.IDNAError, UnicodeError, ValueError):
            return v, f'Invalid internationalized DNS name: {value!r}'
    return v, dns_name_syntax_error(v)


def validate_dns_san(value: str) -> str | None:
    return normalize_dns_san(value)[1]


def validate_ip_san(value: str) -> str | None:
    if _looks_like_ip(value):
        return None
    return (
        f'Invalid IP address for IP SAN: {value}. '
        'Use DNS type for hostnames and FQDNs.'
    )


def validate_email_san(value: str) -> str | None:
    if is_valid_san_email(value):
        return None
    if '@' not in value:
        return (
            f'Invalid Email SAN: {value}. '
            'Use DNS type for hostnames; Email type requires user@domain.'
        )
    return f'Invalid email address: {value}'


def validate_uri_san(value: str) -> str | None:
    if is_valid_san_uri(value):
        return None
    if '@' in value and is_valid_san_email(value):
        return f'Use Email type for {value}'
    return (
        f'URI SAN must include a scheme (e.g. https://example.com): {value}'
    )


def validate_upn_san(value: str) -> str | None:
    if is_valid_upn(value):
        return None
    return f'Invalid UPN format: {value} (expected user@domain)'


def strip_wildcard(domain: str) -> str:
    """Drop a leading ``*.`` label, and only that.

    ``lstrip('*.')`` strips *characters*: it eats any run of ``*`` and ``.``
    at the front, so ``*.*.example.com`` comes back as ``example.com`` instead
    of ``*.example.com``. Eight call sites spelled it that way and two spelled
    it correctly, which meant the DNS-01 challenge name a provider published
    and the one the self-check polled could be different names.
    """
    value = domain or ''
    return value[2:] if value.startswith('*.') else value


def san_buckets_from_general_names(general_names) -> SanBuckets:
    """The five SAN buckets UCM persists, read from x509 GeneralName entries.

    Thirteen readers spelled out the same four-branch DNS/IP/email/URI
    cascade, and every one of them dropped the otherName UPN: the column
    exists, but only the signing path ever filled it, so the same certificate
    came back carrying a UPN when UCM issued it and carrying none when UCM
    imported it.
    """
    from cryptography import x509

    buckets = _empty_buckets()
    entries = list(general_names or [])
    for name in entries:
        if isinstance(name, x509.DNSName):
            buckets['san_dns'].append(name.value)
        elif isinstance(name, x509.IPAddress):
            buckets['san_ip'].append(str(name.value))
        elif isinstance(name, x509.RFC822Name):
            buckets['san_email'].append(name.value)
        elif isinstance(name, x509.UniformResourceIdentifier):
            buckets['san_uri'].append(name.value)
    from utils.upn_san import extract_upns_from_san_list
    buckets['san_upn'] = extract_upns_from_san_list(entries)
    return buckets


def san_buckets_from_certificate(cert) -> SanBuckets:
    """:func:`san_buckets_from_general_names` for a parsed certificate.

    A certificate with no SAN extension yields empty buckets, which is what
    every inline reader did with ``ExtensionNotFound``.
    """
    from cryptography import x509

    try:
        ext = cert.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    except x509.ExtensionNotFound:
        return _empty_buckets()
    return san_buckets_from_general_names(ext.value)


def cn_looks_like_email(cn: str) -> bool:
    return is_valid_san_email((cn or '').strip())


# An LDH label of 1 to 63 (RFC 1123 §2.1), hyphen never at an edge, no underscore.
# Use fullmatch: a `$` anchor lets a final newline through.
_HOSTNAME_LABEL_RE = re.compile(r'(?!-)[A-Za-z0-9-]{1,63}(?<!-)')


def looks_like_hostname(value: str) -> bool:
    """Whether *value* has the shape of a dNSName UCM can actually emit.

    ASCII only: a CN such as ``café.example.com`` gives no DNS name; only a
    SAN entry is converted to its A-label (``normalize_dns_san``).
    """
    v = (value or '').strip()
    if not v or len(v) > 253:
        return False
    if v.startswith('*.'):
        v = v[2:]
    if v.endswith('.'):
        v = v[:-1]
    if '.' not in v:
        # One label is a short name, not an FQDN; the CN-derived SAN has
        # always required a dot and this keeps that.
        return False
    return all(_HOSTNAME_LABEL_RE.fullmatch(label) for label in v.split('.'))


def cn_looks_like_hostname(cn: str) -> bool:
    """FQDN / wildcard hostname — not email, not bare IP.

    This used to be ``'.' in value``, which made the docstring wrong and made
    ``CN=Example, Inc.`` a hostname: the CN was copied into a DNS SAN and the
    certificate went out carrying ``DNS:Example, Inc.``, an identity no
    relying party can match. ``CN=café.example.com`` did not even get that far
    — ``x509.DNSName`` raised and the request answered 500.

    The rule that wins is the syntactic one, because this decision *grants* an
    identity. The neighbouring rule in
    ``services/trust_store/constraints_mixin._DNS_LIKE_CN`` deliberately does
    not delegate here: it decides whether a CN carries a DNS identity to
    *check* against a name constraint, and a check must stay inclusive — it
    treats an IP-shaped CN as a DNSName on purpose, which this must not.
    """
    value = (cn or '').strip()
    if not value or cn_looks_like_email(value):
        return False
    if _looks_like_ip(value):
        return False
    return looks_like_hostname(value)


def cn_looks_like_ip(cn: str) -> bool:
    return _looks_like_ip((cn or '').strip())


def auto_san_buckets_from_cn(
    cn: str,
    cert_type: str,
    *,
    subject_email: str | None = None,
) -> SanBuckets:
    """Derive implicit SAN buckets from CN + cert type (issue certificate UI)."""
    buckets = _empty_buckets()
    value = (cn or '').strip()
    if not value:
        return buckets

    if cert_type in ('server', 'combined'):
        if cn_looks_like_hostname(value):
            # The absolute form's root dot has no place in a dNSName (RFC 5280 §4.2.1.6)
            buckets['san_dns'].append(value[:-1] if value.endswith('.') else value)
        elif cn_looks_like_ip(value):
            buckets['san_ip'].append(str(ip_address(value)))

    if cert_type in ('email', 'combined') and cn_looks_like_email(value):
        buckets['san_email'].append(value)

    # RFC 5280 §4.1.2.6: an address in the subject is also an rfc822Name, whatever the type
    subj = (subject_email or '').strip()
    if (
        subj
        and cn_looks_like_email(subj)
        and subj not in buckets['san_email']
    ):
        buckets['san_email'].append(subj)

    return buckets


def validate_typed_san_buckets(buckets: SanBuckets) -> str | None:
    """Reject values that do not match their declared SAN bucket (issue #167 parity)."""
    validators = {
        'san_dns': validate_dns_san,
        'san_ip': validate_ip_san,
        'san_email': validate_email_san,
        'san_uri': validate_uri_san,
        'san_upn': validate_upn_san,
    }
    for key, validate in validators.items():
        for value in buckets.get(key) or []:
            err = validate(value)
            if err:
                return err
    # The names issued are A-labels (RFC 9549 §1)
    buckets['san_dns'] = [normalize_dns_san(v)[0] for v in buckets.get('san_dns') or []]
    return None


def _coerce_san_list(raw) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(s).strip() for s in raw if str(s).strip()]
    if isinstance(raw, str):
        return [s.strip() for s in re.split(r'[,\n;]+', raw) if s.strip()]
    return []


def general_names_from_buckets(buckets: SanBuckets) -> list:
    """x509 GeneralName entries for the DNS, IP, URI and email buckets."""
    from cryptography import x509
    names = [x509.DNSName(v) for v in buckets.get('san_dns') or []]
    names += [x509.IPAddress(ip_address(v)) for v in buckets.get('san_ip') or []]
    names += [x509.UniformResourceIdentifier(v) for v in buckets.get('san_uri') or []]
    names += [x509.RFC822Name(v) for v in buckets.get('san_email') or []]
    return names


def parse_extra_san_payload(data: dict) -> Tuple[SanBuckets, str | None]:
    """Typed names an operator adds when signing a request (#389): DNS, IP,
    email and URI lists, validated like the issue form's."""
    buckets = _empty_buckets()
    if data.get('san_upn'):
        return buckets, 'san_upn cannot be added when signing a request'
    for key in ('san_dns', 'san_ip', 'san_email', 'san_uri'):
        raw = data.get(key)
        if raw is not None and not isinstance(raw, (list, str)):
            return buckets, f'{key} must be a list'
        buckets[key] = _coerce_san_list(raw)
    return buckets, validate_typed_san_buckets(buckets)


def parse_cert_san_payload(data: dict) -> Tuple[SanBuckets, str | None]:
    """Parse/validate SAN fields from POST /api/v2/certificates."""
    buckets = _empty_buckets()
    typed_keys = ('san_dns', 'san_ip', 'san_email', 'san_uri', 'san_upn')
    has_typed = any(data.get(k) for k in typed_keys)

    if has_typed:
        for key in typed_keys:
            buckets[key] = _coerce_san_list(data.get(key))
        return buckets, validate_typed_san_buckets(buckets)

    raw_sans = _coerce_san_list(data.get('san'))
    if not raw_sans:
        return buckets, None

    return parse_csr_san_entries(raw_sans)


def parse_csr_san_entries(entries: List[str]) -> Tuple[SanBuckets, str | None]:
    """Parse SAN list from CSR UI (``DNS:host``, ``IP:1.2.3.4``, …)."""
    buckets = _empty_buckets()

    for raw in entries or []:
        entry = (raw or '').strip()
        if not entry:
            continue
        lower = entry.lower()

        if lower.startswith('email:'):
            val = entry[6:].strip()
            if not val:
                continue
            err = validate_email_san(val)
            if err:
                return buckets, err
            buckets['san_email'].append(val)
            continue

        if lower.startswith('uri:'):
            val = entry[4:].strip()
            if not val:
                continue
            err = validate_uri_san(val)
            if err:
                return buckets, err
            buckets['san_uri'].append(val)
            continue

        if lower.startswith('upn:'):
            val = entry[4:].strip()
            if not val:
                continue
            err = validate_upn_san(val)
            if err:
                return buckets, err
            buckets['san_upn'].append(val)
            continue

        if lower.startswith('ip:'):
            val = re.sub(r'^IP:\s*', '', entry, flags=re.IGNORECASE).strip()
            if not val:
                continue
            err = validate_ip_san(val)
            if err:
                return buckets, err
            buckets['san_ip'].append(str(ip_address(val)))
            continue

        if lower.startswith('dns:'):
            val = re.sub(r'^DNS:\s*', '', entry, flags=re.IGNORECASE).strip()
            if not val:
                continue
            val, err = normalize_dns_san(val)
            if err:
                return buckets, err
            buckets['san_dns'].append(val)
            continue

        # Legacy / unprefixed: auto-detect
        if _looks_like_ip(entry):
            buckets['san_ip'].append(str(ip_address(entry)))
        elif '@' in entry and is_valid_san_email(entry):
            buckets['san_email'].append(entry)
        elif is_valid_san_uri(entry):
            buckets['san_uri'].append(entry)
        elif is_valid_upn(entry):
            buckets['san_upn'].append(entry)
        else:
            val, err = normalize_dns_san(entry)
            if err:
                return buckets, err
            buckets['san_dns'].append(val)

    return buckets, None
