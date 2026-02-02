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
import base64
import uuid

bp = Blueprint('csrs_v2', __name__)

@bp.route('/api/v2/csrs', methods=['GET'])
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

@bp.route('/api/v2/csrs/<int:csr_id>', methods=['GET'])
@require_auth(['read:csrs'])
def get_csr(csr_id):
    """Get CSR details"""
    cert = Certificate.query.get(csr_id)
    if not cert or not cert.csr:
        return error_response('CSR not found', 404)
    
    data = cert.to_dict(include_private=False)
    # Decode CSR PEM for display
    if cert.csr:
        try:
            data['csr_pem'] = base64.b64decode(cert.csr).decode('utf-8')
        except:
            data['csr_pem'] = cert.csr
    
    return success_response(data=data)

@bp.route('/api/v2/csrs', methods=['POST'])
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
            username=getattr(g, 'user', {}).get('username', 'admin') if hasattr(g, 'user') else 'admin' # TODO: Get real user
        )
        
        return created_response(
            data=cert.to_dict(),
            message='CSR created successfully'
        )
    except Exception as e:
        return error_response(f"Failed to create CSR: {str(e)}", 500)


@bp.route('/api/v2/csrs/upload', methods=['POST'])
@require_auth(['write:csrs'])
def upload_csr():
    """
    Upload CSR from JSON body with PEM content
    
    JSON body:
        pem: PEM-encoded CSR content
        name: Optional display name
    """
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from flask import g
    
    data = request.get_json()
    if not data or not data.get('pem'):
        return error_response('PEM content required', 400)
    
    csr_pem = data['pem'].encode('utf-8') if isinstance(data['pem'], str) else data['pem']
    name = data.get('name', '')
    
    try:
        # Parse CSR
        csr = x509.load_pem_x509_csr(csr_pem, default_backend())
        
        # Extract subject info
        subject = csr.subject
        cn = None
        org = None
        ou = None
        
        for attr in subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                cn = attr.value
            elif attr.oid == x509.oid.NameOID.ORGANIZATION_NAME:
                org = attr.value
            elif attr.oid == x509.oid.NameOID.ORGANIZATIONAL_UNIT_NAME:
                ou = attr.value
        
        # Build subject string
        subject_parts = []
        if cn:
            subject_parts.append(f"CN={cn}")
        if org:
            subject_parts.append(f"O={org}")
        if ou:
            subject_parts.append(f"OU={ou}")
        subject_str = ", ".join(subject_parts) if subject_parts else "Unknown"
        
        # Create Certificate record with CSR (pending)
        # Store CSR as base64-encoded PEM (consistent with other storage)
        new_cert = Certificate(
            refid=str(uuid.uuid4()),
            descr=name or cn or 'Uploaded CSR',
            subject=subject_str,
            csr=base64.b64encode(csr_pem).decode('utf-8'),
            crt=None,  # Not signed yet
            prv=None,  # External CSR, no private key
            source='upload',
            created_by=getattr(g, 'username', 'system')
        )
        
        db.session.add(new_cert)
        db.session.commit()
        
        # Audit log
        from services.audit_service import AuditService
        AuditService.log_action('csr', 'upload', new_cert.id, {'subject': subject_str})
        
        # Return CSR-friendly format
        result = new_cert.to_dict()
        result['status'] = 'Pending'
        result['cn'] = cn
        result['department'] = ou
        
        return created_response(
            data=result,
            message='CSR uploaded successfully'
        )
    except Exception as e:
        return error_response(f"Failed to upload CSR: {str(e)}", 500)


