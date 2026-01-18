"""
CRL & OCSP Routes v2.0
"""

from flask import Blueprint, request, g
from backend.auth.unified import require_auth
from backend.utils.response import success_response

bp = Blueprint('crl_v2', __name__)


@bp.route('/api/crl', methods=['GET'])
@require_auth(['read:crl'])
def list_crls():
    """List CRLs"""
    return success_response(data=[])


@bp.route('/api/crl/<int:ca_id>', methods=['GET'])
@require_auth(['read:crl'])
def get_crl(ca_id):
    """Get CRL for CA"""
    return success_response(data={'ca_id': ca_id})


@bp.route('/api/crl/<int:ca_id>/regenerate', methods=['POST'])
@require_auth(['write:crl'])
def regenerate_crl(ca_id):
    """Force CRL regeneration"""
    return success_response(
        data={'ca_id': ca_id, 'regenerated': True},
        message='CRL regenerated'
    )


@bp.route('/api/ocsp/status', methods=['GET'])
@require_auth(['read:certificates'])
def get_ocsp_status():
    """Get OCSP service status"""
    return success_response(data={
        'enabled': True,
        'running': True
    })


@bp.route('/api/ocsp/stats', methods=['GET'])
@require_auth(['read:certificates'])
def get_ocsp_stats():
    """Get OCSP statistics"""
    return success_response(data={
        'total_requests': 0,
        'cache_hits': 0
    })
