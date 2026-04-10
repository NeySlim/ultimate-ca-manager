"""
CAs Management Routes v2.0
/api/cas/* - Certificate Authorities CRUD
"""

from flask import Blueprint, request, g, jsonify, Response
import base64
import re
import logging
import subprocess
import tempfile
import os
import traceback
import uuid
from datetime import datetime, timezone
from auth.unified import require_auth, has_permission
from utils.response import success_response, error_response, created_response, no_content_response
from utils.pagination import paginate
from utils.dn_validation import validate_dn_field, validate_dn
from utils.protocol_url import get_protocol_base_url
from services.ca_service import CAService
from services.audit_service import AuditService
from services.notification_service import NotificationService
from services.import_service import (
    parse_certificate_file, extract_cert_info, find_existing_ca,
    serialize_cert_to_pem, serialize_key_to_pem
)
from utils.file_validation import validate_upload, CERT_EXTENSIONS
from utils.sanitize import sanitize_filename
from models import Certificate, CA, db
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from websocket.emitters import on_ca_created, on_ca_updated, on_ca_deleted
from security.encryption import decrypt_private_key

logger = logging.getLogger(__name__)


def _needs_protocol_url(current_url):
    """Check if a protocol URL needs (re)generation.
    Returns True if URL is empty or uses https:// (protocol URLs must be http://).
    """
    if not current_url:
        return True
    return current_url.startswith('https://')


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
    
    # Add certificate count for each CA
    result = []
    for ca in paginated_cas:
        ca_dict = ca.to_dict()
        # Count certificates by refid first, then by issuer CN
        cert_count = Certificate.query.filter_by(caref=ca.refid).count()
        if cert_count == 0 and ca_dict.get('common_name'):
            cn = ca_dict.get('common_name')
            cert_count = Certificate.query.filter(
                Certificate.issuer.ilike(f'CN={cn},%') | 
                Certificate.issuer.ilike(f'%,CN={cn},%') |
                Certificate.issuer.ilike(f'%,CN={cn}')
            ).count()
        ca_dict['certs'] = cert_count
        result.append(ca_dict)
    
    return success_response(
        data=result,
        meta={
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        }
    )



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
            'OU': data.get('organizationalUnit') or None,
            'C': (data.get('country') or '').upper() or None,
            'ST': data.get('state') or None,
            'L': data.get('locality') or None
        }
        
        # SECURITY: Validate DN fields
        is_valid, error = validate_dn(dn)
        if not is_valid:
            return error_response(error, 400)
        
        # Determine key type
        key_type = '2048' # Default
        if data.get('keyAlgo') == 'RSA':
            key_size = int(data.get('keySize') or 2048)
            if key_size < 2048:
                return error_response('RSA key size must be at least 2048 bits', 400)
            key_type = str(key_size)
        elif data.get('keyAlgo') == 'ECDSA':
            key_type = data.get('keySize') or 'prime256v1'
        
        # Resolve parent CA for intermediate CAs
        caref = None
        if data.get('type') == 'intermediate' and data.get('parentCAId'):
            parent_ca = CA.query.get(int(data['parentCAId']))
            if not parent_ca:
                return error_response('Parent CA not found', 400)
            if not parent_ca.prv:
                return error_response('Parent CA has no private key', 400)
            # Check parent CA is not expired
            from cryptography import x509 as crypto_x509
            from cryptography.hazmat.backends import default_backend as _default_backend
            parent_cert = crypto_x509.load_pem_x509_certificate(
                base64.b64decode(parent_ca.crt), _default_backend()
            )
            if datetime.now(timezone.utc) > parent_cert.not_valid_after_utc:
                return error_response('Parent CA certificate has expired', 400)
            caref = parent_ca.refid
        
        username = g.user.username if hasattr(g, 'user') else (g.current_user.username if hasattr(g, 'current_user') else 'system')
            
        ca = CAService.create_internal_ca(
            descr=data.get('description') or data.get('commonName'),
            dn=dn,
            key_type=key_type,
            validity_days=int(data.get('validityYears') or 10) * 365,
            caref=caref,
            username=username,
            path_length=data.get('pathLength'),
            name_constraints_permitted=data.get('nameConstraintsPermitted'),
            name_constraints_excluded=data.get('nameConstraintsExcluded'),
            policy_constraints_require=data.get('policyConstraintsRequire'),
            policy_constraints_inhibit=data.get('policyConstraintsInhibit'),
            inhibit_any_policy=data.get('inhibitAnyPolicy'),
            sia_urls=data.get('siaUrls'),
        )
        
        # Send notification for CA creation
        try:
            NotificationService.on_ca_created(ca, username)
        except Exception:
            pass  # Non-blocking
        
        # WebSocket event
        try:
            on_ca_created(
                ca_id=ca.id,
                name=ca.name,
                common_name=ca.dn_commonname,
                created_by=username
            )
        except Exception:
            pass  # Non-blocking
        
        return created_response(
            data=ca.to_dict(),
            message='CA created successfully'
        )
    except Exception as e:
        logger.error(f"Failed to create CA: {e}")
        return error_response("Failed to create CA", 500)


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
    # Get file data from either file upload or pasted PEM content
    file_data = None
    filename = 'pasted.pem'
    
    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        try:
            file_data, filename = validate_upload(file, CERT_EXTENSIONS)
        except ValueError as e:
            logger.warning(f"CA upload validation error: {e}")
            return error_response('Invalid file upload', 400)
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
            AuditService.log_action(
                action='ca_updated',
                resource_type='ca',
                resource_id=existing_ca.id,
                resource_name=existing_ca.descr,
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
            descr=name or cert_info['cn'] or filename,
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=base64.b64encode(key_pem).decode('utf-8') if key_pem else None,
            serial=0,
            subject=cert_info['subject'],
            issuer=cert_info['issuer'],
            ski=cert_info.get('ski'),
            valid_from=cert_info['valid_from'],
            valid_to=cert_info['valid_to'],
            imported_from='manual'
        )
        
        db.session.add(ca)
        db.session.commit()
        AuditService.log_action(
            action='ca_imported',
            resource_type='ca',
            resource_id=ca.id,
            resource_name=ca.descr,
            details=f'Imported CA: {ca.descr}',
            success=True
        )
        
        # Send notification for CA creation
        try:
            username = g.current_user.username if hasattr(g, 'current_user') else 'system'
            NotificationService.on_ca_created(ca, username)
        except Exception:
            pass  # Non-blocking
        
        return created_response(
            data=ca.to_dict(),
            message=f'CA "{ca.descr}" imported successfully'
        )
        
    except ValueError as e:
        db.session.rollback()
        logger.warning(f"CA import validation error: {e}")
        return error_response('Invalid CA data', 400)
    except Exception as e:
        db.session.rollback()
        logger.error(f"CA Import Error: {e}")
        logger.error(traceback.format_exc())
        return error_response('Import failed', 500)


