"""
CSR Management Routes v2.0
/api/csrs/* - Certificate Signing Request CRUD
"""

from flask import Blueprint, request, jsonify
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from models import db, Certificate
from services.cert_service import CertificateService
import datetime

bp = Blueprint('csrs_v2', __name__)

@bp.route('/api/csrs', methods=['GET'])
@require_auth(['read:csrs'])
def list_csrs():
    """List all pending CSRs (Certificates with no crt)"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Filter for certificates that have a CSR but no signed certificate yet
    query = Certificate.query.filter(
        Certificate.csr.isnot(None),
        Certificate.crt.is_(None)
    ).order_by(Certificate.created_at.desc())
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    data = []
    for cert in pagination.items:
        # Convert DB model to frontend friendly format
        item = cert.to_dict()
        item['status'] = 'Pending'
        item['cn'] = cert.common_name
        item['department'] = cert.organizational_unit
        item['sans'] = cert.san_dns_list
        item['key_type'] = cert.key_type
        item['requester'] = cert.created_by
        data.append(item)
    
    return success_response(
        data=data,
        meta={
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }
    )

@bp.route('/api/csrs/<int:csr_id>', methods=['GET'])
@require_auth(['read:csrs'])
def get_csr(csr_id):
    """Get CSR details"""
    cert = Certificate.query.get(csr_id)
    if not cert or not cert.csr:
        return error_response('CSR not found', 404)
    
    data = cert.to_dict(include_private=False)
    data['csr_pem'] = cert.csr  # Allow downloading the PEM
    
    return success_response(data=data)

@bp.route('/api/csrs', methods=['POST'])
@require_auth(['write:csrs'])
def create_csr():
    """Create a new CSR"""
    data = request.json
    if not data or not data.get('cn'):
        return error_response('Common Name (cn) is required', 400)
    
    try:
        # Map frontend data to service arguments
        dn = {'CN': data['cn']}
        if data.get('department'):
            dn['OU'] = data['department']
        if data.get('organization'):
            dn['O'] = data['organization']
        if data.get('country'):
            dn['C'] = data['country']
            
        # Parse key type (Frontend sends "RSA 2048")
        key_algo_full = data.get('key_type', 'RSA 2048')
        # Simple parser
        if 'RSA' in key_algo_full:
            key_type = key_algo_full.replace('RSA', '').strip()
        elif 'EC' in key_algo_full:
            key_type = key_algo_full.replace('EC', '').strip()
        else:
            key_type = '2048'

        cert = CertificateService.generate_csr(
            descr=f"CSR for {data['cn']}",
            dn=dn,
            key_type=key_type,
            san_dns=data.get('sans', []),
            username='current_user' # TODO: Get real user
        )
        
        return created_response(
            data=cert.to_dict(),
            message='CSR created successfully'
        )
    except Exception as e:
        return error_response(f"Failed to create CSR: {str(e)}", 500)

@bp.route('/api/csrs/<int:csr_id>', methods=['DELETE'])
@require_auth(['delete:csrs'])
def delete_csr(csr_id):
    """Delete a CSR"""
    try:
        if CertificateService.delete_certificate(csr_id):
            return no_content_response()
        else:
            return error_response("CSR not found", 404)
    except Exception as e:
        return error_response(str(e), 500)
