"""
Account Management Routes v2.0
/api/account/* - Profile, API Keys, Sessions

Focus: API Keys management (CRUD)
"""

from flask import Blueprint, request, g, current_app
from auth.unified import AuthManager, require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from models.api_key import APIKey
from models import db
from services.audit_service import AuditService
from datetime import datetime
from utils.datetime_utils import utc_isoformat
import pyotp
import re
import qrcode
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('account_v2', __name__)

from . import profile, password, apikeys, twofa, sessions  # noqa: F401, E402