@bp.route('/api/v2/csrs/import', methods=['POST'])
@require_auth(['write:csrs'])
def import_csr():
    """
    Import CSR from file OR pasted PEM content
    
    Form data:
        file: CSR file (optional if pem_content provided)
        pem_content: Pasted PEM content (optional if file provided)
        name: Optional display name
    """
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    
    # Get CSR data from file or pasted content
    csr_pem = None
    
    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        csr_pem = file.read()
    elif request.form.get('pem_content'):
        csr_pem = request.form.get('pem_content').encode('utf-8')
    else:
        return error_response('No file or PEM content provided', 400)
    
    name = request.form.get('name', '')
    
    try:
        # Parse CSR
        csr = x509.load_pem_x509_csr(csr_pem, default_backend())
        
        # Extract subject info
        subject = csr.subject
        cn = None
        org = None
        ou = None
        
        for attr in subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                cn = attr.value
            elif attr.oid == x509.oid.NameOID.ORGANIZATION_NAME:
                org = attr.value
            elif attr.oid == x509.oid.NameOID.ORGANIZATIONAL_UNIT_NAME:
                ou = attr.value
        
        # Build subject string
        subject_parts = []
        for attr in subject:
            subject_parts.append(f"{attr.oid._name}={attr.value}")
        subject_str = ', '.join(subject_parts)
        
        # Extract SANs if present
        san_dns = []
        san_ip = []
        san_email = []
        try:
            san_ext = csr.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            for name_entry in san_ext.value:
                if isinstance(name_entry, x509.DNSName):
                    san_dns.append(name_entry.value)
                elif isinstance(name_entry, x509.IPAddress):
                    san_ip.append(str(name_entry.value))
                elif isinstance(name_entry, x509.RFC822Name):
                    san_email.append(name_entry.value)
        except x509.ExtensionNotFound:
            pass
        
        # Create Certificate record with CSR
        refid = str(uuid.uuid4())
        cert = Certificate(
            refid=refid,
            descr=name or cn or 'Imported CSR',
            csr=base64.b64encode(csr_pem).decode('utf-8'),
            crt=None,  # Not signed yet
            subject=subject_str,
            san_dns=str(san_dns) if san_dns else None,
            san_ip=str(san_ip) if san_ip else None,
            san_email=str(san_email) if san_email else None,
            created_by='import',
            created_at=datetime.datetime.utcnow()
        )
        
        db.session.add(cert)
        db.session.commit()
        
        # Audit log
        from services.audit_service import AuditService
        AuditService.log_action(
            action='csr_imported',
            resource_type='csr',
            resource_id=cert.id,
            resource_name=cert.descr,
            details=f'Imported CSR: {cert.descr}',
            success=True
        )
        
        return created_response(
            data=cert.to_dict(),
            message=f'CSR "{cert.descr}" imported successfully'
        )
        
    except Exception as e:
        import traceback
        print(f"CSR Import Error: {str(e)}")
        print(traceback.format_exc())
        return error_response(f'Import failed: {str(e)}', 500)

@bp.route('/api/v2/csrs/<int:csr_id>/export', methods=['GET'])
@require_auth(['read:csrs'])
def export_csr(csr_id):
    """Export CSR as PEM file"""
    from flask import Response
    
    cert = Certificate.query.get(csr_id)
    if not cert or not cert.csr:
        return error_response('CSR not found', 404)
    
    try:
        csr_pem = base64.b64decode(cert.csr)
        return Response(
            csr_pem,
            mimetype='application/x-pem-file',
            headers={'Content-Disposition': f'attachment; filename="{cert.descr or cert.refid}.csr"'}
        )
    except Exception as e:
        return error_response(f'Export failed: {str(e)}', 500)

@bp.route('/api/v2/csrs/<int:csr_id>', methods=['DELETE'])
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


@bp.route('/api/v2/csrs/<int:csr_id>/sign', methods=['POST'])
@require_auth(['write:csrs', 'write:certificates'])
def sign_csr(csr_id):
    """
    Sign a CSR with a CA to issue a certificate
    
    JSON body:
        ca_id: ID of the CA to sign with
        validity_days: Number of days the certificate should be valid (default: 365)
    """
    from flask import g
    from services.audit_service import AuditService
    from models import CA
    
    cert = Certificate.query.get(csr_id)
    if not cert:
        return error_response('CSR not found', 404)
    
    if not cert.csr:
        return error_response('No CSR data found', 400)
    
    if cert.crt:
        return error_response('CSR already signed', 400)
    
    data = request.get_json() or {}
    ca_id = data.get('ca_id')
    validity_days = data.get('validity_days', 365)
    
    if not ca_id:
        return error_response('CA ID required', 400)
    
    # Get the CA from CA table (not Certificate table)
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    if not ca.crt or not ca.prv:
        return error_response('CA is not valid for signing', 400)
    
    try:
        # Sign the CSR - use CA refid
        signed_cert = CertificateService.sign_csr(
            cert_id=csr_id,
            caref=ca.refid,
            validity_days=validity_days
        )
        
        # Audit log
        AuditService.log_action('certificate', 'sign', csr_id, {
            'ca_id': ca_id,
            'ca_name': ca.descr,
            'validity_days': validity_days,
            'subject': cert.subject
        })
        
        return success_response(
            data=signed_cert.to_dict(),
            message='CSR signed successfully'
        )
    except Exception as e:
        import traceback
        print(f"CSR Sign Error: {str(e)}")
        print(traceback.format_exc())
        return error_response(f"Failed to sign CSR: {str(e)}", 500)