@bp.route('/api/v2/cas/<int:ca_id>', methods=['GET'])
@require_auth(['read:cas'])
def get_ca(ca_id):
    """Get CA details"""
    ca = CAService.get_ca(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    # Get basic model data
    ca_data = ca.to_dict()
    
    # Add certificate count
    cert_count = Certificate.query.filter_by(caref=ca.refid).count()
    if cert_count == 0 and ca_data.get('common_name'):
        cn = ca_data.get('common_name')
        cert_count = Certificate.query.filter(
            Certificate.issuer.ilike(f'CN={cn},%') | 
            Certificate.issuer.ilike(f'%,CN={cn},%') |
            Certificate.issuer.ilike(f'%,CN={cn}')
        ).count()
    ca_data['certs'] = cert_count
    
    # Get CRL status
    crl_status = 'Not Generated'
    next_crl_update = 'N/A'
    try:
        from services.crl_service import CRLService
        crl_info = CRLService.get_crl_info(ca_id)
        if crl_info and crl_info.get('exists'):
            crl_status = 'Active'
            next_crl_update = crl_info.get('next_update', 'N/A')
    except Exception:
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

    # Parse X.509 extensions from CA certificate
    try:
        from utils.cert_extensions import parse_certificate_extensions
        ca_data['extensions'] = parse_certificate_extensions(ca.crt)
    except Exception:
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
    
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    data = request.json or {}
    
    # Update allowed fields
    if 'name' in data:
        ca.descr = data['name']
    if 'ocsp_enabled' in data:
        ca.ocsp_enabled = bool(data['ocsp_enabled'])
        primary_ocsp = ca.get_primary_ocsp_url()
        if ca.ocsp_enabled and _needs_protocol_url(primary_ocsp):
            base_url = get_protocol_base_url()
            if not base_url:
                return error_response('Cannot auto-generate OCSP URL: configure a FQDN or Protocol Base URL in Settings first', 400)
            ca.set_ocsp_urls([f"{base_url}/ocsp"])
    if 'ocsp_url' in data:
        ca.set_ocsp_urls([data['ocsp_url']] if isinstance(data['ocsp_url'], str) else data['ocsp_url'])
    if 'ocsp_urls' in data:
        ca.set_ocsp_urls(data['ocsp_urls'])
    if 'cdp_enabled' in data:
        ca.cdp_enabled = bool(data['cdp_enabled'])
        primary_cdp = ca.get_primary_cdp_url()
        if ca.cdp_enabled and _needs_protocol_url(primary_cdp):
            base_url = get_protocol_base_url()
            if not base_url:
                return error_response('Cannot auto-generate CDP URL: configure a FQDN or Protocol Base URL in Settings first', 400)
            ca.set_cdp_urls([f"{base_url}/cdp/{ca.refid}.crl"])
    if 'cdp_url' in data:
        ca.set_cdp_urls([data['cdp_url']] if isinstance(data['cdp_url'], str) else data['cdp_url'])
    if 'cdp_urls' in data:
        ca.set_cdp_urls(data['cdp_urls'])
    if 'aia_ca_issuers_enabled' in data:
        ca.aia_ca_issuers_enabled = bool(data['aia_ca_issuers_enabled'])
        primary_aia = ca.get_primary_aia_url()
        if ca.aia_ca_issuers_enabled and _needs_protocol_url(primary_aia):
            base_url = get_protocol_base_url()
            if not base_url:
                return error_response('Cannot auto-generate AIA URL: configure a FQDN or Protocol Base URL in Settings first', 400)
            ca.set_aia_urls([f"{base_url}/ca/{ca.refid}.cer"])
    if 'aia_ca_issuers_url' in data:
        ca.set_aia_urls([data['aia_ca_issuers_url']] if isinstance(data['aia_ca_issuers_url'], str) else data['aia_ca_issuers_url'])
    if 'aia_ca_issuers_urls' in data:
        ca.set_aia_urls(data['aia_ca_issuers_urls'])
    # CPS fields
    if 'cps_enabled' in data:
        ca.cps_enabled = bool(data['cps_enabled'])
    if 'cps_uri' in data:
        ca.cps_uri = data['cps_uri']
    if 'cps_oid' in data:
        ca.cps_oid = data['cps_oid'] or '2.5.29.32.0'
    if 'is_active' in data:
        ca.is_active = bool(data['is_active'])
    
    try:
        db.session.commit()
        
        # Audit log
        AuditService.log_action(
            action='ca_updated',
            resource_type='ca',
            resource_id=ca_id,
            resource_name=ca.descr,
            details=f'CA {ca.descr} settings updated',
            success=True
        )
        
        try:
            on_ca_updated(ca_id, ca.descr, {k: v for k, v in data.items()})
        except Exception:
            pass
        
        return success_response(data=ca.to_dict(), message='CA updated successfully')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update CA: {e}")
        return error_response('Failed to update CA', 500)


@bp.route('/api/v2/cas/<int:ca_id>', methods=['DELETE'])
@require_auth(['delete:cas'])
def delete_ca(ca_id):
    """Delete CA and all dependent records (CRLs, OCSP responses, etc.)"""
    
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    ca_name = ca.descr or f'CA #{ca_id}'
    
    # Check for child CAs (intermediates signed by this CA)
    child_cas = CA.query.filter_by(caref=ca.refid).count()
    if child_cas > 0:
        return error_response(
            f'Cannot delete CA: {child_cas} intermediate CA(s) depend on it. Delete them first.',
            409
        )
    
    # Check for issued certificates
    from models import Certificate
    issued_certs = Certificate.query.filter_by(caref=ca.refid).count()
    if issued_certs > 0:
        return error_response(
            f'Cannot delete CA: {issued_certs} certificate(s) were issued by it. Revoke and delete them first.',
            409
        )
    
    try:
        # Delete dependent records before deleting CA
        from models.crl import CRLMetadata
        from models.ocsp import OCSPResponse
        
        crl_count = CRLMetadata.query.filter_by(ca_id=ca_id).delete()
        ocsp_count = OCSPResponse.query.filter_by(ca_id=ca_id).delete()
        
        if crl_count or ocsp_count:
            logger.info(f"Deleted {crl_count} CRL(s) and {ocsp_count} OCSP response(s) for CA {ca_name}")
        
        db.session.delete(ca)
        db.session.commit()
        
        # Audit log
        AuditService.log_action(
            action='ca_deleted',
            resource_type='ca',
            resource_id=ca_id,
            resource_name=ca_name,
            details=f'Deleted CA: {ca_name} (cleaned {crl_count} CRLs, {ocsp_count} OCSP responses)',
            success=True
        )
        
        try:
            username = g.current_user.username if hasattr(g, 'current_user') else 'system'
            on_ca_deleted(ca_id, ca_name, username)
        except Exception:
            pass
        
        return no_content_response()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete CA {ca_name}: {e}")
        return error_response('Failed to delete CA', 500)


@bp.route('/api/v2/cas/export', methods=['GET', 'POST'])
@require_auth(['read:cas'])
def export_all_cas():
    """Export all CA certificates in various formats"""
    
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        export_format = data.get('format', 'pem').lower()
    else:
        export_format = request.args.get('format', 'pem').lower()
    
    cas = CA.query.filter(CA.crt.isnot(None)).all()
    if not cas:
        return error_response('No CAs to export', 404)
    
    try:
        if export_format == 'pem':
            pem_data = b''
            for ca in cas:
                if ca.crt:
                    pem_data += base64.b64decode(ca.crt)
                    if not pem_data.endswith(b'\n'):
                        pem_data += b'\n'
            
            return Response(
                pem_data,
                mimetype='application/x-pem-file',
                headers={'Content-Disposition': 'attachment; filename="ca-certificates.pem"'}
            )
        
        elif export_format == 'pkcs7' or export_format == 'p7b':
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                for ca in cas:
                    if ca.crt:
                        f.write(base64.b64decode(ca.crt))
                        f.write(b'\n')
                pem_file = f.name
            
            try:
                p7b_output = subprocess.check_output([
                    'openssl', 'crl2pkcs7', '-nocrl',
                    '-certfile', pem_file,
                    '-outform', 'DER'
                ], stderr=subprocess.DEVNULL, timeout=30)
                
                return Response(
                    p7b_output,
                    mimetype='application/x-pkcs7-certificates',
                    headers={'Content-Disposition': 'attachment; filename="ca-certificates.p7b"'}
                )
            finally:
                os.unlink(pem_file)
        
        else:
            return error_response(f'Bulk export only supports PEM and P7B formats. Use individual export for DER/PKCS12/PFX', 400)
    
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return error_response('Export failed', 500)


@bp.route('/api/v2/cas/<int:ca_id>/export', methods=['GET', 'POST'])
@require_auth(['read:cas'])
def export_ca(ca_id):
    """
    Export CA certificate in various formats
    
    Params (query or POST body):
        format: pem (default), der, pkcs12
        include_key: bool - Include private key
        include_chain: bool - Include parent CA chain
        password: string - Required for PKCS12
    """
    
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    if not ca.crt:
        return error_response('CA certificate data not available', 400)
    
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        export_format = data.get('format', 'pem').lower()
        include_key = bool(data.get('include_key', False))
        include_chain = bool(data.get('include_chain', False))
        password = data.get('password')
    else:
        export_format = request.args.get('format', 'pem').lower()
        include_key = request.args.get('include_key', 'false').lower() == 'true'
        include_chain = request.args.get('include_chain', 'false').lower() == 'true'
        password = request.args.get('password')
    
    # Private key export requires write permission (operator+)
    if include_key or export_format in ('pkcs12', 'pfx', 'key', 'jks'):
        if not has_permission('write:cas', g.permissions):
            return error_response('Private key export requires write:cas permission', 403)
    
    try:
        cert_pem = base64.b64decode(ca.crt)
        
        # Private key only export
        if export_format == 'key':
            if not ca.prv:
                return error_response('CA has no private key', 400)
            key_pem = base64.b64decode(decrypt_private_key(ca.prv))
            if password:
                private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
                key_pem = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
                )
            return Response(
                key_pem,
                mimetype='application/x-pem-file',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.key"'}
            )
        
        if export_format == 'pem':
            result = cert_pem
            content_type = 'application/x-pem-file'
            filename = f"{sanitize_filename(ca.descr or ca.refid)}.crt"
            
            # Include private key if requested
            if include_key and ca.prv:
                key_pem = base64.b64decode(decrypt_private_key(ca.prv))
                if not result.endswith(b'\n'):
                    result += b'\n'
                result += key_pem
                filename = f"{sanitize_filename(ca.descr or ca.refid)}_with_key.pem"
            
            # Include parent CA chain if requested
            if include_chain and ca.caref:
                parent = CA.query.filter_by(refid=ca.caref).first()
                while parent:
                    if parent.crt:
                        parent_cert = base64.b64decode(parent.crt)
                        if not result.endswith(b'\n'):
                            result += b'\n'
                        result += parent_cert
                    if parent.caref:
                        parent = CA.query.filter_by(refid=parent.caref).first()
                    else:
                        break
                if include_key:
                    filename = f"{sanitize_filename(ca.descr or ca.refid)}_full_chain.pem"
                else:
                    filename = f"{sanitize_filename(ca.descr or ca.refid)}_chain.pem"
            
            return Response(
                result,
                mimetype=content_type,
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )
        
        elif export_format == 'der':
            
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            der_bytes = cert.public_bytes(serialization.Encoding.DER)
            
            return Response(
                der_bytes,
                mimetype='application/x-x509-ca-cert',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.der"'}
            )
        
        elif export_format == 'pkcs12':
            if not password:
                return error_response('Password required for PKCS12 export', 400)
            if not ca.prv:
                return error_response('CA has no private key for PKCS12 export', 400)
            
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem = base64.b64decode(decrypt_private_key(ca.prv))
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
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.p12"'}
            )
        
        elif export_format == 'pkcs7' or export_format == 'p7b':
            
            # Create temporary PEM file with CA chain
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                f.write(cert_pem)
                # Include parent chain
                if include_chain and ca.caref:
                    parent = CA.query.filter_by(refid=ca.caref).first()
                    while parent:
                        if parent.crt:
                            f.write(b'\n')
                            f.write(base64.b64decode(parent.crt))
                        if parent.caref:
                            parent = CA.query.filter_by(refid=parent.caref).first()
                        else:
                            break
                pem_file = f.name
            
            try:
                p7b_output = subprocess.check_output([
                    'openssl', 'crl2pkcs7', '-nocrl',
                    '-certfile', pem_file,
                    '-outform', 'DER'
                ], stderr=subprocess.DEVNULL, timeout=30)
                
                return Response(
                    p7b_output,
                    mimetype='application/x-pkcs7-certificates',
                    headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.p7b"'}
                )
            finally:
                os.unlink(pem_file)
        
        elif export_format == 'pfx':
            # PFX is same as PKCS12
            if not password:
                return error_response('Password required for PFX export', 400)
            if not ca.prv:
                return error_response('CA has no private key for PFX export', 400)
            
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem_data = base64.b64decode(decrypt_private_key(ca.prv))
            private_key = serialization.load_pem_private_key(key_pem_data, password=None, backend=default_backend())
            
            p12_bytes = pkcs12.serialize_key_and_certificates(
                name=(ca.descr or ca.refid).encode(),
                key=private_key,
                cert=cert,
                cas=None,
                encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
            )
            
            return Response(
                p12_bytes,
                mimetype='application/x-pkcs12',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.pfx"'}
            )
        
        elif export_format == 'jks':
            if not password:
                return error_response('Password required for JKS export', 400)
            if not ca.prv:
                return error_response('CA has no private key for JKS export', 400)

            import jks as pyjks
            import time

            cert_obj = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem_data = base64.b64decode(decrypt_private_key(ca.prv))
            private_key = serialization.load_pem_private_key(key_pem_data, password=None, backend=default_backend())

            cert_der = cert_obj.public_bytes(serialization.Encoding.DER)
            key_pkcs8 = private_key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()
            )

            cert_chain = [("X.509", cert_der)]

            if include_chain and ca.caref:
                parent = CA.query.filter_by(refid=ca.caref).first()
                while parent:
                    if parent.crt:
                        parent_cert = x509.load_pem_x509_certificate(
                            base64.b64decode(parent.crt), default_backend()
                        )
                        cert_chain.append(("X.509", parent_cert.public_bytes(serialization.Encoding.DER)))
                    if parent.caref:
                        parent = CA.query.filter_by(refid=parent.caref).first()
                    else:
                        break

            ts = int(time.time() * 1000)
            pke = pyjks.PrivateKeyEntry(
                alias=(ca.descr or ca.refid).lower().replace(' ', '-'),
                cert_chain=cert_chain,
                pkey_pkcs8=key_pkcs8,
                timestamp=ts,
            )

            keystore = pyjks.KeyStore.new("jks", [pke])
            jks_bytes = keystore.saves(password)

            return Response(
                jks_bytes,
                mimetype='application/x-java-keystore',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.jks"'}
            )

        else:
            return error_response(f'Unsupported format: {export_format}', 400)
    
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return error_response('Export failed', 500)


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


