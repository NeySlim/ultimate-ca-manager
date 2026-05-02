"""
Name validation helpers for TrustStoreService
"""
import ipaddress
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


def _name_matches_subtree(name, subtree):
    """Check if a GeneralName matches a NameConstraints subtree (RFC 5280 §4.2.1.10).

    DNS: ".example.com" matches "sub.example.com" and "example.com"
    Email: ".example.com" matches "user@example.com" and "user@sub.example.com"
    IP: network matching (e.g. 10.0.0.0/8 matches 10.1.2.3)
    """
    if type(name) != type(subtree):
        return False

    if isinstance(name, x509.DNSName):
        name_val = name.value.lower()
        constraint_val = subtree.value.lower()
        if name_val == constraint_val:
            return True
        if constraint_val.startswith('.'):
            return name_val.endswith(constraint_val) or name_val == constraint_val[1:]
        return name_val == constraint_val or name_val.endswith('.' + constraint_val)

    elif isinstance(name, x509.RFC822Name):
        name_val = name.value.lower()
        constraint_val = subtree.value.lower()
        if name_val == constraint_val:
            return True
        if constraint_val.startswith('.'):
            domain = name_val.split('@')[-1] if '@' in name_val else name_val
            return domain.endswith(constraint_val) or domain == constraint_val[1:]
        if '@' not in constraint_val:
            domain = name_val.split('@')[-1] if '@' in name_val else name_val
            return domain == constraint_val or domain.endswith('.' + constraint_val)
        return False

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
