"""
Settings - Public endpoints (admin URL, protocol URL, ACME vhost effective view)
"""

from flask import request

from auth.unified import require_auth
from utils.response import success_response

from . import bp
from .general import update_general_settings
from utils.public_endpoints import build_effective_endpoints, run_preflight_checks


@bp.route('/api/v2/settings/public-endpoints', methods=['GET'])
@require_auth(['read:settings'])
def get_public_endpoints():
    """Effective public URLs, CORS origins, and host-role status."""
    return success_response(data=build_effective_endpoints(request))


@bp.route('/api/v2/settings/public-endpoints/preflight', methods=['POST'])
@require_auth(['write:settings'])
def preflight_public_endpoints():
    """DNS/TLS diagnostics for configured admin and ACME hosts."""
    return success_response(data=run_preflight_checks())


@bp.route('/api/v2/settings/public-endpoints', methods=['PATCH'])
@require_auth(['write:settings'])
def patch_public_endpoints():
    """Update admin/protocol/ACME public endpoint settings (delegates to general PATCH)."""
    return update_general_settings()
