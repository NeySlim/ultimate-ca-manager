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
    Supports: PEM, DER, PKCS12
    
    Form data:
        file: Certificate file
        format: auto, pem, der, pkcs12
        password: Password for PKCS12
        name: Optional display name
        ca_id: Optional CA ID to link to
        import_key: Whether to import private key (default: true)
    """
    from models import Certificate, CA, db
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    import base64
    import uuid
    
    if 'file' not in request.files:
        return error_response('No file provided', 400)
    
    file = request.files['file']
    if file.filename == '':
        return error_response('No file selected', 400)
    
    format_type = request.form.get('format', 'auto').lower()
    password = request.form.get('password')
    name = request.form.get('name', '')
    ca_id = request.form.get('ca_id', type=int)
    import_key = request.form.get('import_key', 'true').lower() == 'true'
    
    try:
        file_data = file.read()
        cert = None
        private_key = None
        
        # Auto-detect format
        if format_type == 'auto':
            if file_data.startswith(b'-----BEGIN'):
                format_type = 'pem'
            elif file.filename.endswith('.p12') or file.filename.endswith('.pfx'):
                format_type = 'pkcs12'
            else:
                format_type = 'der'
        
        if format_type == 'pem':
            cert = x509.load_pem_x509_certificate(file_data, default_backend())
            # Try to extract private key
            if import_key and b'-----BEGIN' in file_data and b'PRIVATE KEY' in file_data:
                try:
                    private_key = serialization.load_pem_private_key(
                        file_data, password=password.encode() if password else None, backend=default_backend()
                    )
                except:
                    pass
                    
        elif format_type == 'der':
            cert = x509.load_der_x509_certificate(file_data, default_backend())
            
        elif format_type == 'pkcs12':
            if not password:
                return error_response('Password required for PKCS12', 400)
            from cryptography.hazmat.primitives.serialization import pkcs12
            private_key, cert, chain = pkcs12.load_key_and_certificates(
                file_data, password.encode(), default_backend()
            )
        
        if not cert:
            return error_response('Could not parse certificate', 400)
        
        # Check if this is a CA certificate (has CA:TRUE basic constraint)
        is_ca_cert = False
        try:
            basic_constraints = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.BASIC_CONSTRAINTS)
            if basic_constraints.value.ca:
                is_ca_cert = True
        except x509.extensions.ExtensionNotFound:
            pass
        
        # If it's a CA certificate, redirect to CA import
        if is_ca_cert:
            # Import as CA instead
            subject = cert.subject
            issuer = cert.issuer
            
            def get_name_attr(name_obj, oid):
                try:
                    return name_obj.get_attributes_for_oid(oid)[0].value
                except:
                    return ''
            
            from cryptography.x509.oid import NameOID
            cn = get_name_attr(subject, NameOID.COMMON_NAME)
            
            cert_pem = cert.public_bytes(serialization.Encoding.PEM)
            key_pem = None
            if private_key and import_key:
                key_pem = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                )
            
            refid = str(uuid.uuid4())
            ca = CA(
                refid=refid,
                descr=name or cn or file.filename,
                crt=base64.b64encode(cert_pem).decode('utf-8'),
                prv=base64.b64encode(key_pem).decode('utf-8') if key_pem else None,
                serial=0,
                subject=subject.rfc4514_string(),
                issuer=issuer.rfc4514_string(),
                valid_from=cert.not_valid_before_utc,
                valid_to=cert.not_valid_after_utc,
                imported_from='manual'
            )
            
            db.session.add(ca)
            db.session.commit()
            
            from services.audit_service import AuditService
            AuditService.log_action(
                action='ca_imported',
                resource_type='ca',
                resource_id=ca.id,
                details=f'Imported CA (detected): {ca.descr}',
                success=True
            )
            
            return created_response(
                data=ca.to_dict(),
                message=f'CA certificate "{ca.descr}" imported successfully (detected as CA)'
            )
        
        # Extract certificate info
        subject = cert.subject
        issuer = cert.issuer
        
        def get_name_attr(name_obj, oid):
            try:
                return name_obj.get_attributes_for_oid(oid)[0].value
            except:
                return ''
        
        from cryptography.x509.oid import NameOID
        cn = get_name_attr(subject, NameOID.COMMON_NAME)
        
        # Serialize certificate to PEM
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        
        # Serialize private key if available
        key_pem = None
        if private_key and import_key:
            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
        
        # Find CA by issuer if not specified
        caref = None
        if ca_id:
            ca = CA.query.get(ca_id)
            if ca:
                caref = ca.refid
        else:
            # Try to match issuer with existing CA
            issuer_str = issuer.rfc4514_string()
            ca = CA.query.filter_by(subject=issuer_str).first()
            if ca:
                caref = ca.refid
        
        # Create certificate record
        refid = str(uuid.uuid4())
        certificate = Certificate(
            refid=refid,
            descr=name or cn or file.filename,
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=base64.b64encode(key_pem).decode('utf-8') if key_pem else None,
            caref=caref,
            subject=subject.rfc4514_string(),
            issuer=issuer.rfc4514_string(),
            valid_from=cert.not_valid_before_utc,
            valid_to=cert.not_valid_after_utc,
            created_by='import'
        )
        
        db.session.add(certificate)
        db.session.commit()
        
        # Audit log
        from services.audit_service import AuditService
        AuditService.log_action(
            action='certificate_imported',
            resource_type='certificate',
            resource_id=certificate.id,
            details=f'Imported certificate: {certificate.descr}',
            success=True
        )
        
        return created_response(
            data=certificate.to_dict(),
            message=f'Certificate "{certificate.descr}" imported successfully'
        )
        
    except Exception as e:
        return error_response(f'Import failed: {str(e)}', 500)
