"""Small RFC 4514 DN helpers built on ldap3's parser."""

from string import hexdigits

from cryptography.x509.oid import NameOID
from ldap3.utils.dn import parse_dn as ldap_parse_dn


def _normalize_quoted_values(dn: str) -> str:
    """Convert legacy quoted values to RFC 4514 escaped values."""
    normalized = []
    quoted = False
    escaped = False

    for char in dn:
        if escaped:
            normalized.append(char)
            escaped = False
            continue
        if char == '\\':
            normalized.append(char)
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
            continue
        if quoted and char in (',', '+'):
            normalized.append('\\')
        normalized.append(char)

    if quoted:
        raise ValueError('Unterminated quoted DN value')
    return ''.join(normalized)


def _unescape_value(value: str) -> str:
    """Decode RFC 4514 character and hexadecimal escapes."""
    decoded = bytearray()
    index = 0
    while index < len(value):
        char = value[index]
        if char != '\\':
            decoded.extend(char.encode('utf-8'))
            index += 1
            continue

        if index + 1 >= len(value):
            raise ValueError('Invalid trailing escape in DN value')
        if (
            index + 2 < len(value)
            and value[index + 1] in hexdigits
            and value[index + 2] in hexdigits
        ):
            decoded.append(int(value[index + 1:index + 3], 16))
            index += 3
        else:
            decoded.extend(value[index + 1].encode('utf-8'))
            index += 2

    try:
        return decoded.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('Invalid UTF-8 escape in DN value') from exc


def parse_dn(dn: str) -> list[list[tuple[str, str]]]:
    """Parse a DN into RDNs, preserving multivalued RDN boundaries."""
    if not isinstance(dn, str) or not dn.strip():
        raise ValueError('DN must be a non-empty string')

    try:
        components = ldap_parse_dn(
            _normalize_quoted_values(dn.strip()),
            escape=False,
            strip=True,
        )
    except Exception as exc:
        raise ValueError('Invalid distinguished name') from exc

    rdns = []
    current_rdn = []
    for attribute, value, separator in components:
        current_rdn.append((attribute, value))
        if separator != '+':
            rdns.append(current_rdn)
            current_rdn = []
    if current_rdn:
        rdns.append(current_rdn)
    return rdns


def get_dn_attribute(dn: str, attribute: str) -> str | None:
    """Return the first matching attribute value from a DN."""
    wanted = attribute.casefold()
    for rdn in parse_dn(dn):
        for name, value in rdn:
            if name.casefold() == wanted:
                return _unescape_value(value)
    return None


def _split_unescaped(text: str, separators: str) -> list[str]:
    """Split on the separators a backslash does not escape, keeping the escapes."""
    parts, current, escaped = [], [], False
    for char in text:
        if escaped:
            escaped = False
        elif char == '\\':
            escaped = True
        elif char in separators:
            parts.append(''.join(current))
            current = []
            continue
        current.append(char)
    parts.append(''.join(current))
    return parts


def stored_dn_attribute(dn, types) -> str | None:
    """The first value, in the string, of an attribute named in `types` (any case), or None.
    Reads what `get_dn_attribute` reads, and also what RFC 4514 allows and ldap3 refuses:
    a numeric OID type, an unescaped '=', an empty value."""
    if not dn:
        return None
    wanted = {t.casefold() for t in types}
    try:
        dn = _normalize_quoted_values(dn)
    except ValueError:
        pass
    for ava in _split_unescaped(dn, ',+'):
        attribute, sep, value = ava.partition('=')
        if not sep or attribute.strip().casefold() not in wanted:
            continue
        value = value.lstrip()
        while value.endswith(' ') and not value.endswith('\\ '):
            value = value[:-1]
        try:
            return _unescape_value(value)
        except ValueError:
            return value
    return None


def get_parent_dn(dn: str) -> str:
    """Return the DN after removing its complete first RDN."""
    rdns = parse_dn(dn)
    return ','.join(
        '+'.join(f'{attribute}={value}' for attribute, value in rdn)
        for rdn in rdns[1:]
    )


def subject_common_name(subject) -> str | None:
    """The FIRST commonName of an x509 subject, or None.

    Use this whenever an x509 Name object is in hand. Do NOT derive a CN by
    splitting `subject.rfc4514_string()` on ',' and taking the first "CN="
    token, which is what several call sites did: RFC 4514 s2.1 emits RDNs in
    REVERSE order, so that token is the LAST commonName. A subject of
    `CN=web.example.com, CN=admin.example.com` recorded `admin.example.com`
    as the certificate's identity, while ACME finalize validated
    `web.example.com` -- the name checked and the name recorded disagreed
    precisely when a subject carried more than one CN. Splitting on ',' is
    independently wrong because RFC 4514 escapes a comma inside a value as
    "\\,", which a plain split does not honour.

    `get_dn_attribute()` above is the counterpart for when only the STRING
    exists (an LDAP DN, or a subject already persisted as text); it unescapes
    correctly but cannot recover the original ordering, so prefer this one
    whenever the object is available.
    """
    attrs = subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return attrs[0].value if attrs else None
