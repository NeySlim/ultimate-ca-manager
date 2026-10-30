"""
CAs Import Operations
"""

from . import bp
from flask import request, g
import base64
import logging
from cryptography.hazmat.primitives.asymmetric import ed25519, ed448
import traceback
import uuid

from auth.unified import require_auth
from fips_mode import FipsRestricted
from utils.db_transaction import safe_commit
from utils.key_codec import MalformedKey
from utils.response import success_response, error_response, created_response
from utils.file_validation import validate_upload, CERT_EXTENSIONS
from utils.cert_issuer import private_key_matches
from services.import_service import (
    parse_certificate_file, extract_cert_info, find_existing_ca_for_import, cross_mode_from, finish_cross_attach, AmbiguousImportTarget, CrossCertificateImport, ImportConflict, update_ca_from_import,
    install_on_pending_ca, find_pending_csr_for_certificate,
    serialize_cert_to_pem, serialize_key_to_pem
)
from security.encryption import encrypt_private_key
from services.audit_service import AuditService
from services.ca_service import CAService
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
    cross_mode = cross_mode_from(request.form.get('cross_mode'))
    if cross_mode is None:
        return error_response('cross_mode must be auto, attach, replace or refuse', 400)

    try:
        # Parse certificate using shared service
        cert, private_key, format_detected = parse_certificate_file(
            file_data, filename, password, import_key
        )

        # A key that is not this certificate's must not be stored next to it:
        # it would sign nothing anyone can verify (#347 review)
        if private_key is not None and not private_key_matches(private_key, cert):
            return error_response('Private key does not match the certificate', 400)
        if isinstance(private_key, (ed25519.Ed25519PrivateKey, ed448.Ed448PrivateKey)):
            # The CA's signing paths (certificates, CRLs) hand these keys a
            # digest they refuse: refused here with the reason, not later with 500
            return error_response('Ed25519 and Ed448 CA keys are not supported: '
                                  'such a CA could sign neither certificates nor CRLs', 400)

        # Extract certificate info
        cert_info = extract_cert_info(cert)

        # Serialize to PEM
        cert_pem = serialize_cert_to_pem(cert)
        key_pem = serialize_key_to_pem(private_key) if import_key else None
        # Encrypt private key at rest (matches CA creation code path).
        encrypted_prv = (
            encrypt_private_key(base64.b64encode(key_pem).decode('utf-8'))
            if key_pem else None
        )

        # Check for existing CA with same subject
        username = getattr(getattr(g, 'current_user', None), 'username', None) or 'system'
        try:
            existing_ca, attached = find_existing_ca_for_import(cert_info, cert, cross_mode, username)
        except AmbiguousImportTarget as e:
            return error_response(str(e), 409, e.details)
        except ImportConflict as e:
            db.session.rollback()
            return error_response(str(e), 409)
        if attached:
            data = finish_cross_attach(existing_ca, attached, username)
            return created_response(data=data, message=f'Cross-certificate attached to CA "{existing_ca.descr}"')

        if existing_ca:
            if not update_existing:
                return error_response(
                    f'CA with subject "{cert_info["cn"]}" already exists (ID: {existing_ca.id})',
                    409
                )

            if existing_ca.is_pending or existing_ca.csr:
                # A CA still waiting for its certificate, or holding a renewal
                # request, is completed the way the dedicated upload completes
                # it (key match, chain, request fulfilled), not patched in place
                username = getattr(getattr(g, 'current_user', None), 'username', None) or 'system'
                try:
                    ca_dict, warnings, superseded = install_on_pending_ca(
                        existing_ca, cert_pem, username, encrypted_prv=encrypted_prv, name=name or None,
                        replace_cross=cross_mode == 'replace')
                except CrossCertificateImport as e:
                    db.session.rollback()
                    return error_response(str(e), 409, e.details)
                except ValueError as e:
                    db.session.rollback()
                    return error_response(str(e), 400)
                message = f'CA "{ca_dict["descr"]}" certificate installed'
                if warnings:
                    message += '; ' + '; '.join(warnings)
                data = {**ca_dict, 'warnings': warnings}
                if superseded:
                    data['superseded_serial'] = superseded['serial']
                    data['superseded_valid_to'] = superseded['valid_to']
                return success_response(data=data, message=message)

            try:
                key_dropped = update_ca_from_import(
                    existing_ca, cert, cert_pem, cert_info,
                    key_pem=key_pem, encrypted_prv=encrypted_prv, name=name)
            except ImportConflict as e:
                db.session.rollback()
                return error_response(str(e), 409)

            ok, err = safe_commit(logger, "Failed to update CA")
            if not ok:
                return err
            AuditService.log_action(
                action='ca_updated',
                resource_type='ca',
                resource_id=existing_ca.id,
                resource_name=existing_ca.descr,
                details=f'Updated CA via import: {existing_ca.descr}',
                success=True
            )

            message = f'CA "{existing_ca.descr}" updated (already existed)'
            if key_dropped:
                message += '; the stored key did not match the new certificate and was unbound'
            return success_response(data=existing_ca.to_dict(), message=message)

        # Create new CA record
        refid = str(uuid.uuid4())
        # A CA certificate issued elsewhere for a request pending in the
        # certificates table (an intermediate requested here, signed outside):
        # the request's key becomes the CA's and the request is fulfilled
        pending_request = find_pending_csr_for_certificate(cert)
        if pending_request is not None and not encrypted_prv:
            encrypted_prv = pending_request.prv
        ca = CA(
            refid=refid,
            descr=name or cert_info['cn'] or filename,
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=encrypted_prv,
            serial=0,
            subject=cert_info['subject'],
            issuer=cert_info['issuer'],
            ski=cert_info.get('ski'),
            serial_number=str(cert.serial_number),
            valid_from=cert_info['valid_from'],
            valid_to=cert_info['valid_to'],
            imported_from='manual'
        )
        # Deleted after its revocation and imported again: still revoked (#343)
        CAService.apply_persisted_revocation(ca)

        fulfilled = None
        if pending_request is not None:
            fulfilled = pending_request.descr or f'request {pending_request.id}'
            db.session.delete(pending_request)
        db.session.add(ca)
        ok, err = safe_commit(logger, "Failed to import CA")
        if not ok:
            return err
        AuditService.log_action(
            action='ca_imported',
            resource_type='ca',
            resource_id=ca.id,
            resource_name=ca.descr,
            details=f'Imported CA: {ca.descr}',
            success=True
        )

        # Single lifecycle event — bus fans out to webhook + email + WebSocket.
        # Snapshot before emit: subscribers may commit and expire the instance.
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'
        ca_dict = ca.to_dict()
        ca_descr = ca.descr
        from services.webhook_service import emit_ca_created
        emit_ca_created(ca_dict, actor=username)

        message = f'CA "{ca_descr}" imported successfully'
        if fulfilled:
            message += f'; pending request "{fulfilled}" fulfilled, its key is now the CA\'s'
        return created_response(data=ca_dict, message=message)

    except FipsRestricted:
        db.session.rollback()
        raise  # the app handler answers 400 with the FIPS problem type
    except MalformedKey as e:
        db.session.rollback()
        return error_response(str(e), 400)
    except ValueError as e:
        db.session.rollback()
        logger.warning(f"CA import validation error: {e}")
        return error_response('Invalid CA data', 400)
    except Exception as e:
        db.session.rollback()
        logger.error(f"CA Import Error: {e}")
        logger.error(traceback.format_exc())
        return error_response('Import failed', 500)
