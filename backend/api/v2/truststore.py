"""
TrustStore Management Routes v2.0
/api/v2/truststore/* - Manage trusted certificates
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from models import db
from models.truststore import TrustedCertificate
from services.audit_service import AuditService
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
import hashlib
from datetime import datetime
import base64
import os

bp = Blueprint('truststore_v2', __name__)


def parse_certificate(pem_data):
    """
    Parse certificate and extract details
    
    Returns dict with subject, issuer, fingerprints, etc.
    """
    try:
        cert = x509.load_pem_x509_certificate(pem_data.encode(), default_backend())
        
        # Extract subject and issuer
        subject = cert.subject.rfc4514_string()
        issuer = cert.issuer.rfc4514_string()
        
        # Calculate fingerprints
        cert_der = cert.public_bytes(serialization.Encoding.DER)
        fp_sha256 = hashlib.sha256(cert_der).hexdigest()
        fp_sha1 = hashlib.sha1(cert_der).hexdigest()
        
        return {
            'subject': subject,
            'issuer': issuer,
            'serial_number': format(cert.serial_number, 'X'),
            'not_before': cert.not_valid_before_utc,
            'not_after': cert.not_valid_after_utc,
            'fingerprint_sha256': fp_sha256,
            'fingerprint_sha1': fp_sha1,
        }
    except Exception as e:
        raise ValueError(f'Invalid certificate: {str(e)}')


def parse_der_certificate(der_data):
    """Parse DER-encoded certificate"""
    try:
        cert = x509.load_der_x509_certificate(der_data, default_backend())
        pem_data = cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
        return pem_data, parse_certificate(pem_data)
    except Exception as e:
        raise ValueError(f'Invalid DER certificate: {str(e)}')


@bp.route('/api/v2/truststore/stats', methods=['GET'])
@require_auth(['read:truststore'])
def get_truststore_stats():
    """Get trust store statistics"""
    now = datetime.utcnow()
    
    total = TrustedCertificate.query.count()
    root_cas = TrustedCertificate.query.filter_by(purpose='root_ca').count()
    intermediate_cas = TrustedCertificate.query.filter_by(purpose='intermediate_ca').count()
    expired = TrustedCertificate.query.filter(TrustedCertificate.not_after <= now).count()
    
    return success_response(data={
        'total': total,
        'root_ca': root_cas,
        'intermediate_ca': intermediate_cas,
        'expired': expired,
        'valid': total - expired
    })


@bp.route('/api/v2/truststore/import', methods=['POST'])
@require_auth(['write:truststore'])
def import_trusted_certificate():
    """
    Import certificate via file upload
    
    Supports PEM and DER formats
    """
    if 'file' not in request.files:
        return error_response('No file provided', 400)
    
    file = request.files['file']
    if not file.filename:
        return error_response('No file selected', 400)
    
    from utils.file_validation import validate_upload, CERT_EXTENSIONS
    try:
        file_content, safe_filename = validate_upload(file, CERT_EXTENSIONS)
    except ValueError as e:
        return error_response(str(e), 400)
    
    name = request.form.get('name', safe_filename.rsplit('.', 1)[0])
    purpose = request.form.get('purpose', 'custom')
    description = request.form.get('description', '')
    notes = request.form.get('notes', '')
    
    try:
        # Try PEM first
        if b'-----BEGIN CERTIFICATE-----' in file_content:
            pem_data = file_content.decode('utf-8')
            cert_details = parse_certificate(pem_data)
        else:
            # Try DER
            pem_data, cert_details = parse_der_certificate(file_content)
        
        # Check if already exists
        existing = TrustedCertificate.query.filter_by(
            fingerprint_sha256=cert_details['fingerprint_sha256']
        ).first()
        
        if existing:
            return error_response(f'Certificate already in trust store as "{existing.name}"', 409)
        
        # Create trusted certificate
        trusted_cert = TrustedCertificate(
            name=name,
            description=description,
            certificate_pem=pem_data,
            fingerprint_sha256=cert_details['fingerprint_sha256'],
            fingerprint_sha1=cert_details['fingerprint_sha1'],
            subject=cert_details['subject'],
            issuer=cert_details['issuer'],
            serial_number=cert_details['serial_number'],
            not_before=cert_details['not_before'],
            not_after=cert_details['not_after'],
            purpose=purpose,
            added_by=g.current_user.username,
            notes=notes
        )
        
        db.session.add(trusted_cert)
        db.session.commit()
        
        from services.audit_service import AuditService
        AuditService.log_action(
            action='truststore_import',
            resource_type='truststore',
            resource_id=trusted_cert.id,
            resource_name=trusted_cert.name,
            details=f'Imported certificate: {trusted_cert.name}',
            success=True
        )
        
        return created_response(
            data=trusted_cert.to_dict(),
            message=f'Certificate "{name}" imported to trust store'
        )
        
    except ValueError as e:
        db.session.rollback()
        return error_response(str(e), 400)
    except Exception as e:
        db.session.rollback()
        return error_response(f'Import failed: {str(e)}', 500)


@bp.route('/api/v2/truststore', methods=['GET'])
@require_auth(['read:truststore'])
def list_trusted_certificates():
    """
    List all trusted certificates
    
    Query params:
    - purpose: Filter by purpose
    - search: Search name, subject, fingerprint
    """
    purpose = request.args.get('purpose')
    search = request.args.get('search', '').strip()
    
    query = TrustedCertificate.query
    
    if purpose:
        query = query.filter_by(purpose=purpose)
    
    if search:
        search_pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                TrustedCertificate.name.ilike(search_pattern),
                TrustedCertificate.subject.ilike(search_pattern),
                TrustedCertificate.fingerprint_sha256.ilike(search_pattern)
            )
        )
    
    certs = query.order_by(TrustedCertificate.added_at.desc()).all()
    
    return success_response(
        data=[cert.to_dict() for cert in certs]
    )


@bp.route('/api/v2/truststore', methods=['POST'])
@require_auth(['read:truststore'])
def add_trusted_certificate():
    """
    Add certificate to trust store
    
    POST /api/v2/truststore
    {
        "name": "DigiCert Global Root CA",
        "description": "DigiCert public root CA",
        "certificate_pem": "-----BEGIN CERTIFICATE-----...",
        "purpose": "root_ca",
        "notes": "Trusted for code signing"
    }
    """
    data = request.get_json()
    
    # Required fields
    if not data.get('name'):
        return error_response('Name is required', 400)
    if not data.get('certificate_pem'):
        return error_response('Certificate PEM is required', 400)
    
    # Parse certificate
    try:
        cert_details = parse_certificate(data['certificate_pem'])
    except ValueError as e:
        return error_response(str(e), 400)
    
    # Check if already exists (by fingerprint)
    existing = TrustedCertificate.query.filter_by(
        fingerprint_sha256=cert_details['fingerprint_sha256']
    ).first()
    
    if existing:
        return error_response('Certificate already in trust store', 409)
    
    # Create trusted certificate
    trusted_cert = TrustedCertificate(
        name=data['name'],
        description=data.get('description', ''),
        certificate_pem=data['certificate_pem'],
        fingerprint_sha256=cert_details['fingerprint_sha256'],
        fingerprint_sha1=cert_details['fingerprint_sha1'],
        subject=cert_details['subject'],
        issuer=cert_details['issuer'],
        serial_number=cert_details['serial_number'],
        not_before=cert_details['not_before'],
        not_after=cert_details['not_after'],
        purpose=data.get('purpose', 'custom'),
        added_by=g.current_user.username,
        notes=data.get('notes', '')
    )
    
    try:
        db.session.add(trusted_cert)
        db.session.commit()
        
        AuditService.log_action(
            action='truststore_add',
            resource_type='truststore',
            resource_id=str(trusted_cert.id),
            resource_name=trusted_cert.name,
            details=f'Added certificate to trust store: {trusted_cert.name}',
            success=True
        )
        
        return created_response(
            data=trusted_cert.to_dict(),
            message=f'Certificate {trusted_cert.name} added to trust store'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to add certificate: {str(e)}', 500)


@bp.route('/api/v2/truststore/<int:cert_id>', methods=['GET'])
@require_auth(['read:truststore'])
def get_trusted_certificate(cert_id):
    """Get single trusted certificate details"""
    cert = TrustedCertificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    
    return success_response(data=cert.to_dict())


@bp.route('/api/v2/truststore/<int:cert_id>', methods=['DELETE'])
@require_auth(['read:truststore'])
def remove_trusted_certificate(cert_id):
    """
    Remove certificate from trust store
    
    DELETE /api/v2/truststore/{cert_id}
    """
    cert = TrustedCertificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    
    cert_name = cert.name
    
    try:
        db.session.delete(cert)
        db.session.commit()
        
        AuditService.log_action(
            action='truststore_remove',
            resource_type='truststore',
            resource_id=str(cert_id),
            resource_name=cert_name,
            details=f'Removed certificate from trust store: {cert_name}',
            success=True
        )
        
        return success_response(message=f'Certificate {cert_name} removed from trust store')
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to remove certificate: {str(e)}', 500)


@bp.route('/api/v2/truststore/sync', methods=['POST'])
@require_auth(['write:truststore'])
def sync_trust_store():
    """
    Synchronize trust store with system CA bundle
    
    POST /api/v2/truststore/sync
    {
        "source": "system",  # "system" reads from /etc/ssl/certs
        "limit": 50          # Optional: limit number of certs to import
    }
    """
    data = request.get_json() or {}
    source = data.get('source', 'system')
    limit = data.get('limit', 50)
    
    CA_BUNDLE_PATH = '/etc/ssl/certs/ca-certificates.crt'
    
    if source != 'system':
        return error_response('Only "system" source is currently supported', 400)
    
    if not os.path.exists(CA_BUNDLE_PATH):
        return error_response(f'System CA bundle not found at {CA_BUNDLE_PATH}', 404)
    
    try:
        # Read and parse CA bundle
        with open(CA_BUNDLE_PATH, 'r') as f:
            bundle_content = f.read()
        
        # Split into individual certificates
        certs_pem = []
        current_cert = []
        in_cert = False
        
        for line in bundle_content.split('\n'):
            if '-----BEGIN CERTIFICATE-----' in line:
                in_cert = True
                current_cert = [line]
            elif '-----END CERTIFICATE-----' in line:
                current_cert.append(line)
                certs_pem.append('\n'.join(current_cert))
                in_cert = False
                current_cert = []
            elif in_cert:
                current_cert.append(line)
        
        new_count = 0
        skipped_count = 0
        error_count = 0
        
        for pem in certs_pem[:limit]:
            try:
                cert_details = parse_certificate(pem)
                
                # Check if already exists
                existing = TrustedCertificate.query.filter_by(
                    fingerprint_sha256=cert_details['fingerprint_sha256']
                ).first()
                
                if existing:
                    skipped_count += 1
                    continue
                
                # Extract CN for name
                subject = cert_details['subject']
                cn = None
                for part in subject.split(','):
                    if part.strip().startswith('CN='):
                        cn = part.strip()[3:]
                        break
                
                name = cn or f"System CA {cert_details['fingerprint_sha256'][:8]}"
                
                trusted_cert = TrustedCertificate(
                    name=name,
                    description='Imported from system CA bundle',
                    certificate_pem=pem,
                    fingerprint_sha256=cert_details['fingerprint_sha256'],
                    fingerprint_sha1=cert_details['fingerprint_sha1'],
                    subject=cert_details['subject'],
                    issuer=cert_details['issuer'],
                    serial_number=cert_details['serial_number'],
                    not_before=cert_details['not_before'],
                    not_after=cert_details['not_after'],
                    purpose='system',
                    added_by='system_sync',
                    notes='Auto-imported from /etc/ssl/certs/ca-certificates.crt'
                )
                
                db.session.add(trusted_cert)
                new_count += 1
                
            except Exception as e:
                error_count += 1
                continue
        
        db.session.commit()
        
        from services.audit_service import AuditService
        AuditService.log_action(
            action='truststore_sync',
            resource_type='truststore',
            resource_name='System CA Bundle',
            details=f'Synced {new_count} new certificates from system',
            success=True
        )
        
        return success_response(
            message=f'Trust store synchronized: {new_count} new, {skipped_count} already exist',
            data={
                'source': source,
                'total_found': len(certs_pem),
                'new_count': new_count,
                'skipped_count': skipped_count,
                'error_count': error_count
            }
        )
        
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to sync trust store: {str(e)}', 500)


@bp.route('/api/v2/truststore/export', methods=['GET'])
@require_auth(['read:truststore'])
def export_trust_bundle():
    """
    Export trust store as a certificate bundle.
    
    GET /api/v2/truststore/export?format=pem&purpose=root_ca
    
    Query params:
      - format: pem (default), p7b
      - purpose: root_ca, intermediate_ca, system, all (default)
    """
    from flask import Response
    
    fmt = request.args.get('format', 'pem')
    purpose = request.args.get('purpose', 'all')
    
    if fmt not in ('pem', 'p7b'):
        return error_response('Unsupported format. Use: pem, p7b', 400)
    
    try:
        query = TrustedCertificate.query
        if purpose != 'all':
            query = query.filter_by(purpose=purpose)
        
        certs = query.order_by(TrustedCertificate.name).all()
        
        if not certs:
            return error_response('No certificates found matching criteria', 404)
        
        if fmt == 'pem':
            bundle_lines = []
            for cert in certs:
                bundle_lines.append(f'# {cert.name}')
                bundle_lines.append(cert.certificate_pem.strip())
                bundle_lines.append('')
            
            bundle = '\n'.join(bundle_lines)
            filename = f'truststore-{purpose}-bundle.pem'
            
            return Response(
                bundle,
                mimetype='application/x-pem-file',
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )
        
        elif fmt == 'p7b':
            from cryptography.hazmat.primitives.serialization import pkcs7
            
            x509_certs = []
            for cert in certs:
                try:
                    x509_cert = x509.load_pem_x509_certificate(
                        cert.certificate_pem.encode(), default_backend()
                    )
                    x509_certs.append(x509_cert)
                except Exception:
                    continue
            
            if not x509_certs:
                return error_response('No valid certificates to export', 400)
            
            p7b_data = pkcs7.serialize_certificates(x509_certs, serialization.Encoding.DER)
            
            filename = f'truststore-{purpose}-bundle.p7b'
            return Response(
                p7b_data,
                mimetype='application/x-pkcs7-certificates',
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )
    
    except Exception as e:
        return error_response(f'Failed to export bundle: {str(e)}', 500)


@bp.route('/api/v2/truststore/expiring', methods=['GET'])
@require_auth(['read:truststore'])
def get_expiring_trusted_certs():
    """
    Get trusted certificates expiring within N days.
    
    GET /api/v2/truststore/expiring?days=90
    """
    from sqlalchemy import and_
    
    days = request.args.get('days', 90, type=int)
    
    try:
        now = datetime.utcnow()
        from datetime import timedelta
        threshold = now + timedelta(days=days)
        
        # Expiring soon (valid but within threshold)
        expiring = TrustedCertificate.query.filter(
            and_(
                TrustedCertificate.not_after != None,
                TrustedCertificate.not_after > now,
                TrustedCertificate.not_after <= threshold
            )
        ).order_by(TrustedCertificate.not_after.asc()).all()
        
        # Already expired
        expired = TrustedCertificate.query.filter(
            and_(
                TrustedCertificate.not_after != None,
                TrustedCertificate.not_after <= now
            )
        ).order_by(TrustedCertificate.not_after.desc()).all()
        
        def cert_to_dict(c):
            days_left = (c.not_after - now).days if c.not_after else None
            return {
                'id': c.id,
                'name': c.name,
                'subject': c.subject,
                'purpose': c.purpose,
                'not_after': c.not_after.isoformat() if c.not_after else None,
                'days_remaining': days_left,
                'fingerprint_sha256': c.fingerprint_sha256,
            }
        
        return success_response(data={
            'expiring': [cert_to_dict(c) for c in expiring],
            'expired': [cert_to_dict(c) for c in expired],
            'expiring_count': len(expiring),
            'expired_count': len(expired),
            'threshold_days': days,
        })
    
    except Exception as e:
        return error_response(f'Failed to get expiring certificates: {str(e)}', 500)


@bp.route('/api/v2/truststore/add-from-ca/<string:ca_refid>', methods=['POST'])
@require_auth(['write:truststore'])
def add_ca_to_truststore(ca_refid):
    """
    Add a managed CA's certificate to the Trust Store.
    
    POST /api/v2/truststore/add-from-ca/<ca_refid>
    Body (optional): { "purpose": "root_ca", "notes": "..." }
    """
    from models import CA
    
    ca = CA.query.filter_by(refid=ca_refid).first()
    if not ca:
        return error_response('CA not found', 404)
    
    try:
        pem_data = base64.b64decode(ca.crt).decode('utf-8')
    except Exception:
        return error_response('Failed to decode CA certificate', 500)
    
    # Check if already in Trust Store
    cert_info = parse_certificate(pem_data)
    if not cert_info:
        return error_response('Failed to parse CA certificate', 500)
    
    existing = TrustedCertificate.query.filter_by(
        fingerprint_sha256=cert_info['fingerprint_sha256']
    ).first()
    if existing:
        return error_response('This CA is already in the Trust Store', 409)
    
    body = request.get_json(silent=True) or {}
    purpose = body.get('purpose', 'root_ca' if ca.is_root else 'intermediate_ca')
    
    trusted = TrustedCertificate(
        name=ca.common_name or ca.descr or cert_info['subject'],
        certificate_pem=pem_data,
        subject=cert_info['subject'],
        issuer=cert_info['issuer'],
        serial_number=cert_info['serial_number'],
        not_before=cert_info['not_before'],
        not_after=cert_info['not_after'],
        fingerprint_sha256=cert_info['fingerprint_sha256'],
        fingerprint_sha1=cert_info['fingerprint_sha1'],
        purpose=purpose,
        added_by=g.current_user.username,
        notes=body.get('notes', f'Added from managed CA: {ca.descr or ca.common_name}'),
    )
    
    db.session.add(trusted)
    db.session.commit()
    
    AuditService.log_action(
        action='truststore.add_from_ca',
        resource_type='truststore',
        resource_id=str(trusted.id),
        resource_name=trusted.name,
        details=f'Added managed CA "{ca.common_name or ca.descr}" to Trust Store'
    )
    
    return created_response(data={
        'id': trusted.id,
        'name': trusted.name,
        'fingerprint_sha256': trusted.fingerprint_sha256,
        'purpose': trusted.purpose,
    }, message=f'CA "{trusted.name}" added to Trust Store')
