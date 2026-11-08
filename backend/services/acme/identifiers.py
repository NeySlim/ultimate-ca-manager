"""What an ACME order may name, judged once for both front doors.

UCM answers ACME on two paths: its own server (`api/acme/acme_api.py`), which
issues from a local authority, and the proxy (`api/acme/acme_proxy_api.py`),
which relays to an upstream CA and answers the dns-01 challenge itself. Both
take an `identifiers` array straight from an unauthenticated client.

The syntax check lived on the server only. On the proxy the value went
unexamined into `AcmeClientOrder.domains` and into the DNS provider API as a
record name, and was forwarded verbatim upstream. That is the difference this
module removes: the rules are here, and both doors call them.

The label rule is the one certificates are issued under (RFC 5280 §4.2.1.6).
It is syntax, not policy: a name is refused for carrying a port, userinfo, a
scheme, a path, whitespace, an underscore, an over-long label or an empty one,
never for pointing somewhere private.
`localhost`, `host-1.internal.lan` and RFC1918 targets stay acceptable at
order time -- UCM is deployed on LAN and those are the ordinary case. Whether
a *challenge* may be fetched from a given address is a separate decision, made
later and with the deliberately permissive helpers in
`utils/ssrf_protection.py`.
"""

import re
from typing import Any, Dict, Optional, Tuple

# The label rule certificates are issued under (utils.san_parse); a single
# trailing root dot is still tolerated here, as before.
from utils.san_parse import _HOSTNAME_LABEL_RE as _DNS_LABEL_RE
from utils.san_parse import dns_name_syntax_error


def is_valid_dns_identifier(value: Any) -> bool:
    """Whether `value` is a syntactically valid RFC 8555 §7.1.4 DNS identifier.

    The 'dns' branch used to validate nothing, so a value carrying a port or
    userinfo ("169.254.169.254:80", "evil@169.254.169.254") was accepted. Such
    a value is unresolvable as a hostname — which made the challenge validator's
    private-address guard pass it — but the HTTP client then re-parses it as a
    URL authority, strips the port/userinfo and reaches the address behind it.
    """
    if not isinstance(value, str) or not value or len(value) > 253:
        return False
    if value.startswith('*.'):
        # Wildcard order: the prefix is stripped later, during authorization
        # normalization, so it must be tolerated here.
        value = value[2:]
    if value.endswith('.'):
        value = value[:-1]          # tolerate a single trailing root dot
    if not value:
        return False
    return all(_DNS_LABEL_RE.fullmatch(label) for label in value.split('.'))


def validate_acme_identifier(identifier: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate a single ACME identifier (RFC 8555 DNS + RFC 8738 IP).

    Normalizes IP identifier values to their canonical form in place.

    Args:
        identifier: dict with 'type' and 'value' keys

    Returns:
        Tuple of (is_valid, acme_error_type, detail). When is_valid is True,
        error_type and detail are None and ``identifier['value']`` may have
        been rewritten to its canonical form.
    """
    if (
        not isinstance(identifier, dict)
        or 'type' not in identifier
        or 'value' not in identifier
    ):
        return False, 'malformed', 'Valid identifier required'

    # Support both DNS (RFC 8555) and IP (RFC 8738) identifiers
    if identifier['type'] not in ('dns', 'ip'):
        return False, 'unsupportedIdentifier', f'Identifier type {identifier["type"]} not supported'

    # Validate DNS name syntax for DNS identifiers (RFC 8555 §7.1.4)
    if identifier['type'] == 'dns':
        if not is_valid_dns_identifier(identifier['value']):
            return False, 'malformed', 'Malformed DNS identifier value'

    # Validate IP address format for IP identifiers (RFC 8738)
    if identifier['type'] == 'ip':
        from utils.acme_ip import validate_ip_address
        is_valid, result = validate_ip_address(identifier['value'])
        if not is_valid:
            return False, 'malformed', result
        # Normalize to canonical form
        identifier['value'] = result

    return True, None, None


# ---------------------------------------------------------------------------
# The outbound client's own rule
#
# Ordering FROM an upstream CA is a different question from answering an order:
# UCM chooses the names it asks for, so it applies the stricter public-CA shape
# (at least two labels, no trailing dot) and refuses upfront what
# Let's Encrypt would refuse anyway. That rule was written out twice — once in
# the order route, once in the preflight report — and only the route carried the
# length cap, so the preflight answered "Domain validation OK" for a name the
# order then rejected with a 400. One rule, both readers.
# ---------------------------------------------------------------------------

CLIENT_MAX_DOMAIN_LENGTH = 253

# Labels of 1-63 chars (alnum + hyphen, no leading/trailing hyphen), two or
# more of them, with an optional leading "*." for wildcards.
_CLIENT_LABEL = r'(?!-)[A-Za-z0-9-]{1,63}(?<!-)'
_CLIENT_FQDN_RE = re.compile(rf'^(\*\.)?({_CLIENT_LABEL}\.)+{_CLIENT_LABEL}$')


def normalize_client_identifier(value: Any) -> Tuple[Optional[str], bool, Optional[str]]:
    """Judge one name the outbound ACME client is about to order.

    Returns ``(normalized_value, is_ip_identifier, problem)``. ``problem`` is
    None when the name is acceptable, otherwise it is the operator-facing
    message — the same wording the order route has always returned.
    """
    if not isinstance(value, str) or not value:
        return None, False, 'Invalid domain (empty or not a string)'

    from utils.acme_ip import normalize_ip_for_identifier
    normalized_ip = normalize_ip_for_identifier(value)
    if normalized_ip is not None:
        return normalized_ip, True, None

    if len(value) > CLIENT_MAX_DOMAIN_LENGTH:
        return None, False, (
            f'Invalid domain (>{CLIENT_MAX_DOMAIN_LENGTH} chars): {value[:60]}...'
        )
    # Two labels on top of the server's RFC 5280 syntax; fullmatch, since `$` lets a newline through
    if not _CLIENT_FQDN_RE.fullmatch(value) or dns_name_syntax_error(value):
        return None, False, f'Invalid domain syntax: {value}'
    return value, False, None
