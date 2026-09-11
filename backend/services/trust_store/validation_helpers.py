"""
Name validation helpers for TrustStoreService
"""
import ipaddress
from urllib.parse import urlsplit
from cryptography import x509


def _name_value(name):
    """Extract string value from an x509.GeneralName."""
    if isinstance(name, x509.DNSName):
        return name.value
    elif isinstance(name, x509.RFC822Name):
        return name.value
    elif isinstance(name, x509.IPAddress):
        return str(name.value)
    return str(name)


_UPN_OID = x509.ObjectIdentifier('1.3.6.1.4.1.311.20.2.3')


def _dns_matches(name_val: str, constraint_val: str) -> bool:
    """DNS subtree rule: "example.com" covers itself and its subdomains,
    ".example.com" the subdomains only."""
    name_val = name_val.lower()
    constraint_val = constraint_val.lower()
    if name_val == constraint_val:
        return True
    if constraint_val.startswith('.'):
        return name_val.endswith(constraint_val) or name_val == constraint_val[1:]
    return name_val.endswith('.' + constraint_val)


def _der_utf8(value) -> str:
    """The text of a DER UTF8String (an otherName value), tolerant of a
    raw string."""
    if isinstance(value, str):
        return value
    data = bytes(value)
    if len(data) >= 2 and data[0] == 0x0C:
        length = data[1]
        offset = 2
        if length & 0x80:
            n = length & 0x7F
            length = int.from_bytes(data[2:2 + n], 'big')
            offset = 2 + n
        return data[offset:offset + length].decode('utf-8', errors='replace')
    return data.decode('utf-8', errors='replace')


def _name_matches_subtree(name, subtree):
    """Check if a GeneralName matches a NameConstraints subtree (RFC 5280 §4.2.1.10).

    DNS: "example.com" matches "example.com" and "sub.example.com"
    Email: "user@example.com" = that mailbox only; "example.com" = mailboxes on
        that host only; ".example.com" = mailboxes in the domain (not the host
        itself). This mirrors what OpenSSL enforces at chain validation.
    IP: network matching (e.g. 10.0.0.0/8 matches 10.1.2.3)
    """
    if type(name) != type(subtree):
        return False

    if isinstance(name, x509.DNSName):
        return _dns_matches(name.value, subtree.value)
    elif isinstance(name, x509.UniformResourceIdentifier):
        # RFC 5280 §4.2.1.10: a URI constraint names a host or a domain
        # (leading dot); it applies to the URI's host part
        host = urlsplit(name.value).hostname or ''
        return bool(host) and _dns_matches(host, subtree.value)
    elif isinstance(name, x509.DirectoryName):
        # The subtree is a prefix of the name (RDN by RDN)
        prefix = list(subtree.value.rdns)
        return list(name.value.rdns)[:len(prefix)] == prefix
    elif isinstance(name, x509.OtherName):
        if name.type_id != subtree.type_id:
            return False
        if name.type_id == _UPN_OID:
            # A UPN (user@realm) is constrained like an e-mail address
            upn = _der_utf8(name.value).lower()
            constraint_val = _der_utf8(subtree.value).lower()
            domain = upn.rpartition('@')[2] if '@' in upn else upn
            if '@' in constraint_val:
                return upn == constraint_val
            if constraint_val.startswith('.'):
                return domain.endswith(constraint_val)
            return domain == constraint_val
        return name.value == subtree.value

    elif isinstance(name, x509.RFC822Name):
        name_val = name.value.lower()
        constraint_val = subtree.value.lower()
        # Domain is everything after the LAST '@' (a quoted local part may
        # contain one); cryptography already rejects bare multi-'@' addresses.
        name_domain = name_val.rpartition('@')[2] if '@' in name_val else name_val
        if '@' in constraint_val:
            # mailbox form: the exact address, nothing else
            return name_val == constraint_val
        if constraint_val.startswith('.'):
            # domain form: any host within the domain, but not the domain itself
            return name_domain.endswith(constraint_val)
        # host form: mail addressed to that specific host only
        return name_domain == constraint_val

    elif isinstance(name, x509.IPAddress):
        try:
            name_addr = name.value
            constraint_net = subtree.value
            if hasattr(constraint_net, 'network_address'):
                if hasattr(name_addr, 'network_address'):
                    return name_addr.subnet_of(constraint_net)
                return name_addr in constraint_net
            return name_addr == constraint_net
        except Exception:
            return False

    return False
