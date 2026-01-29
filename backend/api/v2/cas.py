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


@bp.route('/api/v2/cas', methods=['GET'])
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


@bp.route('/api/v2/cas/tree', methods=['GET'])
@require_auth(['read:cas'])
def list_cas_tree():
    """
    Get CA hierarchy with orphans separated
    Returns: {
        "roots": [...],
        "orphans": [...]
    }
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
        # Check expiry status
        if ca['valid_to']:
            from datetime import datetime
            try:
                valid_to = datetime.fromisoformat(ca['valid_to'].replace('Z', '+00:00'))
                if valid_to < datetime.now(valid_to.tzinfo):
                    ca['status'] = 'Expired'
                else:
                    ca['status'] = 'Active'
            except:
                ca['status'] = 'Active'
        else:
            ca['status'] = 'Active'
        # Get certificate count
        ca['certs'] = Certificate.query.filter_by(caref=ca['refid']).count()
        ca['expiry'] = ca['valid_to'].split('T')[0] if ca['valid_to'] else 'N/A'

    roots = []
    orphans = []
    
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
            processed_ids.add(ca.refid)
            continue
            
        # Try to find parent by matching Issuer DN with Subject DN of other CAs
        parent_found = False
        if ca.issuer and ca.subject != ca.issuer: # Not self-signed
            for potential_parent in all_cas:
                if potential_parent.refid == ca.refid:
                    continue
                    
                # Loose matching on Subject string
                if potential_parent.subject == ca.issuer:
                    ca_map[potential_parent.refid]['children'].append(ca_dict)
                    parent_found = True
                    processed_ids.add(ca.refid)
                    # Update type if it was mislabeled
                    if ca_dict['type'] == 'Root CA':
                         ca_dict['type'] = 'Intermediate'
                         
                    # AUTO-FIX: Persist the relationship if missing
                    try:
                        ca_obj = CAService.get_ca_by_refid(ca.refid)
                        if ca_obj and not ca_obj.caref:
                            ca_obj.caref = potential_parent.refid
                            if ca_obj.is_root:
                                ca_obj.is_root = False
                            from models import db
                            db.session.commit()
                    except Exception:
                        pass
                        
                    break
        
        if not parent_found:
            # This is an orphan: intermediate CA without parent in database
            if ca.subject == ca.issuer:
                # Self-signed but not marked as root
                roots.append(ca_dict)
                ca_dict['type'] = 'Root CA'
            else:
                # Intermediate without parent = orphan
                orphans.append(ca_dict)
                ca_dict['type'] = 'Intermediate (Orphaned)'
            
    return success_response(data={
        'roots': roots,
        'orphans': orphans
    })


@bp.route('/api/v2/cas', methods=['POST'])
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


@bp.route('/api/v2/cas/import', methods=['POST'])
@require_auth(['write:cas'])
def import_ca():
    """
    Import CA certificate from file OR pasted PEM content
    Supports: PEM, DER, PKCS12, PKCS7
    Auto-updates existing CA if duplicate found (same subject)
    
    Form data:
        file: Certificate file (optional if pem_content provided)
        pem_content: Pasted PEM content (optional if file provided)
        password: Password for PKCS12
        name: Optional display name
        import_key: Whether to import private key (default: true)
        update_existing: Whether to update if duplicate found (default: true)
    """
    from models import CA, db
    from services.import_service import (
        parse_certificate_file, extract_cert_info, find_existing_ca,
        serialize_cert_to_pem, serialize_key_to_pem
    )
    import base64
    import uuid
    
    # Get file data from either file upload or pasted PEM content
    file_data = None
    filename = 'pasted.pem'
    
    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        file_data = file.read()
        filename = file.filename
    elif request.form.get('pem_content'):
        pem_content = request.form.get('pem_content')
        file_data = pem_content.encode('utf-8')
        filename = 'pasted.pem'
    else:
        return error_response('No file or PEM content provided', 400)
    
    password = request.form.get('password')
    name = request.form.get('name', '')
    import_key = request.form.get('import_key', 'true').lower() == 'true'
    update_existing = request.form.get('update_existing', 'true').lower() == 'true'
    
    try:
        # Parse certificate using shared service
        cert, private_key, format_detected = parse_certificate_file(
            file_data, filename, password, import_key
        )
        
        # Extract certificate info
        cert_info = extract_cert_info(cert)
        
        # Serialize to PEM
        cert_pem = serialize_cert_to_pem(cert)
        key_pem = serialize_key_to_pem(private_key) if import_key else None
        
        # Check for existing CA with same subject
        existing_ca = find_existing_ca(cert_info)
        
        if existing_ca:
            if not update_existing:
                return error_response(
                    f'CA with subject "{cert_info["cn"]}" already exists (ID: {existing_ca.id})',
                    409
                )
            
            # Update existing CA
            existing_ca.descr = name or cert_info['cn'] or existing_ca.descr
            existing_ca.crt = base64.b64encode(cert_pem).decode('utf-8')
            if key_pem:
                existing_ca.prv = base64.b64encode(key_pem).decode('utf-8')
            existing_ca.issuer = cert_info['issuer']
            existing_ca.valid_from = cert_info['valid_from']
            existing_ca.valid_to = cert_info['valid_to']
            
            db.session.commit()
            
            from services.audit_service import AuditService
            AuditService.log_action(
                action='ca_updated',
                resource_type='ca',
                resource_id=existing_ca.id,
                details=f'Updated CA via import: {existing_ca.descr}',
                success=True
            )
            
            return success_response(
                data=existing_ca.to_dict(),
                message=f'CA "{existing_ca.descr}" updated (already existed)'
            )
        
        # Create new CA record
        refid = str(uuid.uuid4())
        ca = CA(
            refid=refid,
            descr=name or cert_info['cn'] or file.filename,
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=base64.b64encode(key_pem).decode('utf-8') if key_pem else None,
            serial=0,
            subject=cert_info['subject'],
            issuer=cert_info['issuer'],
            valid_from=cert_info['valid_from'],
            valid_to=cert_info['valid_to'],
            imported_from='manual'
        )
        
        db.session.add(ca)
        db.session.commit()
        
        from services.audit_service import AuditService
        AuditService.log_action(
            action='ca_imported',
            resource_type='ca',
            resource_id=ca.id,
            details=f'Imported CA: {ca.descr}',
            success=True
        )
        
        return created_response(
            data=ca.to_dict(),
            message=f'CA "{ca.descr}" imported successfully'
        )
        
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        import traceback
        print(f"CA Import Error: {str(e)}")
        print(traceback.format_exc())
        return error_response(f'Import failed: {str(e)}', 500)


@bp.route('/api/v2/cas/<int:ca_id>', methods=['GET'])
@require_auth(['read:cas'])
def get_ca(ca_id):
    """Get CA details"""
    ca = CAService.get_ca(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    # Get basic model data
    ca_data = ca.to_dict()
    
    # Get CRL status
    crl_status = 'Not Generated'
    next_crl_update = 'N/A'
    try:
        from services.crl_service import CRLService
        crl_info = CRLService.get_crl_info(ca_id)
        if crl_info and crl_info.get('exists'):
            crl_status = 'Active'
            next_crl_update = crl_info.get('next_update', 'N/A')
    except:
        pass
    
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
            'crlStatus': crl_status,
            'nextCrlUpdate': next_crl_update
        })
    except Exception as e:
        # Fallback if parsing fails
        pass
        
    return success_response(data=ca_data)


@bp.route('/api/v2/cas/<int:ca_id>', methods=['PATCH'])
@require_auth(['write:cas'])
def update_ca(ca_id):
    """
    Update CA settings (OCSP, CDP, etc.)
    
    Body (all optional):
        name: Display name
        ocsp_enabled: bool - Enable OCSP responder
        ocsp_url: string - OCSP responder URL
        cdp_enabled: bool - Enable CRL Distribution Point
        cdp_url: string - CRL Distribution Point URL
        is_active: bool - Active status
    """
    from models import CA, db
    
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    data = request.json or {}
    
    # Update allowed fields
    if 'name' in data:
        ca.descr = data['name']
    if 'ocsp_enabled' in data:
        ca.ocsp_enabled = bool(data['ocsp_enabled'])
    if 'ocsp_url' in data:
        ca.ocsp_url = data['ocsp_url']
    if 'cdp_enabled' in data:
        ca.cdp_enabled = bool(data['cdp_enabled'])
    if 'cdp_url' in data:
        ca.cdp_url = data['cdp_url']
    if 'is_active' in data:
        ca.is_active = bool(data['is_active'])
    
    try:
        db.session.commit()
        
        # Audit log
        from services.audit_service import AuditService
        AuditService.log_action(
            action='ca_updated',
            resource_type='ca',
            resource_id=ca_id,
            details=f'CA {ca.descr} settings updated',
            success=True
        )
        
        return success_response(data=ca.to_dict(), message='CA updated successfully')
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to update CA: {str(e)}', 500)


@bp.route('/api/v2/cas/<int:ca_id>', methods=['DELETE'])
@require_auth(['delete:cas'])
def delete_ca(ca_id):
    """Delete CA"""
    from models import CA, db
    
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    ca_name = ca.descr or ca.descr or f'CA #{ca_id}'
    
    # Delete the CA
    db.session.delete(ca)
    db.session.commit()
    
    # Audit log
    from services.audit_service import AuditService
    AuditService.log_action(
        action='ca_deleted',
        resource_type='ca',
        resource_id=ca_id,
        details=f'Deleted CA: {ca_name}',
        success=True
    )
    
    return no_content_response()


@bp.route('/api/v2/cas/<int:ca_id>/export', methods=['GET'])
@require_auth(['read:cas'])
def export_ca(ca_id):
    """
    Export CA certificate in various formats
    
    Query params:
        format: pem (default), der, pkcs12
        include_key: bool - Include private key
        include_chain: bool - Include parent CA chain
        password: string - Required for PKCS12
    """
    from flask import Response
    from models import CA
    import base64
    
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    if not ca.crt:
        return error_response('CA certificate data not available', 400)
    
    export_format = request.args.get('format', 'pem').lower()
    include_key = request.args.get('include_key', 'false').lower() == 'true'
    include_chain = request.args.get('include_chain', 'false').lower() == 'true'
    password = request.args.get('password')
    
    try:
        cert_pem = base64.b64decode(ca.crt)
        
        if export_format == 'pem':
            result = cert_pem
            content_type = 'application/x-pem-file'
            filename = f"{ca.descr or ca.refid}.crt"
            
            # Include private key if requested
            if include_key and ca.prv:
                key_pem = base64.b64decode(ca.prv)
                if not result.endswith(b'\\n'):
                    result += b'\\n'
                result += key_pem
                filename = f"{ca.descr or ca.refid}_with_key.pem"
            
            # Include parent CA chain if requested
            if include_chain and ca.caref:
                parent = CA.query.filter_by(refid=ca.caref).first()
                while parent:
                    if parent.crt:
                        parent_cert = base64.b64decode(parent.crt)
                        if not result.endswith(b'\\n'):
                            result += b'\\n'
                        result += parent_cert
                    if parent.caref:
                        parent = CA.query.filter_by(refid=parent.caref).first()
                    else:
                        break
                if include_key:
                    filename = f"{ca.descr or ca.refid}_full_chain.pem"
                else:
                    filename = f"{ca.descr or ca.refid}_chain.pem"
            
            return Response(
                result,
                mimetype=content_type,
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )
        
        elif export_format == 'der':
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import serialization
            
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            der_bytes = cert.public_bytes(serialization.Encoding.DER)
            
            return Response(
                der_bytes,
                mimetype='application/x-x509-ca-cert',
                headers={'Content-Disposition': f'attachment; filename="{ca.descr or ca.refid}.der"'}
            )
        
        elif export_format == 'pkcs12':
            if not password:
                return error_response('Password required for PKCS12 export', 400)
            if not ca.prv:
                return error_response('CA has no private key for PKCS12 export', 400)
            
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.serialization import pkcs12
            
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem = base64.b64decode(ca.prv)
            private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
            
            # Build parent CA chain if available
            ca_certs = []
            if ca.caref:
                parent = CA.query.filter_by(refid=ca.caref).first()
                while parent:
                    if parent.crt:
                        parent_cert = x509.load_pem_x509_certificate(
                            base64.b64decode(parent.crt), default_backend()
                        )
                        ca_certs.append(parent_cert)
                    if parent.caref:
                        parent = CA.query.filter_by(refid=parent.caref).first()
                    else:
                        break
            
            p12_bytes = pkcs12.serialize_key_and_certificates(
                name=(ca.descr or ca.refid).encode(),
                key=private_key,
                cert=cert,
                cas=ca_certs if ca_certs else None,
                encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
            )
            
            return Response(
                p12_bytes,
                mimetype='application/x-pkcs12',
                headers={'Content-Disposition': f'attachment; filename="{ca.descr or ca.refid}.p12"'}
            )
        
        else:
            return error_response(f'Unsupported format: {export_format}', 400)
    
    except Exception as e:
        return error_response(f'Export failed: {str(e)}', 500)


@bp.route('/api/v2/cas/<int:ca_id>/certificates', methods=['GET'])
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
    
    result = paginate(query, page, per_page)
    
    # Convert items to dict
    return success_response(
        data=[cert.to_dict() for cert in result['items']],
        meta=result['meta']
    )
