"""
SCEP Management Routes v2.0
/api/scep/* - SCEP configuration and requests
"""

from flask import Blueprint, request, g
from backend.auth.unified import require_auth
from backend.utils.response import success_response, error_response

bp = Blueprint('scep_v2', __name__)


@bp.route('/api/scep/config', methods=['GET'])
@require_auth(['read:scep'])
def get_scep_config():
    """Get SCEP configuration"""
    return success_response(data={
        'enabled': False,
        'challenge_password': None
    })


@bp.route('/api/scep/config', methods=['PATCH'])
@require_auth(['write:scep'])
def update_scep_config():
    """Update SCEP configuration"""
    data = request.json
    return success_response(
        data=data,
        message='SCEP config updated'
    )


@bp.route('/api/scep/requests', methods=['GET'])
@require_auth(['read:scep'])
def list_scep_requests():
    """List SCEP certificate requests"""
    status = request.args.get('status')  # pending, approved, rejected
    return success_response(data=[])


@bp.route('/api/scep/<int:request_id>/approve', methods=['POST'])
@require_auth(['write:scep'])
def approve_scep_request(request_id):
    """Approve SCEP request"""
    return success_response(
        data={'id': request_id, 'status': 'approved'},
        message='SCEP request approved'
    )


@bp.route('/api/scep/<int:request_id>/reject', methods=['POST'])
@require_auth(['write:scep'])
def reject_scep_request(request_id):
    """Reject SCEP request"""
    data = request.json
    reason = data.get('reason') if data else None
    
    return success_response(
        data={'id': request_id, 'status': 'rejected', 'reason': reason},
        message='SCEP request rejected'
    )
