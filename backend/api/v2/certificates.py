"""
Certificates Management Routes v2.0
/api/certificates/* - Certificate CRUD
"""

from flask import Blueprint, request, g
import re
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response

bp = Blueprint('certificates_v2', __name__)


# SECURITY: DN field validation patterns (reused from cas.py)
DN_FIELD_PATTERNS = {
    'CN': re.compile(r'^[\w\s\-\.\,\'\@\(\)\*]+$', re.UNICODE),  # CN allows wildcards
    'O': re.compile(r'^[\w\s\-\.\,\'\&]+$', re.UNICODE),
    'OU': re.compile(r'^[\w\s\-\.\,\'\&]+$', re.UNICODE),
    'C': re.compile(r'^[A-Z]{2}$'),
    'ST': re.compile(r'^[\w\s\-\.]+$', re.UNICODE),
    'L': re.compile(r'^[\w\s\-\.]+$', re.UNICODE),
}

MAX_DN_FIELD_LENGTH = 64


def validate_dn_field(field_name, value):
    """Validate DN field for security"""
    if not value:
        return True, None
    
    value = str(value).strip()
    
    if len(value) > MAX_DN_FIELD_LENGTH:
        return False, f"{field_name} must be {MAX_DN_FIELD_LENGTH} characters or less"
    
    if field_name in DN_FIELD_PATTERNS:
        if not DN_FIELD_PATTERNS[field_name].match(value):
            return False, f"Invalid characters in {field_name}"
    
    dangerous_patterns = [';', '|', '`', '$', '\\n', '\\r', '\x00', '\n', '\r']
    for pattern in dangerous_patterns:
        if pattern in value:
            return False, f"Invalid character in {field_name}"
    
    return True, None


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
    ca_id = request.args.get('ca_id', type=int)  # Filter by CA
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'subject')  # Default sort by subject (common_name)
    sort_order = request.args.get('sort_order', 'asc')  # Default ascending (A-Z)
    
    # Whitelist of allowed sort columns
    ALLOWED_SORT_COLUMNS = {
        'subject': Certificate.subject_cn,  # Sort by CN, not full DN
        'subject_cn': Certificate.subject_cn,
        'issuer': Certificate.issuer,
        'valid_to': Certificate.valid_to,
        'valid_from': Certificate.valid_from,
        'created_at': Certificate.created_at,
        'serial_number': Certificate.serial_number,
        'revoked': Certificate.revoked,
        'descr': Certificate.descr,
        'key_algo': Certificate.key_algo,
        'status': 'special'  # Handled separately with CASE
    }
    
    query = Certificate.query
    
    # Apply CA filter
    if ca_id:
        query = query.filter_by(ca_id=ca_id)
    
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
    
    # Apply sorting BEFORE pagination (use whitelist)
    sort_column = ALLOWED_SORT_COLUMNS.get(sort_by, Certificate.subject)
    
    if sort_by == 'status':
        # Special handling: sort by computed status (revoked > expired > expiring > valid)
        # Then alphabetically by subject within each group
        from sqlalchemy import case
        now = datetime.utcnow()
        expiry_threshold = now + timedelta(days=30)
        
        # Status priority: 1=revoked, 2=expired, 3=expiring, 4=valid
        status_order = case(
            (Certificate.revoked == True, 1),
            (Certificate.valid_to <= now, 2),
            (Certificate.valid_to <= expiry_threshold, 3),
            else_=4
        )
        
        if sort_order == 'desc':
            query = query.order_by(status_order.desc(), Certificate.subject.asc())
        else:
            query = query.order_by(status_order.asc(), Certificate.subject.asc())
    elif sort_column != 'special':
        if sort_order == 'desc':
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    certs = [cert.to_dict() for cert in pagination.items]
    
    return success_response(
        data=certs,
        meta={'total': pagination.total, 'page': page, 'per_page': per_page}
    )


@bp.route('/api/v2/certificates/stats', methods=['GET'])
@require_auth(['read:certificates'])
def get_certificate_stats():
    """Get certificate statistics"""
    from models import Certificate
    from datetime import datetime, timedelta
    
    now = datetime.utcnow()
    expiry_threshold = now + timedelta(days=30)
    
    total = Certificate.query.count()
    revoked = Certificate.query.filter_by(revoked=True).count()
    expired = Certificate.query.filter(
        Certificate.valid_to <= now,
        Certificate.revoked == False
    ).count()
    expiring = Certificate.query.filter(
        Certificate.valid_to <= expiry_threshold,
        Certificate.valid_to > now,
        Certificate.revoked == False
    ).count()
    valid = Certificate.query.filter(
        Certificate.valid_to > now,
        Certificate.revoked == False
    ).count() - expiring  # Don't double-count expiring as valid
    
    return success_response(data={
        'total': total,
        'valid': valid,
        'expiring': expiring,
        'expired': expired,
        'revoked': revoked
    })


