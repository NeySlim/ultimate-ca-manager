"""Certificate import route"""
import logging
import base64
import uuid
import json
import traceback
from flask import request, g
from auth.unified import require_auth
from utils.db_transaction import safe_commit
from utils.response import success_response, error_response, created_response
from utils.file_validation import validate_upload, CERT_EXTENSIONS
from models import Certificate, CA, db
from services.audit_service import AuditService
from utils.cert_issuer import private_key_matches, stored_private_key_matches, hsm_key_binding_matches
from services.import_service import (
    parse_certificate_file, is_ca_certificate, extract_cert_info,
    find_existing_ca, find_existing_certificate, find_pending_csr_for_certificate,
    AmbiguousImportTarget, install_on_pending_ca,
    serialize_cert_to_pem, serialize_key_to_pem
)
from services.cert_service import CertificateService
from services.ca_service import CAService
try:
    from security.encryption import encrypt_private_key
    HAS_ENCRYPTION = True
except ImportError:
    HAS_ENCRYPTION = False
    def encrypt_private_key(data):
        return data
from . import bp

logger = logging.getLogger(__name__)


def _resolve_caref(ca_id, cert_info):
    """The issuing CA's refid: the one the caller named, else the CA whose
    SKI is the certificate's AKI (cryptographically reliable), else the CA
    whose subject is the issuer DN; None when UCM does not hold the issuer."""
    if ca_id:
        ca = db.session.get(CA, ca_id)
        return ca.refid if ca else None
    aki = cert_info.get('aki')
    if aki:
        ca = CA.query.filter_by(ski=aki).first()
        if ca:
            return ca.refid
    ca = CA.query.filter_by(subject=cert_info['issuer']).first()
    return ca.refid if ca else None


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

        # A key that is not this certificate's must not be stored next to it:
        # it would sign nothing anyone can verify (#347 review)
        if private_key is not None and not private_key_matches(private_key, cert):
            return error_response('Private key does not match the certificate', 400)

        # Extract certificate info
        cert_info = extract_cert_info(cert)

        # Serialize to PEM
        cert_pem = serialize_cert_to_pem(cert)
        key_pem = serialize_key_to_pem(private_key) if import_key else None
        # Encrypt private key at rest (matches creation/CSR-sign code paths).
        # encrypt_private_key is a no-op if encryption is disabled or fails.
        encrypted_prv = (
            encrypt_private_key(base64.b64encode(key_pem).decode('utf-8'))
            if key_pem else None
        )

        # Check if this is a CA certificate - auto-route to CA table
        if is_ca_certificate(cert):
            # Check for existing CA
            try:
                existing_ca = find_existing_ca(cert_info, cert)
            except AmbiguousImportTarget as e:
                return error_response(str(e), 409)

            if existing_ca:
                if not update_existing:
                    return error_response(
                        f'CA with subject "{cert_info["cn"]}" already exists (ID: {existing_ca.id})',
                        409
                    )

                if existing_ca.is_pending:
                    # A CA still waiting for its certificate is completed the way
                    # the dedicated upload completes it, not patched in place
                    username = getattr(getattr(g, 'current_user', None), 'username', None) or 'system'
                    try:
                        ca_dict, warnings = install_on_pending_ca(existing_ca, cert_pem, username)
                    except ValueError as e:
                        db.session.rollback()
                        return error_response(str(e), 400)
                    message = f'CA "{ca_dict["descr"]}" certificate installed'
                    if warnings:
                        message += '; ' + '; '.join(warnings)
                    return success_response(data={**ca_dict, 'warnings': warnings}, message=message)

                # Decide what becomes of the stored key before touching the record:
                # the HSM lookup may commit its public key cache, and a record already
                # half-updated would be persisted with the old binding (#347 review)
                key_dropped = False
                if key_pem:
                    # The new certificate's key arrived with it: it replaces whatever
                    # the record held, an HSM binding included
                    pass
                elif existing_ca.hsm_key_id:
                    # An HSM-backed CA holds no key column: the binding is checked
                    # against the HSM key's public key, and left untouched when that
                    # key cannot be reached rather than kept or dropped on a guess
                    bound = hsm_key_binding_matches(existing_ca.hsm_key_id, cert)
                    if bound is None:
                        db.session.rollback()
                        return error_response(
                            'Cannot verify the HSM key bound to this CA against the new '
                            'certificate; the HSM key is unreachable', 409)
                    key_dropped = bound is False
                elif existing_ca.prv:
                    # The new certificate is not the stored key's: keeping the key
                    # would leave a pair that signs nothing verifiable (re-keyed
                    # certificate imported without its key). A key that cannot be
                    # read is not shown to be foreign: the update is refused
                    matches = stored_private_key_matches(existing_ca.prv, cert, context=f"CA {existing_ca.id}")
                    if matches is None:
                        db.session.rollback()
                        return error_response(
                            'Cannot verify the stored private key against the new '
                            'certificate; the stored key could not be read', 409)
                    key_dropped = matches is False

                # Update existing CA
                existing_ca.descr = name or cert_info['cn'] or existing_ca.descr
                existing_ca.crt = base64.b64encode(cert_pem).decode('utf-8')
                if key_pem:
                    existing_ca.prv = encrypted_prv
                    existing_ca.hsm_key_id = None
                elif key_dropped:
                    existing_ca.prv = None
                    existing_ca.hsm_key_id = None
                existing_ca.issuer = cert_info['issuer']
                existing_ca.valid_from = cert_info['valid_from']
                existing_ca.valid_to = cert_info['valid_to']
                existing_ca.ski = cert_info.get('ski')
                CAService.apply_persisted_revocation(existing_ca)

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

                message = f'CA certificate "{existing_ca.descr}" updated (already existed)'
                if key_dropped:
                    message += '; the stored key did not match the new certificate and was unbound'
                return success_response(data=existing_ca.to_dict(), message=message)

            # Create new CA
            refid = str(uuid.uuid4())
            ca = CA(
                refid=refid,
                descr=name or cert_info['cn'] or filename,
                crt=base64.b64encode(cert_pem).decode('utf-8'),
                prv=encrypted_prv,
                serial=0,
                subject=cert_info['subject'],
                issuer=cert_info['issuer'],
                ski=cert_info.get('ski'),
                valid_from=cert_info['valid_from'],
                valid_to=cert_info['valid_to'],
                imported_from='manual'
            )
            # Deleted after its revocation and imported again: still revoked (#343)
            CAService.apply_persisted_revocation(ca)

            db.session.add(ca)
            ok, err = safe_commit(logger, "Failed to import CA")
            if not ok:
                return err
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

        # A certificate issued elsewhere for a CSR pending here completes
        # that record instead of creating a keyless duplicate (#341)
        pending_csr = find_pending_csr_for_certificate(cert)
        if pending_csr:
            username = getattr(getattr(g, 'current_user', None), 'username', None) or 'import'
            try:
                CertificateService.complete_external_csr(
                    pending_csr, cert, cert_pem,
                    caref=_resolve_caref(ca_id, cert_info),
                    descr=name or None,
                    key_pem=key_pem,
                    username=username,
                )
            except ValueError as e:
                db.session.rollback()
                return error_response(str(e), 400)
            return success_response(
                data=pending_csr.to_dict(),
                message=(
                    f'Certificate "{pending_csr.descr}" imported and attached to its '
                    f'pending CSR' + (' (private key kept)' if pending_csr.prv else '')
                )
            )

        # Check for existing certificate
        try:
            existing_cert = find_existing_certificate(cert_info, cert)
        except AmbiguousImportTarget as e:
            return error_response(str(e), 409)

        if existing_cert:
            if not update_existing:
                return error_response(
                    f'Certificate with subject "{cert_info["cn"]}" already exists (ID: {existing_cert.id})',
                    409
                )

            # Decide what becomes of the stored key before touching the record
            # (#347 review)
            key_dropped = False
            if not key_pem and existing_cert.prv:
                matches = stored_private_key_matches(existing_cert.prv, cert, context=f"certificate {existing_cert.id}")
                if matches is None:
                    db.session.rollback()
                    return error_response(
                        'Cannot verify the stored private key against the new '
                        'certificate; the stored key could not be read', 409)
                key_dropped = matches is False

            # Update existing certificate
            first_san = (cert_info.get('san_dns') or [None])[0]
            existing_cert.descr = name or cert_info['cn'] or first_san or existing_cert.descr
            existing_cert.crt = base64.b64encode(cert_pem).decode('utf-8')
            if key_pem:
                existing_cert.prv = encrypted_prv
            elif key_dropped:
                existing_cert.prv = None
            existing_cert.valid_from = cert_info['valid_from']
            existing_cert.valid_to = cert_info['valid_to']
            existing_cert.aki = cert_info.get('aki')
            existing_cert.ski = cert_info.get('ski')
            if cert_info.get('serial_number') is not None:
                existing_cert.serial_number = str(cert_info['serial_number'])
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
                ca = db.session.get(CA, ca_id)
                if ca:
                    existing_cert.caref = ca.refid

            ok, err = safe_commit(logger, "Failed to update certificate")
            if not ok:
                return err
            AuditService.log_action(
                action='certificate_updated',
                resource_type='certificate',
                resource_id=existing_cert.id,
                resource_name=existing_cert.descr,
                details=f'Updated certificate via import: {existing_cert.descr}',
                success=True
            )

            message = f'Certificate "{existing_cert.descr}" updated (already existed)'
            if key_dropped:
                message += '; the stored key did not match the new certificate and was unbound'
            return success_response(data=existing_cert.to_dict(), message=message)

        # Regular certificate - find parent CA
        caref = _resolve_caref(ca_id, cert_info)

        # Create certificate record
        refid = str(uuid.uuid4())
        first_san = (cert_info.get('san_dns') or [None])[0]
        certificate = Certificate(
            refid=refid,
            descr=name or cert_info['cn'] or first_san or filename,
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=encrypted_prv,
            caref=caref,
            subject=cert_info['subject'],
            issuer=cert_info['issuer'],
            aki=cert_info.get('aki'),
            ski=cert_info.get('ski'),
            serial_number=str(cert_info['serial_number']) if cert_info.get('serial_number') is not None else None,
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
        ok, err = safe_commit(logger, "Failed to import certificate")
        if not ok:
            return err
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
