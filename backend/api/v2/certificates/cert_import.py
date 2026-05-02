"""Certificate import route"""
import logging
import base64
import uuid
import json
import traceback
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response
from utils.file_validation import validate_upload, CERT_EXTENSIONS
from models import Certificate, CA, db
from services.audit_service import AuditService
from services.import_service import (
    parse_certificate_file, is_ca_certificate, extract_cert_info,
    find_existing_ca, find_existing_certificate,
    serialize_cert_to_pem, serialize_key_to_pem
)
from . import bp

logger = logging.getLogger(__name__)


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

    # Get file data from either file upload or pasted PEM content
    file_data = None
    filename = 'pasted.pem'

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        try:
            file_data, filename = validate_upload(file, CERT_EXTENSIONS)
        except ValueError as e:
            logger.error(f"Certificate upload validation error: {e}")
            return error_response('Invalid input', 400)
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
            if cert_info.get('san_dns'):
                existing_cert.san_dns = json.dumps(cert_info['san_dns'])
            if cert_info.get('san_ip'):
                existing_cert.san_ip = json.dumps(cert_info['san_ip'])
            if cert_info.get('san_email'):
                existing_cert.san_email = json.dumps(cert_info['san_email'])
            if cert_info.get('san_uri'):
                existing_cert.san_uri = json.dumps(cert_info['san_uri'])

            # Update CA link if provided
            if ca_id:
                ca = CA.query.get(ca_id)
                if ca:
                    existing_cert.caref = ca.refid

            db.session.commit()
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
            san_dns=json.dumps(cert_info.get('san_dns', [])) if cert_info.get('san_dns') else None,
            san_ip=json.dumps(cert_info.get('san_ip', [])) if cert_info.get('san_ip') else None,
            san_email=json.dumps(cert_info.get('san_email', [])) if cert_info.get('san_email') else None,
            san_uri=json.dumps(cert_info.get('san_uri', [])) if cert_info.get('san_uri') else None,
            source='import',
            created_by='import'
        )

        db.session.add(certificate)
        db.session.commit()
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
        logger.error(f"Certificate import validation error: {e}")
        return error_response('Invalid input', 400)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Certificate Import Error: {e}")
        logger.error(traceback.format_exc())
        return error_response('Import failed', 500)
