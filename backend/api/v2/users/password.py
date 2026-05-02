"""
Users Password Policy Routes
"""

from . import bp, HAS_PASSWORD_POLICY, MIN_PASSWORD_LENGTH, PASSWORD_REQUIREMENTS
from flask import request
from utils.response import success_response

try:
    from security.password_policy import get_password_strength, get_policy_requirements
except ImportError:
    pass


@bp.route('/api/v2/users/password-policy', methods=['GET'])
def get_password_policy():
    """
    Get password policy requirements

    GET /api/v2/users/password-policy

    Returns password requirements for UI display
    """
    if HAS_PASSWORD_POLICY:
        requirements = get_policy_requirements()
    else:
        requirements = {
            'min_length': MIN_PASSWORD_LENGTH,
            'max_length': 128,
            'rules': PASSWORD_REQUIREMENTS.split('\n')[1:]  # Skip header
        }

    return success_response(data=requirements)


@bp.route('/api/v2/users/password-strength', methods=['POST'])
def check_password_strength():
    """
    Check password strength (no auth required - used during registration/password change)

    POST /api/v2/users/password-strength
    {"password": "test123"}

    Returns strength score and feedback
    """
    data = request.get_json() or {}
    password = data.get('password', '')

    if HAS_PASSWORD_POLICY:
        result = get_password_strength(password)
    else:
        # Basic fallback
        length = len(password)
        score = min(100, length * 10)
        level = 'weak' if score < 40 else 'fair' if score < 60 else 'good' if score < 80 else 'strong'
        result = {'score': score, 'level': level, 'feedback': []}

    return success_response(data=result)
