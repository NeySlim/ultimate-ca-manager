"""
CAs Import Operations
"""

from . import bp
from flask import request, g
import base64
import logging
import traceback
import uuid

from auth.unified import require_auth
from utils.response import success_response, error_response, created_response
from utils.file_validation import validate_upload, CERT_EXTENSIONS
from services.import_service import (
    parse_certificate_file, extract_cert_info, find_existing_ca,
    serialize_cert_to_pem, serialize_key_to_pem
)
from services.audit_service import AuditService
from services.notification_service import NotificationService
from models import CA, db

logger = logging.getLogger(__name__)


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
