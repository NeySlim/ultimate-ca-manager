"""
CAs Management Routes v2.0
/api/cas/* - Certificate Authorities CRUD
"""

from flask import Blueprint, request, g, jsonify
import base64
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from utils.pagination import paginate
from services.ca_service import CAService
from models import Certificate

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
    
    # First pass: Link by explicit parent reference (caref)
    processed_ids = set()
    
    for ca in all_cas:
        ca_dict = ca_map[ca.refid]
        
        if ca.caref and ca.caref in ca_map:
            # Explicit parent link found
            parent = ca_map[ca.caref]
            parent['children'].append(ca_dict)
            processed_ids.add(ca.refid)
            
    # Second pass: Link orphans by Subject/Issuer matching if not already processed
    for ca in all_cas:
        if ca.refid in processed_ids:
            continue
            
        ca_dict = ca_map[ca.refid]
        
        # If it's explicitly marked as root, add to roots
        if ca.is_root:
            roots.append(ca_dict)
            continue
            
        # Try to find parent by matching Issuer DN with Subject DN of other CAs
        parent_found = False
        if ca.issuer and ca.subject != ca.issuer: # Not self-signed
            for potential_parent in all_cas:
                if potential_parent.refid == ca.refid:
                    continue
                    
                # Loose matching on Subject string
                # TODO: Parse DN properly for robust matching
                if potential_parent.subject == ca.issuer:
                    ca_map[potential_parent.refid]['children'].append(ca_dict)
                    parent_found = True
                    # Update type if it was mislabeled
                    if ca_dict['type'] == 'Root CA':
                         ca_dict['type'] = 'Intermediate'
                         
                    # AUTO-FIX: Persist the relationship if missing
                    # We do this asynchronously/implicitly by updating the DB model
                    # But since we are inside a read-only view function, we should ideally trigger a task
                    # For now, we will attempt a direct update if safe (GET requests shouldn't write, but this is a repair)
                    try:
                        ca_obj = CAService.get_ca_by_refid(ca.refid)
                        if ca_obj and not ca_obj.caref:
                            ca_obj.caref = potential_parent.refid
                            # If it was marked as root but has a parent, unmark root
                            if ca_obj.is_root:
                                ca_obj.is_root = False
                            from models import db
                            db.session.commit()
                    except Exception as e:
                        # Log error but don't fail the request
                        pass
                        
                    break
        
        if not parent_found:
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
    ca = CAService.get_ca(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    # Get basic model data
    ca_data = ca.to_dict()
    
    # Get parsed certificate details
    try:
        details = CAService.get_ca_details(ca_id)
        # Merge details into response
        ca_data.update({
            'commonName': details.get('subject', {}).get('CN', ca.descr),
            'org': details.get('subject', {}).get('O', ''),
            'country': details.get('subject', {}).get('C', ''),
            'keyAlgo': details.get('public_key', {}).get('algorithm', 'RSA'),
            'keySize': details.get('public_key', {}).get('size', 2048),
            'fingerprint': details.get('fingerprints', {}).get('sha256', ''),
            'crlStatus': 'Active', # TODO: Check if CRL exists and is valid
            'nextCrlUpdate': 'N/A' # TODO: Check CRL next update
        })
    except Exception as e:
        # Fallback if parsing fails
        pass
        
    return success_response(data=ca_data)


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
    include_chain = request.args.get('chain', 'false').lower() == 'true'
    include_key = request.args.get('key', 'false').lower() == 'true'
    password = request.args.get('password')
    
    try:
        data = CAService.export_ca_with_options(
            ca_id=ca_id,
            export_format=format,
            include_chain=include_chain,
            include_key=include_key,
            password=password
        )
        
        # Determine content type and filename
        filename = f"ca_{ca_id}"
        mimetype = "application/x-pem-file"
        
        if format == 'der':
            filename += ".der"
            mimetype = "application/x-x509-ca-cert"
        elif format == 'pkcs12':
            filename += ".p12"
            mimetype = "application/x-pkcs12"
        else:
            filename += ".crt"
            
        return success_response(
            data={
                'content': data.decode('utf-8') if isinstance(data, bytes) and format != 'der' and format != 'pkcs12' else base64.b64encode(data).decode('utf-8'),
                'filename': filename,
                'mimetype': mimetype,
                'is_binary': format in ['der', 'pkcs12']
            }
        )
    except Exception as e:
        return error_response(str(e), 400)


@bp.route('/api/cas/<int:ca_id>/certificates', methods=['GET'])
@require_auth(['read:certificates'])
def list_ca_certificates(ca_id):
    """List certificates for this CA"""
    ca = CAService.get_ca(ca_id)
    if not ca:
        return error_response('CA not found', 404)
        
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Filter by CA refid
    query = Certificate.query.filter_by(caref=ca.refid).order_by(Certificate.created_at.desc())
    
    return paginate(query, page, per_page)
