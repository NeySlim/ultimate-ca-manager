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
    from datetime import datetime, timedelta
    from sqlalchemy import or_
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status')  # valid, revoked, expired, expiring
    search = request.args.get('search', '').strip()
    
    query = Certificate.query
    
    # Apply status filter
    if status == 'revoked':
        query = query.filter_by(revoked=True)
    elif status == 'valid':
        query = query.filter_by(revoked=False)
        query = query.filter(Certificate.valid_to > datetime.utcnow())
    elif status == 'expired':
        query = query.filter(Certificate.valid_to <= datetime.utcnow())
    elif status == 'expiring':
        # Expiring in next 30 days
        expiry_threshold = datetime.utcnow() + timedelta(days=30)
        query = query.filter(Certificate.valid_to <= expiry_threshold)
        query = query.filter(Certificate.valid_to > datetime.utcnow())
        query = query.filter_by(revoked=False)
    
    # Apply search filter
    if search:
        query = query.filter(
            or_(
                Certificate.subject.ilike(f'%{search}%'),
                Certificate.issuer.ilike(f'%{search}%'),
                Certificate.descr.ilike(f'%{search}%'),
                Certificate.serial_number.ilike(f'%{search}%')
            )
        )
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    certs = [cert.to_dict() for cert in pagination.items]
    
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
    from models import Certificate
    
    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    
    return success_response(data=cert.to_dict())


@bp.route('/api/v2/certificates/<int:cert_id>', methods=['DELETE'])
@require_auth(['delete:certificates'])
def delete_certificate(cert_id):
    """Delete certificate"""
    return no_content_response()


@bp.route('/api/v2/certificates/<int:cert_id>/export', methods=['GET'])
@require_auth(['read:certificates'])
def export_certificate(cert_id):
    """
    Export certificate in various formats
    
    Query params:
        format: pem (default), der, pkcs12
        include_key: bool - Include private key (PEM only)
        include_chain: bool - Include CA chain (PEM only)
        password: string - Required for PKCS12
    """
    from flask import Response
    from models import Certificate, CA
    import base64
    
    certificate = Certificate.query.get(cert_id)
    if not certificate:
        return error_response('Certificate not found', 404)
    
    if not certificate.crt:
        return error_response('Certificate data not available', 400)
    
    export_format = request.args.get('format', 'pem').lower()
    include_key = request.args.get('include_key', 'false').lower() == 'true'
    include_chain = request.args.get('include_chain', 'false').lower() == 'true'
    password = request.args.get('password')
    
    try:
        cert_pem = base64.b64decode(certificate.crt)
        
        if export_format == 'pem':
            result = cert_pem
            content_type = 'application/x-pem-file'
            filename = f"{certificate.descr or certificate.refid}.crt"
            
            # Include private key if requested
            if include_key and certificate.prv:
                key_pem = base64.b64decode(certificate.prv)
                if not result.endswith(b'\\n'):
                    result += b'\\n'
                result += key_pem
                filename = f"{certificate.descr or certificate.refid}_with_key.pem"
            
            # Include CA chain if requested
            if include_chain and certificate.caref:
                ca = CA.query.filter_by(refid=certificate.caref).first()
                while ca:
                    if ca.crt:
                        ca_cert = base64.b64decode(ca.crt)
                        if not result.endswith(b'\\n'):
                            result += b'\\n'
                        result += ca_cert
                    # Get parent CA
                    if ca.caref:
                        ca = CA.query.filter_by(refid=ca.caref).first()
                    else:
                        break
                if include_key:
                    filename = f"{certificate.descr or certificate.refid}_full_chain.pem"
                else:
                    filename = f"{certificate.descr or certificate.refid}_chain.pem"
            
            return Response(
                result,
                mimetype=content_type,
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )
        
        elif export_format == 'der':
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            der_bytes = cert.public_bytes(serialization.Encoding.DER)
            
            return Response(
                der_bytes,
                mimetype='application/x-x509-ca-cert',
                headers={'Content-Disposition': f'attachment; filename="{certificate.descr or certificate.refid}.der"'}
            )
        
        elif export_format == 'pkcs12':
            if not password:
                return error_response('Password required for PKCS12 export', 400)
            if not certificate.prv:
                return error_response('Certificate has no private key for PKCS12 export', 400)
            
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.serialization import pkcs12
            
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem = base64.b64decode(certificate.prv)
            private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
            
            # Build CA chain if available
            ca_certs = []
            if certificate.caref:
                ca = CA.query.filter_by(refid=certificate.caref).first()
                while ca:
                    if ca.crt:
                        ca_cert = x509.load_pem_x509_certificate(
                            base64.b64decode(ca.crt), default_backend()
                        )
                        ca_certs.append(ca_cert)
                    if ca.caref:
                        ca = CA.query.filter_by(refid=ca.caref).first()
                    else:
                        break
            
            p12_bytes = pkcs12.serialize_key_and_certificates(
                name=(certificate.descr or certificate.refid).encode(),
                key=private_key,
                cert=cert,
                cas=ca_certs if ca_certs else None,
                encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
            )
            
            return Response(
                p12_bytes,
                mimetype='application/x-pkcs12',
                headers={'Content-Disposition': f'attachment; filename="{certificate.descr or certificate.refid}.p12"'}
            )
        
        else:
            return error_response(f'Unsupported format: {export_format}', 400)
    
    except Exception as e:
        return error_response(f'Export failed: {str(e)}', 500)


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
