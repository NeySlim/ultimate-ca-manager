"""
Certificates Management Routes v2.0
/api/certificates/* - Certificate CRUD
"""

from flask import Blueprint, request, g
from backend.auth.unified import require_auth
from backend.utils.response import success_response, error_response, created_response, no_content_response

bp = Blueprint('certificates_v2', __name__)


@bp.route('/api/certificates', methods=['GET'])
@require_auth(['read:certificates'])
def list_certificates():
    """List certificates"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')  # valid, revoked, expired
    
    return success_response(
        data=[],
        meta={'total': 0, 'page': page, 'per_page': per_page}
    )


@bp.route('/api/certificates', methods=['POST'])
@require_auth(['write:certificates'])
def create_certificate():
    """Create certificate"""
    data = request.json
    
    if not data or not data.get('cn'):
        return error_response('Common Name (cn) is required', 400)
    
    if not data.get('ca_id'):
        return error_response('CA ID is required', 400)
    
    return created_response(
        data={'id': 1, 'cn': data['cn']},
        message='Certificate created successfully'
    )


@bp.route('/api/certificates/<int:cert_id>', methods=['GET'])
@require_auth(['read:certificates'])
def get_certificate(cert_id):
    """Get certificate details"""
    return success_response(data={'id': cert_id})


@bp.route('/api/certificates/<int:cert_id>', methods=['DELETE'])
@require_auth(['delete:certificates'])
def delete_certificate(cert_id):
    """Delete certificate"""
    return no_content_response()


@bp.route('/api/certificates/<int:cert_id>/export', methods=['GET'])
@require_auth(['read:certificates'])
def export_certificate(cert_id):
    """Export certificate (PEM/DER/PKCS12)"""
    format = request.args.get('format', 'pem')
    include_chain = request.args.get('include_chain', 'false') == 'true'
    
    return success_response(data={
        'format': format,
        'include_chain': include_chain
    })


@bp.route('/api/certificates/<int:cert_id>/revoke', methods=['POST'])
@require_auth(['write:certificates'])
def revoke_certificate(cert_id):
    """Revoke certificate"""
    data = request.json
    reason = data.get('reason', 'unspecified') if data else 'unspecified'
    
    return success_response(
        data={'id': cert_id, 'status': 'revoked', 'reason': reason},
        message='Certificate revoked'
    )


@bp.route('/api/certificates/<int:cert_id>/renew', methods=['POST'])
@require_auth(['write:certificates'])
def renew_certificate(cert_id):
    """Renew certificate"""
    return created_response(
        data={'id': cert_id + 1000, 'renewed_from': cert_id},
        message='Certificate renewed'
    )
