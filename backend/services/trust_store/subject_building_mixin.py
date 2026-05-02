"""
Subject building mixin for TrustStoreService
"""
from cryptography import x509
from cryptography.x509.oid import NameOID
from typing import Dict


class SubjectBuildingMixin:
    """X.509 Name/Subject building mixin"""

    @staticmethod
    def build_subject(dn_dict: Dict[str, str]) -> x509.Name:
        """Build X.509 subject/issuer name from dictionary."""
        attributes = []

        oid_map = {
            'C': NameOID.COUNTRY_NAME,
            'ST': NameOID.STATE_OR_PROVINCE_NAME,
            'L': NameOID.LOCALITY_NAME,
            'O': NameOID.ORGANIZATION_NAME,
            'OU': NameOID.ORGANIZATIONAL_UNIT_NAME,
            'CN': NameOID.COMMON_NAME,
            'email': NameOID.EMAIL_ADDRESS,
        }

        order = ['C', 'ST', 'L', 'O', 'OU', 'CN', 'email']

        for field in order:
            if field in dn_dict and dn_dict[field]:
                attributes.append(
                    x509.NameAttribute(oid_map[field], str(dn_dict[field]))
                )

        return x509.Name(attributes)
