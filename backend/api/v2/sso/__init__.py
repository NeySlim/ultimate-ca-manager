"""
SSO API v2 - Modular Package

Original file: api/v2/sso.py (1843 lines)
Split into 8 modular files for maintainability.
"""

from flask import Blueprint, request, redirect, session, Response
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.ssrf_protection import validate_url_not_cloud_metadata
from models import db, User, Certificate
from models.sso import SSOProvider, SSOSession
from services.audit_service import AuditService
from datetime import datetime, timedelta
import hmac
import json
import base64
import secrets as py_secrets
import traceback
import urllib.parse
import requests as http_requests
from defusedxml.lxml import fromstring as safe_fromstring
from lxml import etree

import logging
import os
import tempfile
from utils.datetime_utils import utc_now, utc_isoformat

logger = logging.getLogger(__name__)

# Blueprint and constants
bp = Blueprint('sso_pro', __name__)
VALID_ROLES = {'admin', 'operator', 'auditor', 'viewer'}

# Import all modules to register their routes
from . import helpers
from . import providers
from . import connection_tests
from . import mapping_tests
from . import sessions
from . import saml_routes
from . import login_routes
from . import ldap_routes

# Re-export commonly used helper functions for backward compatibility with tests
from .helpers import (
    _get_ssl_verify,
    _cleanup_ssl_verify,
    _build_ldap_tls,
    _encrypt_ldap_password,
    _decrypt_ldap_password,
    _parse_json_field,
    _get_ldap_lockout_settings,
    _check_ldap_lockout,
    _record_ldap_failed_attempt,
    _clear_ldap_failed_attempts,
    _resolve_role_from_mapping,
    _resolve_role,
)
from .ldap_routes import _get_or_create_sso_user

__all__ = [
    'bp',
    'VALID_ROLES',
    # Helper functions
    '_get_ssl_verify',
    '_cleanup_ssl_verify',
    '_build_ldap_tls',
    '_encrypt_ldap_password',
    '_decrypt_ldap_password',
    '_parse_json_field',
    '_get_ldap_lockout_settings',
    '_check_ldap_lockout',
    '_record_ldap_failed_attempt',
    '_clear_ldap_failed_attempts',
    '_resolve_role_from_mapping',
    '_resolve_role',
    '_get_or_create_sso_user',
]
