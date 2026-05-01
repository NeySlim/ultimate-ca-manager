"""
CA Service - Certificate Authority Management
Handles CA creation, import, export, and operations

This is the main facade class that delegates to specialized mixins.
"""
import base64
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from models import db, CA, Certificate, AuditLog
from services.trust_store import TrustStoreService
from config.settings import Config
from utils.file_naming import ca_cert_path, ca_key_path, cleanup_old_files

from .ca_creation import CACreationMixin
from .ca_crud import CAcrudMixin
from .ca_export import CAExportMixin
from .ca_operations import CAOperationsMixin
from .ca_signing import CASigningMixin

logger = logging.getLogger(__name__)

# Import key encryption (optional - fallback if not available)
try:
    from security.encryption import decrypt_private_key, encrypt_private_key
    HAS_ENCRYPTION = True
except ImportError:
    HAS_ENCRYPTION = False
    def decrypt_private_key(data):
        return data
    def encrypt_private_key(data):
        return data


class CAService(
    CACreationMixin,
    CAcrudMixin,
    CAExportMixin,
    CAOperationsMixin,
    CASigningMixin
):
    """
    Service for Certificate Authority operations.

    This class inherits from multiple mixins that provide specialized functionality:
    - CACreationMixin: CA creation and import
    - CAcrudMixin: Basic CRUD operations
    - CAExportMixin: Export operations
    - CAOperationsMixin: Chain, serial, CRL operations
    - CASigningMixin: CSR signing operations

    All methods are delegated to the appropriate mixin.
    """
    pass
