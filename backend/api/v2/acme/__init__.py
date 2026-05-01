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


from . import settings, accounts, orders, eab  # noqa: F401, E402
