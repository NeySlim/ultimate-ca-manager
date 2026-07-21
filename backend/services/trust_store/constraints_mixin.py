"""
Name constraints mixin for TrustStoreService
"""
import ipaddress
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID

from .validation_helpers import _name_value, _name_matches_subtree


def _validate_against_cert(ca_cert, names_to_check):
    """Validate names against a single CA cert's NameConstraints. Raises ValueError."""
    try:
        nc_ext = ca_cert.extensions.get_extension_for_oid(ExtensionOID.NAME_CONSTRAINTS)
        nc = nc_ext.value
    except x509.ExtensionNotFound:
        return

    permitted = nc.permitted_subtrees or []
    excluded = nc.excluded_subtrees or []
    if not permitted and not excluded:
        return

    excluded_names = []
    outside_permitted_names = []
    for name in names_to_check:
        name_value = _name_value(name)
        if any(_name_matches_subtree(name, subtree) for subtree in excluded):
            if name_value not in excluded_names:
                excluded_names.append(name_value)
            continue

        same_type_permitted = [
            subtree for subtree in permitted if type(subtree) is type(name)
        ]
        if same_type_permitted and not any(
            _name_matches_subtree(name, subtree) for subtree in same_type_permitted
        ):
            if name_value not in outside_permitted_names:
                outside_permitted_names.append(name_value)

    errors = []
    if excluded_names:
        errors.append(
            "Names excluded by CA NameConstraints: " + ", ".join(excluded_names)
        )
    if outside_permitted_names:
        errors.append(
            "Names outside CA permitted NameConstraints: "
            + ", ".join(outside_permitted_names)
        )
    if errors:
        raise ValueError("; ".join(errors))


def _chain_certs_above(ca_cert):
    """Return the issuer CA certs above ca_cert, walking the DB CA table by
    subject/issuer name. Best-effort: on any error, returns what was collected
    so far (the direct-CA check still applies). Bounded to avoid cycles."""
    chain = []
    try:
        import base64
        from models import CA
    except Exception:
        return chain

    current = ca_cert
    seen = set()
    for _ in range(16):  # depth guard
        issuer_bytes = current.issuer.public_bytes()
        subject_bytes = current.subject.public_bytes()
        if issuer_bytes == subject_bytes:
            break  # self-signed root
        if issuer_bytes in seen:
            break  # cycle guard
        seen.add(issuer_bytes)
        parent = None
        try:
            for ca in CA.query.filter(CA.crt.isnot(None)).all():
                try:
                    pem = base64.b64decode(ca.crt)
                    cert = x509.load_pem_x509_certificate(pem)
                except Exception:
                    continue
                if cert.subject.public_bytes() == issuer_bytes:
                    parent = cert
                    break
        except Exception:
            break
        if parent is None:
            break
        chain.append(parent)
        current = parent
    return chain


def validate_name_constraints(ca_cert, subject, san_names=None):
    """Validate subject and SANs against the NameConstraints of the whole CA
    chain (RFC 5280 §4.2.1.10) — the direct issuer AND every CA above it, so a
    constraint set on a root is enforced even when an intermediate carries none.
    """
    names_to_check = []
    try:
        cn_attrs = subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if cn_attrs:
            cn_value = cn_attrs[0].value
            if '@' in cn_value:
                names_to_check.append(x509.RFC822Name(cn_value))
            else:
                names_to_check.append(x509.DNSName(cn_value))
    except Exception:
        pass

    if san_names:
        names_to_check.extend(san_names)

    if not names_to_check:
        return

    _validate_against_cert(ca_cert, names_to_check)
    for parent_cert in _chain_certs_above(ca_cert):
        _validate_against_cert(parent_cert, names_to_check)


class ConstraintsMixin:
    """Name constraints validation mixin"""

    @staticmethod
    def _build_general_subtrees(constraints):
        """Build GeneralSubtree list from constraint dicts for NameConstraints."""
        if not constraints:
            return None
        subtrees = []
        for c in constraints:
            ctype = c.get('type', '').lower()
            value = c.get('value', '')
            if not value:
                continue
            if ctype == 'dns':
                subtrees.append(x509.DNSName(value))
            elif ctype == 'ip':
                subtrees.append(x509.IPAddress(ipaddress.ip_network(value)))
            elif ctype == 'email':
                subtrees.append(x509.RFC822Name(value))
        return subtrees if subtrees else None

    _validate_name_constraints = staticmethod(validate_name_constraints)