@bp.route('/api/v2/certificates', methods=['POST'])
@require_auth(['write:certificates'])
def create_certificate():
    """Create certificate - Real implementation"""
    from models import Certificate, CA, db
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, ec
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    from datetime import datetime, timedelta
    import base64
    import uuid
    import json
    
    data = request.json
    
    if not data or not data.get('cn'):
        return error_response('Common Name (cn) is required', 400)
    
    if not data.get('ca_id'):
        return error_response('CA ID is required', 400)
    
    # SECURITY: Validate DN fields
    dn_validations = [
        ('CN', data.get('cn')),
        ('O', data.get('organization')),
        ('OU', data.get('organizational_unit')),
        ('C', (data.get('country') or '').upper() or None),
        ('ST', data.get('state')),
        ('L', data.get('locality')),
    ]
    for field_name, value in dn_validations:
        is_valid, error = validate_dn_field(field_name, value)
        if not is_valid:
            return error_response(error, 400)
    
    # Get the CA
    ca = CA.query.get(data['ca_id'])
    if not ca:
        return error_response('CA not found', 404)
    
    if not ca.prv:
        return error_response('CA private key not available', 400)
    
    try:
        # Load CA certificate and key
        ca_cert_pem = base64.b64decode(ca.crt)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
        ca_key_pem = base64.b64decode(ca.prv)
        ca_key = serialization.load_pem_private_key(ca_key_pem, password=None, backend=default_backend())
        
        # Generate key pair
        key_type = data.get('key_type', 'RSA')
        key_size = int(data.get('key_size') or 2048)
        
        if key_type.upper() == 'EC':
            curve_name = data.get('curve', 'secp256r1')
            curves = {
                'secp256r1': ec.SECP256R1(),
                'secp384r1': ec.SECP384R1(),
                'secp521r1': ec.SECP521R1(),
            }
            curve = curves.get(curve_name, ec.SECP256R1())
            new_key = ec.generate_private_key(curve, default_backend())
        else:
            new_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=key_size,
                backend=default_backend()
            )
        
        # Build subject
        subject_attrs = [x509.NameAttribute(NameOID.COMMON_NAME, data['cn'])]
        if data.get('organization'):
            subject_attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, data['organization']))
        if data.get('organizational_unit'):
            subject_attrs.append(x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, data['organizational_unit']))
        if data.get('country'):
            subject_attrs.append(x509.NameAttribute(NameOID.COUNTRY_NAME, data['country'].upper()))
        if data.get('state'):
            subject_attrs.append(x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, data['state']))
        if data.get('locality'):
            subject_attrs.append(x509.NameAttribute(NameOID.LOCALITY_NAME, data['locality']))
        if data.get('email'):
            subject_attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, data['email']))
        
        subject = x509.Name(subject_attrs)
        
        # Validity
        validity_days = data.get('validity_days', 365)
        now = datetime.utcnow()
        not_before = now
        not_after = now + timedelta(days=validity_days)
        
        # Build certificate
        builder = x509.CertificateBuilder()
        builder = builder.subject_name(subject)
        builder = builder.issuer_name(ca_cert.subject)
        builder = builder.public_key(new_key.public_key())
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.not_valid_before(not_before)
        builder = builder.not_valid_after(not_after)
        
        # Basic Constraints (not a CA)
        builder = builder.add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True
        )
        
        # Key Usage
        cert_type = data.get('cert_type', 'server')
        if cert_type == 'server':
            builder = builder.add_extension(
                x509.KeyUsage(
                    digital_signature=True, key_encipherment=True, content_commitment=False,
                    data_encipherment=False, key_agreement=False, key_cert_sign=False,
                    crl_sign=False, encipher_only=False, decipher_only=False
                ),
                critical=True
            )
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                critical=False
            )
        elif cert_type == 'client':
            builder = builder.add_extension(
                x509.KeyUsage(
                    digital_signature=True, key_encipherment=False, content_commitment=False,
                    data_encipherment=False, key_agreement=False, key_cert_sign=False,
                    crl_sign=False, encipher_only=False, decipher_only=False
                ),
                critical=True
            )
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False
            )
        else:  # combined
            builder = builder.add_extension(
                x509.KeyUsage(
                    digital_signature=True, key_encipherment=True, content_commitment=False,
                    data_encipherment=False, key_agreement=False, key_cert_sign=False,
                    crl_sign=False, encipher_only=False, decipher_only=False
                ),
                critical=True
            )
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False
            )
        
        # Subject Alternative Names
        san_list = []
        if data.get('san_dns'):
            for dns in data['san_dns']:
                san_list.append(x509.DNSName(dns))
        if data.get('san_ip'):
            from ipaddress import ip_address
            for ip in data['san_ip']:
                san_list.append(x509.IPAddress(ip_address(ip)))
        if data.get('san_email'):
            for email in data['san_email']:
                san_list.append(x509.RFC822Name(email))
        
        # Always include CN as DNS SAN for server certs
        if cert_type in ['server', 'combined'] and data['cn'] not in (data.get('san_dns') or []):
            san_list.insert(0, x509.DNSName(data['cn']))
        
        if san_list:
            builder = builder.add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False
            )
        
        # Subject Key Identifier
        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(new_key.public_key()),
            critical=False
        )
        
        # Authority Key Identifier
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False
        )
        
        # Sign certificate
        new_cert = builder.sign(ca_key, hashes.SHA256(), default_backend())
        
        # Serialize
        cert_pem = new_cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
        key_pem = new_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        
        # Save to database
        # Extract SKI/AKI from issued cert
        from cryptography.x509.oid import ExtensionOID
        cert_ski = None
        cert_aki = None
        try:
            ext = new_cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
            cert_ski = ext.value.key_identifier.hex(':').upper()
        except Exception:
            pass
        try:
            ext = new_cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
            if ext.value.key_identifier:
                cert_aki = ext.value.key_identifier.hex(':').upper()
        except Exception:
            pass

        db_cert = Certificate(
            refid=str(uuid.uuid4())[:8],
            descr=data.get('description', data['cn']),
            caref=ca.refid,
            crt=base64.b64encode(cert_pem.encode()).decode(),
            prv=base64.b64encode(key_pem.encode()).decode(),
            cert_type=cert_type,
            subject=','.join(f'{attr.oid._name}={attr.value}' for attr in subject),
            issuer=','.join(f'{attr.oid._name}={attr.value}' for attr in ca_cert.subject),
            serial_number=format(new_cert.serial_number, 'x'),
            aki=cert_aki,
            ski=cert_ski,
            valid_from=not_before,
            valid_to=not_after,
            san_dns=json.dumps(data.get('san_dns', [])),
            san_ip=json.dumps(data.get('san_ip', [])),
            san_email=json.dumps(data.get('san_email', [])),
            created_by=g.current_user.username if hasattr(g, 'current_user') else None
        )
        
        db.session.add(db_cert)
        db.session.commit()
        
        # Audit log
        try:
            from services.audit_service import AuditService
            AuditService.log(
                action='certificate_created',
                user_id=g.current_user.id if hasattr(g, 'current_user') else None,
                details={'certificate_id': db_cert.id, 'cn': data['cn'], 'ca_id': ca.id}
            )
        except Exception:
            pass
        
        # Send notification
        try:
            from services.notification_service import NotificationService
            username = g.current_user.username if hasattr(g, 'current_user') else 'system'
            NotificationService.on_certificate_issued(db_cert, username)
        except Exception:
            pass  # Non-blocking
        
        # WebSocket event
        try:
            from websocket.emitters import on_certificate_issued
            on_certificate_issued(
                cert_id=db_cert.id,
                cn=data['cn'],
                ca_id=ca.id,
                issuer=ca.name,
                valid_to=not_after.isoformat() if not_after else None
            )
        except Exception:
            pass  # Non-blocking
        
        return created_response(
            data=db_cert.to_dict(),
            message='Certificate created successfully'
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to create certificate: {str(e)}', 500)


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
    from models import Certificate, db
    
    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    
    cert_name = cert.descr or cert.descr or f'Certificate #{cert_id}'
    
    # Delete the certificate
    db.session.delete(cert)
    db.session.commit()
    
    # Audit log
    from services.audit_service import AuditService
    AuditService.log_action(
        action='certificate_deleted',
        resource_type='certificate',
        resource_id=cert_id,
        resource_name=cert_name,
        details=f'Deleted certificate: {cert_name}',
        success=True
    )
    
    return no_content_response()


@bp.route('/api/v2/certificates/export', methods=['GET'])
@require_auth(['read:certificates'])
def export_all_certificates():
    """Export all certificates in various formats"""
    from flask import Response
    from models import Certificate, CA
    import base64
    import subprocess
    import tempfile
    import os
    
    export_format = request.args.get('format', 'pem').lower()
    include_chain = request.args.get('include_chain', 'false').lower() == 'true'
    
    certificates = Certificate.query.filter(Certificate.crt.isnot(None)).all()
    if not certificates:
        return error_response('No certificates to export', 404)
    
    try:
        if export_format == 'pem':
            # Concatenate all PEM certificates
            pem_data = b''
            for cert in certificates:
                if cert.crt:
                    pem_data += base64.b64decode(cert.crt)
                    if not pem_data.endswith(b'\n'):
                        pem_data += b'\n'
            
            return Response(
                pem_data,
                mimetype='application/x-pem-file',
                headers={'Content-Disposition': 'attachment; filename="certificates.pem"'}
            )
        
        elif export_format == 'pkcs7' or export_format == 'p7b':
            # Create temp file with all PEM certs
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                for cert in certificates:
                    if cert.crt:
                        f.write(base64.b64decode(cert.crt))
                        f.write(b'\n')
                pem_file = f.name
            
            try:
                p7b_output = subprocess.check_output([
                    'openssl', 'crl2pkcs7', '-nocrl',
                    '-certfile', pem_file,
                    '-outform', 'DER'
                ], stderr=subprocess.DEVNULL)
                
                return Response(
                    p7b_output,
                    mimetype='application/x-pkcs7-certificates',
                    headers={'Content-Disposition': 'attachment; filename="certificates.p7b"'}
                )
            finally:
                os.unlink(pem_file)
        
        else:
            return error_response(f'Bulk export only supports PEM and P7B formats. Use individual export for DER/PKCS12/PFX', 400)
    
    except Exception as e:
        return error_response(f'Export failed: {str(e)}', 500)


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
        
        elif export_format == 'pkcs7' or export_format == 'p7b':
            import subprocess
            import tempfile
            import os
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            
            # Create temporary PEM file
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                f.write(cert_pem)
                # Include CA chain if requested
                if include_chain and certificate.caref:
                    ca = CA.query.filter_by(refid=certificate.caref).first()
                    while ca:
                        if ca.crt:
                            f.write(b'\n')
                            f.write(base64.b64decode(ca.crt))
                        if ca.caref:
                            ca = CA.query.filter_by(refid=ca.caref).first()
                        else:
                            break
                pem_file = f.name
            
            try:
                # Convert to PKCS7 using OpenSSL
                p7b_output = subprocess.check_output([
                    'openssl', 'crl2pkcs7', '-nocrl',
                    '-certfile', pem_file,
                    '-outform', 'DER'
                ], stderr=subprocess.DEVNULL)
                
                return Response(
                    p7b_output,
                    mimetype='application/x-pkcs7-certificates',
                    headers={'Content-Disposition': f'attachment; filename="{certificate.descr or certificate.refid}.p7b"'}
                )
            finally:
                os.unlink(pem_file)
        
        elif export_format == 'pfx':
            # PFX is same as PKCS12
            if not password:
                return error_response('Password required for PFX export', 400)
            if not certificate.prv:
                return error_response('Certificate has no private key for PFX export', 400)
            
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.serialization import pkcs12
            
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem = base64.b64decode(certificate.prv)
            private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
            
            # Build CA chain
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
                headers={'Content-Disposition': f'attachment; filename="{certificate.descr or certificate.refid}.pfx"'}
            )
        
        else:
            return error_response(f'Unsupported format: {export_format}', 400)
    
    except Exception as e:
        return error_response(f'Export failed: {str(e)}', 500)


