"""
CAs Management Routes v2.0
/api/cas/* - Certificate Authorities CRUD
"""

from flask import Blueprint, request, g, jsonify
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from utils.pagination import paginate
from services.ca_service import CAService

bp = Blueprint('cas_v2', __name__)


@bp.route('/api/cas', methods=['GET'])
@require_auth(['read:cas'])
def list_cas():
    """
    List CAs for current user
    Query: ?page=1&per_page=20&search=xxx&type=xxx
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    ca_type = request.args.get('type', '')
    
    # Get all CAs
    all_cas = CAService.list_cas()
    
    # Filter
    filtered_cas = []
    for ca in all_cas:
        if search and search.lower() not in ca.descr.lower():
            continue
            
        # Optional: Filter by 'orphan' logic if requested
        if ca_type == 'orphan':
             # Orphan = Intermediate (caref set) but parent not found in list?
             # Or imported manually without parent link?
             # For now, we'll return manual imports that have no caref but are not self-signed?
             if ca.imported_from == 'manual' and not ca.is_root and not ca.caref:
                 filtered_cas.append(ca)
             continue
             
        filtered_cas.append(ca)
    
    # Paginate manually since list_cas returns list
    total = len(filtered_cas)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_cas = filtered_cas[start:end]
    
    return success_response(
        data=[ca.to_dict() for ca in paginated_cas],
        meta={
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        }
    )


@bp.route('/api/cas/tree', methods=['GET'])
@require_auth(['read:cas'])
def list_cas_tree():
    """
    Get CA hierarchy
    """
    all_cas = CAService.list_cas()
    
    # Build map
    ca_map = {ca.refid: ca.to_dict() for ca in all_cas}
    
    # Initialize children array for each CA
    for ca in ca_map.values():
        ca['children'] = []
        # Add extra fields expected by UI
        ca['name'] = ca['descr']
        ca['type'] = 'Root CA' if ca['is_root'] else 'Intermediate'
        ca['status'] = 'Active' # TODO: Check expiry
        ca['certs'] = 0 # TODO: Get count
        ca['expiry'] = ca['valid_to'].split('T')[0] if ca['valid_to'] else 'N/A'

    roots = []
    
    for ca in all_cas:
        ca_dict = ca_map[ca.refid]
        if ca.caref and ca.caref in ca_map:
            parent = ca_map[ca.caref]
            parent['children'].append(ca_dict)
        else:
            roots.append(ca_dict)
            
    return success_response(data=roots)


@bp.route('/api/cas', methods=['POST'])
@require_auth(['write:cas'])
def create_ca():
    """
    Create new CA
    Body: {commonName, organization, country, keyAlgo, keySize, validityYears, type...}
    """
    data = request.json
    
    if not data or not data.get('commonName'):
        return error_response('Common Name is required', 400)
    
    try:
        # Map frontend fields to backend expected fields
        dn = {
            'CN': data.get('commonName'),
            'O': data.get('organization'),
            'C': data.get('country')
        }
        
        # Determine key type
        key_type = '2048' # Default
        if data.get('keyAlgo') == 'RSA':
            key_type = str(data.get('keySize', 2048))
        elif data.get('keyAlgo') == 'ECDSA':
            key_type = data.get('keySize', 'P-256') # Using keySize field for curve in frontend
            
        ca = CAService.create_internal_ca(
            descr=data.get('commonName'), # Use CN as description
            dn=dn,
            key_type=key_type,
            validity_days=int(data.get('validityYears', 10)) * 365,
            username=g.user.username if hasattr(g, 'user') else 'system'
        )
        
        return created_response(
            data=ca.to_dict(),
            message='CA created successfully'
        )
    except Exception as e:
        return error_response(str(e), 500)


@bp.route('/api/cas/<int:ca_id>', methods=['GET'])
@require_auth(['read:cas'])
def get_ca(ca_id):
    """Get CA details"""
    return success_response(data={'id': ca_id})


@bp.route('/api/cas/<int:ca_id>', methods=['PATCH'])
@require_auth(['write:cas'])
def update_ca(ca_id):
    """Update CA"""
    data = request.json
    return success_response(data={'id': ca_id}, message='CA updated')


@bp.route('/api/cas/<int:ca_id>', methods=['DELETE'])
@require_auth(['delete:cas'])
def delete_ca(ca_id):
    """Delete CA"""
    return no_content_response()


@bp.route('/api/cas/<int:ca_id>/export', methods=['GET'])
@require_auth(['read:cas'])
def export_ca(ca_id):
    """Export CA certificate"""
    format = request.args.get('format', 'pem')
    return success_response(data={'format': format})


@bp.route('/api/cas/<int:ca_id>/certificates', methods=['GET'])
@require_auth(['read:certificates'])
def list_ca_certificates(ca_id):
    """List certificates for this CA"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    return success_response(
        data=[],
        meta={'total': 0, 'page': page, 'per_page': per_page}
    )
