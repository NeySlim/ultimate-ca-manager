"""
ACME Configuration Routes v2.0
/api/acme/* - ACME settings and stats
"""
import logging
import json
import base64
import hashlib

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge, SystemConfig, CA, Certificate
from models.acme_models import DnsProvider
from services.audit_service import AuditService
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from utils.datetime_utils import utc_isoformat

logger = logging.getLogger('ucm.acme')

bp = Blueprint('acme_v2', __name__)


def resolve_acme_account(account_id):
    """Resolve an ACME account by either numeric PK ``id`` or RFC 8555 ``account_id``.

    Frontend admin UI passes the numeric PK (``account.id``) when a user clicks
    a row in the accounts table. The RFC 8555 ACME server uses the opaque
    ``account_id`` string in protocol URLs (``/acme/acct/<account_id>``).
    Both must work on admin endpoints to avoid 404s when clicking a row.

    Returns the AcmeAccount or None.
    """
    # Try numeric PK first (admin UI path)
    if isinstance(account_id, str) and account_id.isdigit():
        acc = AcmeAccount.query.get(int(account_id))
        if acc:
            return acc
    elif isinstance(account_id, int):
        acc = AcmeAccount.query.get(account_id)
        if acc:
            return acc
    # Fallback to RFC 8555 account_id string
    return AcmeAccount.query.filter_by(account_id=str(account_id)).first()


from . import settings, accounts, orders, eab  # noqa: F401, E402
