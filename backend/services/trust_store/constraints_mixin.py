"""
Name constraints mixin for TrustStoreService
"""
import ipaddress
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID

from .validation_helpers import _name_value, _name_matches_subtree


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

    @staticmethod
    def _validate_name_constraints(ca_cert, subject, san_names=None):
        """Validate subject and SANs against CA's NameConstraints (RFC 5280 §4.2.1.10)."""
        try:
            nc_ext = ca_cert.extensions.get_extension_for_oid(ExtensionOID.NAME_CONSTRAINTS)
            nc = nc_ext.value
        except x509.ExtensionNotFound:
            return

        permitted = nc.permitted_subtrees or []
        excluded = nc.excluded_subtrees or []

        if not permitted and not excluded:
            return

        names_to_check = []

        try:
            cn_attrs = subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            if cn_attrs:
                cn_val = cn_attrs[0].value
                if '@' in cn_val:
                    names_to_check.append(x509.RFC822Name(cn_val))
                else:
                    names_to_check.append(x509.DNSName(cn_val))
        except Exception:
            pass

        if san_names:
            names_to_check.extend(san_names)

        for name in names_to_check:
            for exc in excluded:
                if _name_matches_subtree(name, exc):
                    raise ValueError(
                        f"Name '{_name_value(name)}' is excluded by CA NameConstraints"
                    )

            if permitted:
                same_type_permitted = [p for p in permitted if type(p) == type(name)]
                if same_type_permitted:
                    if not any(_name_matches_subtree(name, perm) for perm in same_type_permitted):
                        raise ValueError(
                            f"Name '{_name_value(name)}' is not in CA's permitted NameConstraints"
                        )