@bp.route('/api/v2/certificates/<int:cert_id>/revoke', methods=['POST'])
@require_auth(['write:certificates'])
def revoke_certificate(cert_id):
    """Revoke certificate"""
    from models import Certificate, db
    from services.cert_service import CertificateService
    from services.audit_service import AuditService
    
    data = request.json
    reason = data.get('reason', 'unspecified') if data else 'unspecified'
    
    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    
    if cert.revoked:
        return error_response('Certificate already revoked', 400)
    
    try:
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'
        
        # Revoke using service
        cert = CertificateService.revoke_certificate(
            cert_id=cert_id,
            reason=reason,
            username=username
        )
        
        # Send notification
        try:
            from services.notification_service import NotificationService
            NotificationService.on_certificate_revoked(cert, reason, username)
        except Exception:
            pass  # Non-blocking
        
        # WebSocket event
        try:
            from websocket.emitters import on_certificate_revoked
            on_certificate_revoked(
                cert_id=cert.id,
                cn=cert.descr or cert.refid,
                reason=reason,
                revoked_by=username
            )
        except Exception:
            pass  # Non-blocking
        
        return success_response(
            data=cert.to_dict(),
            message='Certificate revoked successfully'
        )
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        return error_response(f'Failed to revoke certificate: {str(e)}', 500)


