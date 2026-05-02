"""
Users API v2.0 - Modular Routes Package

This package contains routes for /api/v2/users/*
split into thematic modules.
"""

import logging
import re
from flask import Blueprint

logger = logging.getLogger(__name__)

# Create the blueprint here
bp = Blueprint('users_v2', __name__)

# Password policy constants (shared across sub-modules)
MIN_PASSWORD_LENGTH = 8
PASSWORD_REQUIREMENTS = """Password must:
- Be at least 8 characters long
- Contain at least one uppercase letter
- Contain at least one lowercase letter
- Contain at least one number
- Contain at least one special character (!@#$%^&*(),.?":{}|<>)"""

# Import password policy
try:
    from security.password_policy import validate_password, get_password_strength, get_policy_requirements
    HAS_PASSWORD_POLICY = True
except ImportError:
    HAS_PASSWORD_POLICY = False


def validate_password_strength(password, username=None):
    """
    SECURITY: Validate password meets security requirements
    Returns (is_valid, error_message)
    """
    # Use new security module if available
    if HAS_PASSWORD_POLICY:
        is_valid, errors = validate_password(password, username=username)
        if not is_valid:
            return False, errors[0] if errors else "Invalid password"
        return True, None

    # Legacy validation
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    return True, None


# Note: Route modules are imported in api/v2/__init__.py to register routes
# This avoids circular import issues
