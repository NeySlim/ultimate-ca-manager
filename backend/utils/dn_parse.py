"""Small RFC 4514 DN helpers built on ldap3's parser."""

from string import hexdigits

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


def get_parent_dn(dn: str) -> str:
    """Return the DN after removing its complete first RDN."""
    rdns = parse_dn(dn)
    return ','.join(
        '+'.join(f'{attribute}={value}' for attribute, value in rdn)
        for rdn in rdns[1:]
    )