# ============================================================
# Bulk Operations
# ============================================================

@bp.route('/api/v2/cas/bulk/delete', methods=['POST'])
@require_auth(['delete:cas'])
def bulk_delete_cas():
    """Bulk delete CAs"""

    data = request.get_json()
    if not data or not data.get('ids'):
        return error_response('ids array required', 400)

    ids = data['ids']
    results = {'success': [], 'failed': []}

    for ca_id in ids:
        try:
            ca = CA.query.get(ca_id)
            if not ca:
                results['failed'].append({'id': ca_id, 'error': 'Not found'})
                continue
            
            ca_name = ca.descr or f'CA #{ca_id}'
            
            # Check for child CAs
            child_cas = CA.query.filter_by(caref=ca.refid).count()
            if child_cas > 0:
                results['failed'].append({'id': ca_id, 'error': f'{child_cas} intermediate CA(s) depend on it'})
                continue
            
            # Check for issued certificates
            issued_certs = Certificate.query.filter_by(caref=ca.refid).count()
            if issued_certs > 0:
                results['failed'].append({'id': ca_id, 'error': f'{issued_certs} certificate(s) issued by it'})
                continue
            
            # Clean up dependent records
            from models.crl import CRLMetadata
            from models.ocsp import OCSPResponse
            CRLMetadata.query.filter_by(ca_id=ca_id).delete()
            OCSPResponse.query.filter_by(ca_id=ca_id).delete()
            
            db.session.delete(ca)
            db.session.commit()
            results['success'].append(ca_id)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete CA {ca_id}: {e}")
            results['failed'].append({'id': ca_id, 'error': 'Deletion failed'})

    AuditService.log_action(
        action='cas_bulk_deleted',
        resource_type='ca',
        resource_id=','.join(str(i) for i in results['success']),
        resource_name=f'{len(results["success"])} CAs',
        details=f'Bulk deleted {len(results["success"])} CAs',
        success=True
    )

    return success_response(data=results, message=f'{len(results["success"])} CAs deleted')