@bp.route('/api/v2/certificates/<int:cert_id>/key', methods=['POST'])
@require_auth(['write:certificates'])
def upload_private_key(cert_id):
    """
    Upload/attach a private key to an existing certificate
    
    Request body:
    - key: Private key in PEM format (raw or base64 encoded)
    - passphrase: Optional passphrase if key is encrypted
    """
    from models import Certificate, db
    from services.audit_service import AuditService
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509 import load_pem_x509_certificate
    import base64
    
    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    
    if cert.has_private_key:
        return error_response('Certificate already has a private key', 400)
    
    data = request.json
    if not data or not data.get('key'):
        return error_response('Private key is required', 400)
    
    key_data = data['key'].strip()
    passphrase = data.get('passphrase')
    
    try:
        # Decode key if base64 encoded
        if not key_data.startswith('-----BEGIN'):
            try:
                key_data = base64.b64decode(key_data).decode('utf-8')
            except Exception:
                return error_response('Invalid key format - must be PEM or base64-encoded PEM', 400)
        
        # Validate key format
        if 'PRIVATE KEY' not in key_data:
            return error_response('Invalid private key format', 400)
        
        # Try to load the key to validate it
        key_bytes = key_data.encode('utf-8')
        password = passphrase.encode('utf-8') if passphrase else None
        
        try:
            private_key = serialization.load_pem_private_key(
                key_bytes,
                password=password,
                backend=default_backend()
            )
        except Exception as e:
            if 'password' in str(e).lower() or 'decrypt' in str(e).lower():
                return error_response('Private key is encrypted - please provide passphrase', 400)
            return error_response(f'Invalid private key: {str(e)}', 400)
        
        # Verify key matches certificate public key
        if cert.crt:
            try:
                cert_pem = base64.b64decode(cert.crt)
                certificate = load_pem_x509_certificate(cert_pem, default_backend())
                cert_public_key = certificate.public_key()
                key_public_key = private_key.public_key()
                
                # Compare public key bytes
                cert_pub_bytes = cert_public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )
                key_pub_bytes = key_public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )
                
                if cert_pub_bytes != key_pub_bytes:
                    return error_response('Private key does not match certificate public key', 400)
            except Exception as e:
                return error_response(f'Failed to verify key matches certificate: {str(e)}', 400)
        
        # Store key (decrypt if needed, re-encode without password)
        unencrypted_key = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        # Encrypt with our key encryption if configured
        from security.encryption import encrypt_private_key
        key_encoded = base64.b64encode(unencrypted_key).decode('utf-8')
        cert.prv = encrypt_private_key(key_encoded)
        
        db.session.commit()
        
        # Audit log
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'
        AuditService.log_action(
            action='certificate_key_uploaded',
            resource_type='certificate',
            resource_id=cert_id,
            resource_name=cert.descr or f'Certificate #{cert_id}',
            details=f'Private key uploaded by {username}',
            success=True
        )
        
        return success_response(
            data=cert.to_dict(),
            message='Private key uploaded successfully'
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to upload private key: {str(e)}', 500)


@bp.route('/api/v2/certificates/<int:cert_id>/renew', methods=['POST'])
@require_auth(['write:certificates'])
def renew_certificate(cert_id):
    """
    Renew certificate - Creates a new certificate with same subject/SANs but new validity
    """
    from models import Certificate, CA, db
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, ec
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509.oid import NameOID, ExtensionOID
    from datetime import datetime, timedelta
    import base64
    import uuid
    from flask import g
    from services.audit_service import AuditService
    
    # Get original certificate
    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    
    if not cert.crt:
        return error_response('Certificate data not available', 400)
    
    # Get the CA that issued this certificate
    # Try by refid first, then by matching issuer to CA subject
    ca = CA.query.filter_by(refid=cert.caref).first()
    if not ca and cert.issuer:
        # Try to find CA by matching subject to certificate's issuer
        ca = CA.query.filter(CA.subject == cert.issuer).first()
        if not ca:
            # Try partial match (issuer might have different formatting)
            for potential_ca in CA.query.all():
                if potential_ca.subject and cert.issuer:
                    # Extract CN from both and compare
                    ca_cn = potential_ca.subject.split('CN=')[1].split(',')[0] if 'CN=' in potential_ca.subject else None
                    cert_issuer_cn = cert.issuer.split('CN=')[1].split(',')[0] if 'CN=' in cert.issuer else None
                    if ca_cn and cert_issuer_cn and ca_cn == cert_issuer_cn:
                        ca = potential_ca
                        break
    
    if not ca:
        return error_response('Issuing CA not found. The CA that signed this certificate is not in the system.', 404)
    
    if not ca.prv:
        return error_response('CA private key not available. Cannot renew without CA private key.', 400)
    
    try:
        # Load original certificate
        orig_cert_pem = base64.b64decode(cert.crt)
        orig_cert = x509.load_pem_x509_certificate(orig_cert_pem, default_backend())
        
        # Load CA certificate and key
        ca_cert_pem = base64.b64decode(ca.crt)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
        ca_key_pem = base64.b64decode(ca.prv)
        ca_key = serialization.load_pem_private_key(ca_key_pem, password=None, backend=default_backend())
        
        # Generate new key pair (same type and size as original)
        orig_pub_key = orig_cert.public_key()
        if isinstance(orig_pub_key, rsa.RSAPublicKey):
            key_size = orig_pub_key.key_size
            new_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=key_size,
                backend=default_backend()
            )
        elif isinstance(orig_pub_key, ec.EllipticCurvePublicKey):
            curve = orig_pub_key.curve
            new_key = ec.generate_private_key(curve, default_backend())
        else:
            # Default to RSA 2048
            new_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
        
        # Calculate new validity (same duration as original, starting now)
        orig_duration = orig_cert.not_valid_after_utc - orig_cert.not_valid_before_utc
        validity_days = orig_duration.days if orig_duration.days > 0 else 365
        
        now = datetime.utcnow()
        not_before = now
        not_after = now + timedelta(days=validity_days)
        
        # Build new certificate with same subject and extensions
        builder = x509.CertificateBuilder()
        builder = builder.subject_name(orig_cert.subject)
        builder = builder.issuer_name(ca_cert.subject)
        builder = builder.public_key(new_key.public_key())
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.not_valid_before(not_before)
        builder = builder.not_valid_after(not_after)
        
        # Copy extensions from original certificate
        for ext in orig_cert.extensions:
            # Skip Authority Key Identifier (will be regenerated)
            if ext.oid == ExtensionOID.AUTHORITY_KEY_IDENTIFIER:
                continue
            # Skip Subject Key Identifier (will be regenerated for new key)
            if ext.oid == ExtensionOID.SUBJECT_KEY_IDENTIFIER:
                continue
            try:
                builder = builder.add_extension(ext.value, ext.critical)
            except Exception:
                # Skip extensions that can't be copied
                pass
        
        # Add Subject Key Identifier for new key
        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(new_key.public_key()),
            critical=False
        )
        
        # Add Authority Key Identifier
        try:
            builder = builder.add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                critical=False
            )
        except Exception:
            pass
        
        # Sign new certificate
        new_cert = builder.sign(ca_key, hashes.SHA256(), default_backend())
        
        # Serialize to PEM
        new_cert_pem = new_cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
        new_key_pem = new_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        
        # Update existing certificate IN-PLACE (replace, no archive)
        cert.crt = base64.b64encode(new_cert_pem.encode()).decode()
        cert.prv = base64.b64encode(new_key_pem.encode()).decode()
        cert.serial_number = format(new_cert.serial_number, 'x')
        cert.valid_from = not_before
        cert.valid_to = not_after
        cert.revoked = False
        cert.revoked_at = None
        cert.revoke_reason = None
        
        db.session.commit()
        
        # Audit log
        try:
            AuditService.log(
                action='certificate_renewed',
                user_id=g.current_user.id if hasattr(g, 'current_user') else None,
                details={
                    'certificate_id': cert_id,
                    'subject': cert.subject,
                    'valid_until': not_after.isoformat()
                }
            )
        except Exception:
            pass
        
        return success_response(
            data=cert.to_dict(),
            message='Certificate renewed successfully'
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to renew certificate: {str(e)}', 500)


@bp.route('/api/v2/certificates/import', methods=['POST'])
@require_auth(['write:certificates'])
def import_certificate():
    """
    Import certificate from file OR pasted PEM content
    Supports: PEM, DER, PKCS12, PKCS7
    Auto-detects CA certificates and stores them in CA table
    Auto-updates existing cert/CA if duplicate found
    
    Form data:
        file: Certificate file (optional if pem_content provided)
        pem_content: Pasted PEM content (optional if file provided)
        password: Password for PKCS12
        name: Optional display name
        ca_id: Optional CA ID to link to
        import_key: Whether to import private key (default: true)
        update_existing: Whether to update if duplicate found (default: true)
    """
    from models import Certificate, CA, db
    from services.import_service import (
        parse_certificate_file, is_ca_certificate, extract_cert_info,
        find_existing_ca, find_existing_certificate,
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
    ca_id = request.form.get('ca_id', type=int)
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
        
        # Check if this is a CA certificate - auto-route to CA table
        if is_ca_certificate(cert):
            # Check for existing CA
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
                existing_ca.ski = cert_info.get('ski')
                
                db.session.commit()
                
                from services.audit_service import AuditService
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
                    message=f'CA certificate "{existing_ca.descr}" updated (already existed)'
                )
            
            # Create new CA
            refid = str(uuid.uuid4())
            ca = CA(
                refid=refid,
                descr=name or cert_info['cn'] or file.filename,
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
            
            from services.audit_service import AuditService
            AuditService.log_action(
                action='ca_imported',
                resource_type='ca',
                resource_id=ca.id,
                resource_name=ca.descr,
                details=f'Imported CA (auto-detected): {ca.descr}',
                success=True
            )
            
            return created_response(
                data=ca.to_dict(),
                message=f'CA certificate "{ca.descr}" imported successfully (detected as CA)'
            )
        
        # Check for existing certificate
        existing_cert = find_existing_certificate(cert_info)
        
        if existing_cert:
            if not update_existing:
                return error_response(
                    f'Certificate with subject "{cert_info["cn"]}" already exists (ID: {existing_cert.id})',
                    409
                )
            
            # Update existing certificate
            existing_cert.descr = name or cert_info['cn'] or existing_cert.descr
            existing_cert.crt = base64.b64encode(cert_pem).decode('utf-8')
            if key_pem:
                existing_cert.prv = base64.b64encode(key_pem).decode('utf-8')
            existing_cert.valid_from = cert_info['valid_from']
            existing_cert.valid_to = cert_info['valid_to']
            existing_cert.aki = cert_info.get('aki')
            existing_cert.ski = cert_info.get('ski')
            
            # Update CA link if provided
            if ca_id:
                ca = CA.query.get(ca_id)
                if ca:
                    existing_cert.caref = ca.refid
            
            db.session.commit()
            
            from services.audit_service import AuditService
            AuditService.log_action(
                action='certificate_updated',
                resource_type='certificate',
                resource_id=existing_cert.id,
                resource_name=existing_cert.descr,
                details=f'Updated certificate via import: {existing_cert.descr}',
                success=True
            )
            
            return success_response(
                data=existing_cert.to_dict(),
                message=f'Certificate "{existing_cert.descr}" updated (already existed)'
            )
        
        # Regular certificate - find parent CA
        caref = None
        if ca_id:
            ca = CA.query.get(ca_id)
            if ca:
                caref = ca.refid
        else:
            # Auto-link: AKI→SKI first (cryptographically reliable), then issuer DN fallback
            aki = cert_info.get('aki')
            if aki:
                ca = CA.query.filter_by(ski=aki).first()
                if ca:
                    caref = ca.refid
            if not caref:
                ca = CA.query.filter_by(subject=cert_info['issuer']).first()
                if ca:
                    caref = ca.refid
        
        # Create certificate record
        refid = str(uuid.uuid4())
        certificate = Certificate(
            refid=refid,
            descr=name or cert_info['cn'] or file.filename,
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=base64.b64encode(key_pem).decode('utf-8') if key_pem else None,
            caref=caref,
            subject=cert_info['subject'],
            issuer=cert_info['issuer'],
            aki=cert_info.get('aki'),
            ski=cert_info.get('ski'),
            valid_from=cert_info['valid_from'],
            valid_to=cert_info['valid_to'],
            created_by='import'
        )
        
        db.session.add(certificate)
        db.session.commit()
        
        from services.audit_service import AuditService
        AuditService.log_action(
            action='certificate_imported',
            resource_type='certificate',
            resource_id=certificate.id,
            resource_name=certificate.descr,
            details=f'Imported certificate: {certificate.descr}',
            success=True
        )
        
        return created_response(
            data=certificate.to_dict(),
            message=f'Certificate "{certificate.descr}" imported successfully'
        )
        
    except ValueError as e:
        db.session.rollback()
        return error_response(str(e), 400)
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Certificate Import Error: {str(e)}")
        print(traceback.format_exc())
        return error_response(f'Import failed: {str(e)}', 500)


# ============================================================
# Bulk Operations
# ============================================================

@bp.route('/api/v2/certificates/bulk/revoke', methods=['POST'])
@require_auth(['write:certificates'])
def bulk_revoke_certificates():
    """Bulk revoke certificates"""
    from models import Certificate, db
    from services.cert_service import CertificateService
    from services.audit_service import AuditService

    data = request.get_json()
    if not data or not data.get('ids'):
        return error_response('ids array required', 400)

    ids = data['ids']
    reason = data.get('reason', 'unspecified')
    username = g.current_user.username if hasattr(g, 'current_user') else 'system'

    results = {'success': [], 'failed': []}
    for cert_id in ids:
        try:
            cert = Certificate.query.get(cert_id)
            if not cert:
                results['failed'].append({'id': cert_id, 'error': 'Not found'})
                continue
            if cert.revoked:
                results['failed'].append({'id': cert_id, 'error': 'Already revoked'})
                continue
            CertificateService.revoke_certificate(cert_id=cert_id, reason=reason, username=username)
            results['success'].append(cert_id)
        except Exception as e:
            results['failed'].append({'id': cert_id, 'error': str(e)})

    AuditService.log_action(
        action='certificates_bulk_revoked',
        resource_type='certificate',
        resource_id=','.join(str(i) for i in results['success']),
        resource_name=f'{len(results["success"])} certificates',
        details=f'Bulk revoked {len(results["success"])} certificates (reason: {reason})',
        success=True
    )

    return success_response(data=results, message=f'{len(results["success"])} certificates revoked')


@bp.route('/api/v2/certificates/bulk/renew', methods=['POST'])
@require_auth(['write:certificates'])
def bulk_renew_certificates():
    """Bulk renew certificates"""
    from models import Certificate, CA, db
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, ec
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509.oid import ExtensionOID
    from datetime import datetime, timedelta
    from services.audit_service import AuditService
    import base64

    data = request.get_json()
    if not data or not data.get('ids'):
        return error_response('ids array required', 400)

    ids = data['ids']
    results = {'success': [], 'failed': []}

    for cert_id in ids:
        try:
            cert = Certificate.query.get(cert_id)
            if not cert:
                results['failed'].append({'id': cert_id, 'error': 'Not found'})
                continue
            if not cert.crt:
                results['failed'].append({'id': cert_id, 'error': 'No certificate data'})
                continue

            ca = CA.query.filter_by(refid=cert.caref).first()
            if not ca or not ca.prv:
                results['failed'].append({'id': cert_id, 'error': 'Issuing CA not found or no private key'})
                continue

            orig_cert_pem = base64.b64decode(cert.crt)
            orig_cert = x509.load_pem_x509_certificate(orig_cert_pem, default_backend())
            ca_cert_pem = base64.b64decode(ca.crt)
            ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
            ca_key_pem = base64.b64decode(ca.prv)
            ca_key = serialization.load_pem_private_key(ca_key_pem, password=None, backend=default_backend())

            orig_pub_key = orig_cert.public_key()
            if isinstance(orig_pub_key, rsa.RSAPublicKey):
                new_key = rsa.generate_private_key(65537, orig_pub_key.key_size, default_backend())
            elif isinstance(orig_pub_key, ec.EllipticCurvePublicKey):
                new_key = ec.generate_private_key(orig_pub_key.curve, default_backend())
            else:
                new_key = rsa.generate_private_key(65537, 2048, default_backend())

            orig_duration = orig_cert.not_valid_after_utc - orig_cert.not_valid_before_utc
            validity_days = orig_duration.days if orig_duration.days > 0 else 365
            now = datetime.utcnow()

            builder = (x509.CertificateBuilder()
                .subject_name(orig_cert.subject)
                .issuer_name(ca_cert.subject)
                .public_key(new_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now)
                .not_valid_after(now + timedelta(days=validity_days)))

            for ext in orig_cert.extensions:
                if ext.oid in (ExtensionOID.AUTHORITY_KEY_IDENTIFIER, ExtensionOID.SUBJECT_KEY_IDENTIFIER):
                    continue
                try:
                    builder = builder.add_extension(ext.value, ext.critical)
                except Exception:
                    pass

            builder = builder.add_extension(x509.SubjectKeyIdentifier.from_public_key(new_key.public_key()), critical=False)
            try:
                builder = builder.add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            except Exception:
                pass

            new_cert = builder.sign(ca_key, hashes.SHA256(), default_backend())
            cert.crt = base64.b64encode(new_cert.public_bytes(serialization.Encoding.PEM)).decode()
            cert.prv = base64.b64encode(new_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption())).decode()
            cert.serial_number = format(new_cert.serial_number, 'x')
            cert.valid_from = now
            cert.valid_to = now + timedelta(days=validity_days)
            cert.revoked = False
            cert.revoked_at = None
            cert.revoke_reason = None
            db.session.commit()
            results['success'].append(cert_id)
        except Exception as e:
            db.session.rollback()
            results['failed'].append({'id': cert_id, 'error': str(e)})

    AuditService.log_action(
        action='certificates_bulk_renewed',
        resource_type='certificate',
        resource_id=','.join(str(i) for i in results['success']),
        resource_name=f'{len(results["success"])} certificates',
        details=f'Bulk renewed {len(results["success"])} certificates',
        success=True
    )

    return success_response(data=results, message=f'{len(results["success"])} certificates renewed')


@bp.route('/api/v2/certificates/bulk/delete', methods=['POST'])
@require_auth(['delete:certificates'])
def bulk_delete_certificates():
    """Bulk delete certificates"""
    from models import Certificate, db
    from services.audit_service import AuditService

    data = request.get_json()
    if not data or not data.get('ids'):
        return error_response('ids array required', 400)

    ids = data['ids']
    results = {'success': [], 'failed': []}

    for cert_id in ids:
        try:
            cert = Certificate.query.get(cert_id)
            if not cert:
                results['failed'].append({'id': cert_id, 'error': 'Not found'})
                continue
            db.session.delete(cert)
            db.session.commit()
            results['success'].append(cert_id)
        except Exception as e:
            db.session.rollback()
            results['failed'].append({'id': cert_id, 'error': str(e)})

    AuditService.log_action(
        action='certificates_bulk_deleted',
        resource_type='certificate',
        resource_id=','.join(str(i) for i in results['success']),
        resource_name=f'{len(results["success"])} certificates',
        details=f'Bulk deleted {len(results["success"])} certificates',
        success=True
    )

    return success_response(data=results, message=f'{len(results["success"])} certificates deleted')


@bp.route('/api/v2/certificates/bulk/export', methods=['POST'])
@require_auth(['read:certificates'])
def bulk_export_certificates():
    """Export selected certificates"""
    from flask import Response
    from models import Certificate
    import base64

    data = request.get_json()
    if not data or not data.get('ids'):
        return error_response('ids array required', 400)

    export_format = data.get('format', 'pem').lower()
    certs = Certificate.query.filter(Certificate.id.in_(data['ids']), Certificate.crt.isnot(None)).all()

    if not certs:
        return error_response('No certificates found', 404)

    try:
        if export_format == 'pem':
            pem_data = b''
            for cert in certs:
                pem_data += base64.b64decode(cert.crt)
                if not pem_data.endswith(b'\n'):
                    pem_data += b'\n'
            return Response(pem_data, mimetype='application/x-pem-file',
                headers={'Content-Disposition': 'attachment; filename="certificates.pem"'})
        elif export_format in ('pkcs7', 'p7b'):
            import subprocess, tempfile, os
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                for cert in certs:
                    f.write(base64.b64decode(cert.crt))
                    f.write(b'\n')
                pem_file = f.name
            try:
                p7b_output = subprocess.check_output(
                    ['openssl', 'crl2pkcs7', '-nocrl', '-certfile', pem_file, '-outform', 'DER'],
                    stderr=subprocess.DEVNULL)
                return Response(p7b_output, mimetype='application/x-pkcs7-certificates',
                    headers={'Content-Disposition': 'attachment; filename="certificates.p7b"'})
            finally:
                os.unlink(pem_file)
        else:
            return error_response('Supported formats: pem, p7b', 400)
    except Exception as e:
        return error_response(f'Export failed: {str(e)}', 500)
