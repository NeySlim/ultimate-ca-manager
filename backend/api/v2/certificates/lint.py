"""Certificate linting route (RFC 5280 / CA-Browser Forum conformance).

Informative only — never blocks issuance. Returns structured findings from
the available linters (pkilint, and zlint when its binary is present).
"""
import logging

from flask import request

from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, Certificate
from services import cert_linting_service
from . import bp

logger = logging.getLogger(__name__)


@bp.route('/api/v2/certificates/lint/status', methods=['GET'])
@require_auth(['read:certificates'])
def lint_status():
    """Report which linters are available in this deployment."""
    status = cert_linting_service.linters_status()
    return success_response(data={
        'available': any(status.values()),
        'linters': status,
        'profiles': list(cert_linting_service.VALID_PROFILES),
    })


@bp.route('/api/v2/certificates/<int:cert_id>/lint', methods=['GET'])
@require_auth(['read:certificates'])
def lint_certificate(cert_id):
    """Lint a stored certificate against the requested profile.

    Query param ``profile``: ``rfc5280`` (default), ``cabf`` or ``etsi``.
    """
    cert = db.session.get(Certificate, cert_id)
    if not cert or not cert.crt:
        return error_response('Certificate not found', 404)

    profile = (request.args.get('profile') or cert_linting_service.PROFILE_RFC5280).lower()
    if profile not in cert_linting_service.VALID_PROFILES:
        return error_response('Invalid lint profile', 400)

    try:
        result = cert_linting_service.lint_certificate_pem(cert.crt, profile)
    except ValueError as exc:
        logger.warning('Linting cert %s failed: %s', cert_id, exc)
        return error_response('Could not lint certificate', 422)

    return success_response(data=result)