@bp.route('/api/v2/cas/bulk/export', methods=['POST'])
@require_auth(['read:cas'])
def bulk_export_cas():
    """Export selected CAs"""

    data = request.get_json()
    if not data or not data.get('ids'):
        return error_response('ids array required', 400)

    export_format = data.get('format', 'pem').lower()
    cas = CA.query.filter(CA.id.in_(data['ids']), CA.crt.isnot(None)).all()

    if not cas:
        return error_response('No CAs found', 404)

    try:
        if export_format == 'pem':
            pem_data = b''
            for ca in cas:
                pem_data += base64.b64decode(ca.crt)
                if not pem_data.endswith(b'\n'):
                    pem_data += b'\n'
            return Response(pem_data, mimetype='application/x-pem-file',
                headers={'Content-Disposition': 'attachment; filename="ca-certificates.pem"'})
        elif export_format in ('pkcs7', 'p7b'):
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                for ca in cas:
                    f.write(base64.b64decode(ca.crt))
                    f.write(b'\n')
                pem_file = f.name
            try:
                p7b_output = subprocess.check_output(
                    ['openssl', 'crl2pkcs7', '-nocrl', '-certfile', pem_file, '-outform', 'DER'],
                    stderr=subprocess.DEVNULL, timeout=30)
                return Response(p7b_output, mimetype='application/x-pkcs7-certificates',
                    headers={'Content-Disposition': 'attachment; filename="ca-certificates.p7b"'})
            finally:
                os.unlink(pem_file)
        else:
            return error_response('Supported formats: pem, p7b', 400)
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return error_response('Export failed', 500)


