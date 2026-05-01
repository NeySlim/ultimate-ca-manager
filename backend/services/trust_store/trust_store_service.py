"""
Trust Store Service - Main Facade Class

This is the main TrustStoreService class that inherits from all specialized mixins.
Each mixin provides a cohesive set of related cryptographic operations.
"""
import base64
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import pkcs12
import ipaddress

from .constants import KEY_TYPES, HASH_ALGORITHMS
from .validation_helpers import _name_value, _name_matches_subtree
from .constraints_mixin import ConstraintsMixin
from .key_operations_mixin import KeyOperationsMixin
from .subject_building_mixin import SubjectBuildingMixin
from .fingerprint_mixin import FingerprintMixin
from .ca_certificate_creation_mixin import CACertificateCreationMixin
from .certificate_creation_mixin import CertificateCreationMixin
from .csr_operations_mixin import CSROperationsMixin
from .parsing_mixin import ParsingMixin
from .export_operations_mixin import ExportOperationsMixin
from .crl_operations_mixin import CRLOperationsMixin


class TrustStoreService(
    ConstraintsMixin,
    KeyOperationsMixin,
    SubjectBuildingMixin,
    FingerprintMixin,
    CACertificateCreationMixin,
    CertificateCreationMixin,
    CSROperationsMixin,
    ParsingMixin,
    ExportOperationsMixin,
    CRLOperationsMixin
):
    """
    Service for all cryptographic operations.
    
    This class inherits from multiple mixins that provide specialized functionality:
    - ConstraintsMixin: Name constraints validation
    - KeyOperationsMixin: Private key generation
    - SubjectBuildingMixin: X.509 Name/Subject building
    - FingerprintMixin: Certificate fingerprint calculation
    - CACertificateCreationMixin: CA certificate creation
    - CertificateCreationMixin: End-entity certificate creation
    - CSROperationsMixin: CSR generation and signing
    - ParsingMixin: Certificate parsing
    - ExportOperationsMixin: PKCS#12 export
    - CRLOperationsMixin: CRL generation
    
    All methods are inherited from the appropriate mixin.
    """
    pass
