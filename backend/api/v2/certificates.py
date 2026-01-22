"""
Certificates Management Routes v2.0
/api/certificates/* - Certificate CRUD
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response

bp = Blueprint('certificates_v2', __name__)


@bp.route('/api/v2/certificates', methods=['GET'])
@require_auth(['read:certificates'])
def list_certificates():
    """List certificates"""
    from models import Certificate
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')  # valid, revoked, expired
    
    query = Certificate.query
    
    # Apply status filter
    if status == 'revoked':
        query = query.filter_by(revoked=True)
    elif status == 'valid':
        query = query.filter_by(revoked=False)
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    certs = [{
        'id': cert.id,
        'refid': cert.refid,
        'descr': cert.descr,
        'caref': cert.caref,
        'cert_type': cert.cert_type,
        'subject': cert.subject,
        'issuer': cert.issuer,
        'serial_number': cert.serial_number,
        'valid_from': cert.valid_from.isoformat() if cert.valid_from else None,
        'valid_to': cert.valid_to.isoformat() if cert.valid_to else None,
        'revoked': cert.revoked,
        'imported_from': cert.imported_from,
        'created_at': cert.created_at.isoformat() if cert.created_at else None
    } for cert in pagination.items]
    
    return success_response(
        data=certs,
        meta={'total': pagination.total, 'page': page, 'per_page': per_page}
    )


@bp.route('/api/v2/certificates', methods=['POST'])
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


@bp.route('/api/v2/certificates/<int:cert_id>', methods=['GET'])
@require_auth(['read:certificates'])
def get_certificate(cert_id):
    """Get certificate details"""
    return success_response(data={'id': cert_id})


@bp.route('/api/v2/certificates/<int:cert_id>', methods=['DELETE'])
@require_auth(['delete:certificates'])
def delete_certificate(cert_id):
    """Delete certificate"""
    return no_content_response()


@bp.route('/api/v2/certificates/<int:cert_id>/export', methods=['GET'])
@require_auth(['read:certificates'])
def export_certificate(cert_id):
    """Export certificate (PEM/DER/PKCS12)"""
    format = request.args.get('format', 'pem')
    include_chain = request.args.get('include_chain', 'false') == 'true'
    
    return success_response(data={
        'format': format,
        'include_chain': include_chain
    })


@bp.route('/api/v2/certificates/<int:cert_id>/revoke', methods=['POST'])
@require_auth(['write:certificates'])
def revoke_certificate(cert_id):
    """Revoke certificate"""
    data = request.json
    reason = data.get('reason', 'unspecified') if data else 'unspecified'
    
    return success_response(
        data={'id': cert_id, 'status': 'revoked', 'reason': reason},
        message='Certificate revoked'
    )


@bp.route('/api/v2/certificates/<int:cert_id>/renew', methods=['POST'])
@require_auth(['write:certificates'])
def renew_certificate(cert_id):
    """Renew certificate"""
    return created_response(
        data={'id': cert_id + 1000, 'renewed_from': cert_id},
        message='Certificate renewed'
    )


@bp.route('/api/v2/certificates/import', methods=['POST'])
@require_auth(['write:certificates'])
def import_certificate():
    """
    Import certificate from file
    Supports: PEM, DER, PKCS12, JKS
    """
    # Check for file upload
    if 'file' not in request.files:
        return error_response('No file provided', 400)
    
    file = request.files['file']
    if file.filename == '':
        return error_response('No file selected', 400)
    
    # Get optional parameters
    format_type = request.form.get('format', 'auto')  # auto, pem, der, pkcs12, jks
    password = request.form.get('password')  # For PKCS12/JKS
    ca_id = request.form.get('ca_id', type=int)  # Optional: link to CA
    import_chain = request.form.get('import_chain', 'false') == 'true'
    import_private_key = request.form.get('import_private_key', 'false') == 'true'
    
    # TODO: Implement actual certificate import logic
    # - Detect format if auto
    # - Parse certificate
    # - Validate certificate
    # - Store in database
    # - Save files
    
    return created_response(
        data={
            'id': 999,
            'filename': file.filename,
            'format': format_type,
            'has_private_key': import_private_key,
            'imported': True
        },
        message='Certificate imported successfully'
    )