# --- OCSP Delegated Responder ---

@bp.route('/api/v2/cas/<int:ca_id>/ocsp-responder', methods=['GET'])
@require_auth(['read:cas'])
def get_ocsp_responder(ca_id):
    """Get the delegated OCSP responder certificate for a CA."""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    from models import SystemConfig
    config = SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca_id}').first()
    if not config or not config.value:
        return success_response(data={'responder': None})

    cert = Certificate.query.get(int(config.value))
    if not cert:
        return success_response(data={'responder': None})

    return success_response(data={'responder': {
        'id': cert.id,
        'common_name': cert.common_name,
        'serial_number': cert.serial_number,
        'valid_to': cert.valid_to.isoformat() if cert.valid_to else None,
        'issuer_name': cert.issuer_name,
        'revoked': cert.revoked
    }})


@bp.route('/api/v2/cas/<int:ca_id>/ocsp-responder', methods=['POST'])
@require_auth(['write:cas'])
def set_ocsp_responder(ca_id):
    """Set the delegated OCSP responder certificate for a CA."""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    data = request.get_json()
    cert_id = data.get('certificate_id')
    if not cert_id:
        return error_response('certificate_id is required', 400)

    cert = Certificate.query.get(int(cert_id))
    if not cert:
        return error_response('Certificate not found', 404)

    if cert.caref != ca.refid:
        return error_response('Certificate must be issued by this CA', 400)

    if not cert.prv:
        return error_response('Certificate must have a private key', 400)

    if cert.crt:
        try:
            crt_pem = base64.b64decode(cert.crt).decode('utf-8')
            x509_cert = x509.load_pem_x509_certificate(crt_pem.encode(), default_backend())
            try:
                eku = x509_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
                if x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING not in eku.value:
                    return error_response('Certificate must have OCSPSigning EKU', 400)
            except x509.ExtensionNotFound:
                return error_response('Certificate must have OCSPSigning EKU', 400)
        except Exception as e:
            logger.error(f"Failed to validate OCSP responder cert: {e}")
            return error_response('Failed to validate certificate', 500)

    from models import SystemConfig
    try:
        config = SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca_id}').first()
        if config:
            config.value = str(cert_id)
        else:
            config = SystemConfig(key=f'ocsp_responder_cert_{ca_id}', value=str(cert_id))
            db.session.add(config)
        db.session.commit()

        AuditService.log_action(
            'ocsp_responder_assigned',
            resource_type='ca',
            resource_id=ca_id,
            details=f'Delegated OCSP responder set to cert #{cert_id} for CA {ca.descr}'
        )

        return success_response(data={'certificate_id': cert_id}, message='OCSP responder configured')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to set OCSP responder: {e}")
        return error_response('Failed to configure OCSP responder', 500)


