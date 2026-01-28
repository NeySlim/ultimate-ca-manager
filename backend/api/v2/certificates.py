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
        details=f'Deleted certificate: {cert_name}',
        success=True
    )
    
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
        
        # Create new certificate record
        new_refid = str(uuid.uuid4())[:8]
        new_db_cert = Certificate(
            refid=new_refid,
            descr=cert.descr + ' (renewed)',
            caref=cert.caref,
            crt=base64.b64encode(new_cert_pem.encode()).decode(),
            prv=base64.b64encode(new_key_pem.encode()).decode(),
            serial_number=format(new_cert.serial_number, 'x'),
            subject=cert.subject,
            issuer=cert.issuer,
            valid_from=not_before,
            valid_to=not_after,
            key_type=cert.key_type,
            key_size=cert.key_size,
            revoked=False
        )
        
        db.session.add(new_db_cert)
        db.session.commit()
        
        # Audit log
        try:
            AuditService.log(
                action='certificate_renewed',
                user_id=g.current_user.id if hasattr(g, 'current_user') else None,
                details={
                    'original_id': cert_id,
                    'new_id': new_db_cert.id,
                    'subject': cert.subject,
                    'valid_until': not_after.isoformat()
                }
            )
        except Exception:
            pass
        
        return created_response(
            data=new_db_cert.to_dict(),
            message=f'Certificate renewed successfully. New certificate ID: {new_db_cert.id}'
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
            # Auto-link by matching issuer with CA subject
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
            details=f'Imported certificate: {certificate.descr}',
            success=True
        )
        
        return created_response(
            data=certificate.to_dict(),
            message=f'Certificate "{certificate.descr}" imported successfully'
        )
        
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        import traceback
        print(f"Certificate Import Error: {str(e)}")
        print(traceback.format_exc())
        return error_response(f'Import failed: {str(e)}', 500)