@bp.route('/api/v2/cas/<int:ca_id>/ocsp-responder', methods=['DELETE'])
@require_auth(['delete:cas'])
def delete_ocsp_responder(ca_id):
    """Remove the delegated OCSP responder for a CA."""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    from models import SystemConfig
    try:
        config = SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca_id}').first()
        if config:
            db.session.delete(config)
            db.session.commit()

            AuditService.log_action(
                'ocsp_responder_removed',
                resource_type='ca',
                resource_id=ca_id,
                details=f'Delegated OCSP responder removed for CA {ca.descr}'
            )

        return no_content_response()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to remove OCSP responder: {e}")
        return error_response('Failed to remove OCSP responder', 500)


@bp.route('/api/v2/cas/<int:ca_id>/eligible-ocsp-responders', methods=['GET'])
@require_auth(['read:cas'])
def list_eligible_ocsp_responders(ca_id):
    """List certificates eligible as OCSP delegated responder for a CA.
    Eligible = issued by this CA, has OCSPSigning EKU, has private key, not revoked/expired.
    """
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    now = datetime.utcnow()
    certs = Certificate.query.filter(
        Certificate.caref == ca.refid,
        Certificate.crt.isnot(None),
        Certificate.prv.isnot(None),
        Certificate.revoked == False
    ).all()

    eligible = []
    for cert in certs:
        if cert.valid_to and cert.valid_to < now:
            continue
        try:
            crt_pem = base64.b64decode(cert.crt).decode('utf-8')
            x509_cert = x509.load_pem_x509_certificate(crt_pem.encode(), default_backend())
            eku = x509_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
            if x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING in eku.value:
                eligible.append({
                    'id': cert.id,
                    'common_name': cert.common_name,
                    'serial_number': cert.serial_number,
                    'valid_to': cert.valid_to.isoformat() if cert.valid_to else None
                })
        except (x509.ExtensionNotFound, Exception):
            continue

    return success_response(data=eligible)
