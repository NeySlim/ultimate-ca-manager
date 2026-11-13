"""Certificate import route"""
import logging
import base64
import uuid
import json
import traceback
from flask import request, g
from auth.unified import has_permission, require_auth
from fips_mode import FipsRestricted
from utils.db_transaction import safe_commit
from utils.key_codec import MalformedKey
from utils.response import success_response, error_response, created_response
from utils.file_validation import validate_upload, CERT_EXTENSIONS
from models import Certificate, CA, RevokedSerial, db
from services.audit_service import AuditService
from utils.cert_issuer import ca_signature_verdict, ca_signed, private_key_matches, signing_ca_for, stored_private_key_matches
from utils.key_type import weak_ca_key_refusal
from services.import_service import (
    KeyPasswordError, parse_certificate_file, is_ca_certificate, extract_cert_info,
    find_existing_ca_for_import, cross_mode_from, finish_cross_attach,
    find_existing_certificate, find_pending_csr_for_certificate,
    AmbiguousImportTarget, CrossCertificateImport, ImportConflict, update_ca_from_import, install_on_pending_ca, stored_certificate_serial,
    serialize_cert_to_pem, serialize_key_to_pem, relink_parent_caref
)
from services.cert_service import CertificateService
from services.cert.issued_lookup import apply_persisted_revocation, record_serial_clause
from services.ca_service import CAService
from security.encryption import encrypt_private_key
from . import bp

logger = logging.getLogger(__name__)


class _NotSignedByNamedCa(ValueError):
    pass


def _resolve_caref(ca_id, cert):
    """The issuing CA's refid: the CA the caller named, which must have signed
    *cert*, else the stored CA whose key verifies it; None when UCM holds no
    CA that signed it (a third-party certificate)."""
    if ca_id:
        ca = db.session.get(CA, ca_id)
        if ca is None:
            return None
        verdict = ca_signature_verdict(ca, cert)
        if verdict is None:
            raise _NotSignedByNamedCa(
                f'The certificate cannot be verified against CA "{ca.descr}": its certificate '
                'is missing or unreadable, or its key type cannot be checked')
        if not verdict:
            raise _NotSignedByNamedCa(f'The certificate was not signed by CA "{ca.descr}"')
        return ca.refid
    ca = signing_ca_for(cert)
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

        # A CA that would sign must clear the RSA floor; without its key it is only read
        weak = (import_key and private_key is not None and is_ca_certificate(cert) and weak_ca_key_refusal(private_key))
        if weak:
            return error_response(weak, 400)

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
            if not has_permission('write:cas', g.permissions):
                return error_response('write:cas permission required to import a CA certificate', 403)
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
                            existing_ca, cert_pem, username, encrypted_prv=encrypted_prv, name=name or None)
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
                from services.webhook_service import emit_ca_updated
                emit_ca_updated(existing_ca.to_dict(), actor=username, changes={'certificate': 'imported'})

                message = f'CA certificate "{existing_ca.descr}" updated (already existed)'
                if key_dropped:
                    message += '; the stored key did not match the new certificate and was unbound'
                return success_response(data=existing_ca.to_dict(), message=message)

            # Create new CA
            refid = str(uuid.uuid4())
            # A CA certificate issued elsewhere for a request pending in the
            # certificates table (an intermediate requested here, signed outside):
            # the request's key becomes the CA's and the request is fulfilled
            pending_request = find_pending_csr_for_certificate(cert)
            if pending_request is not None and not encrypted_prv and pending_request.prv:
                # The request's key is the certificate's (matched by SPKI): same RSA floor as a key in the file
                weak = weak_ca_key_refusal(cert.public_key())
                if weak:
                    return error_response(weak, 400)
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
                caref=relink_parent_caref(cert, None),
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
                details=f'Imported CA (auto-detected): {ca.descr}',
                success=True
            )
            from services.webhook_service import emit_ca_created
            emit_ca_created(ca.to_dict(), actor=username)

            message = f'CA certificate "{ca.descr}" imported successfully (detected as CA)'
            if fulfilled:
                message += f'; pending request "{fulfilled}" fulfilled, its key is now the CA\'s'
            return created_response(data=ca.to_dict(), message=message)

        try:
            caref = _resolve_caref(ca_id, cert)
        except _NotSignedByNamedCa as e:
            return error_response(str(e), 400)

        # A certificate issued elsewhere for a CSR pending here completes
        # that record instead of creating a keyless duplicate (#341)
        pending_csr = find_pending_csr_for_certificate(cert)
        if pending_csr:
            username = getattr(getattr(g, 'current_user', None), 'username', None) or 'import'
            try:
                CertificateService.complete_external_csr(
                    pending_csr, cert, cert_pem,
                    caref=caref,
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
            return error_response(str(e), 409, e.details)

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
            old_serial = stored_certificate_serial(existing_cert)
            serial_changed = old_serial is not None and old_serial != cert.serial_number
            first_san = (cert_info.get('san_dns') or [None])[0]
            existing_cert.descr = name or cert_info['cn'] or first_san or existing_cert.descr
            existing_cert.crt = base64.b64encode(cert_pem).decode('utf-8')
            if serial_changed:
                # Revocation is per certificate (RFC 5280): a renewed certificate
                # is not the revoked one, whose serial stays on the CRL
                existing_cert.revoked = False
                existing_cert.revoked_at = None
                existing_cert.revoke_reason = None
                existing_cert.invalidity_at = None
                existing_cert.archived = False
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

            # The issuing CA is one whose key signed the new certificate, never
            # a link kept from the certificate it replaces
            if not caref and existing_cert.caref:
                kept = CA.query.filter_by(refid=existing_cert.caref).first()
                caref = existing_cert.caref if ca_signed(kept, cert) else None
            existing_cert.caref = caref
            if serial_changed:
                # The row now holds another certificate: the old serial's record stays, unlinked
                RevokedSerial.query.filter(
                    RevokedSerial.certificate_id == existing_cert.id,
                    record_serial_clause(old_serial),
                ).update({RevokedSerial.certificate_id: None}, synchronize_session='fetch')
            came_back_revoked = apply_persisted_revocation(existing_cert)

            # A key reaching a renewed certificate takes the bindings left behind for it;
            # a new serial deploys them through its renewal event
            https_moved = False
            if key_pem and not came_back_revoked:
                from services.binding_attention import follow_key
                user = getattr(g, 'current_user', None)
                https_moved = follow_key(existing_cert, actor=getattr(user, 'username', None) or 'system',
                                         queue=not serial_changed)
            ok, err = safe_commit(logger, "Failed to update certificate")
            if not ok:
                return err
            if https_moved and not serial_changed:
                from services.https_binding import apply_bound_now
                apply_bound_now(existing_cert.refid)
            AuditService.log_action(
                action='certificate_updated',
                resource_type='certificate',
                resource_id=existing_cert.id,
                resource_name=existing_cert.descr,
                details=f'Updated certificate via import: {existing_cert.descr}',
                success=True
            )

            # A new serial is a renewal (deploy bindings, webhooks and HTTPS binding
            # follow), a first certificate an import; the same serial stays silent
            cert_dict = existing_cert.to_dict()
            from services.webhook_service import WebhookService, emit_cert_stored
            user = getattr(g, 'current_user', None)
            # A certificate its CA revoked is no renewal of the one it replaces
            if not (came_back_revoked and serial_changed):
                emit_cert_stored(cert_dict, old_serial, cert.serial_number,
                                 first_event=WebhookService.CERT_IMPORTED,
                                 ca_refid=existing_cert.caref, actor=getattr(user, 'username', None))

            message = f'Certificate "{existing_cert.descr}" updated (already existed)'
            if key_dropped:
                message += '; the stored key did not match the new certificate and was unbound'
            return success_response(data=cert_dict, message=message)

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

        apply_persisted_revocation(certificate)
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
        cert_dict = certificate.to_dict()
        from services.webhook_service import emit_cert_imported
        emit_cert_imported(cert_dict, ca_refid=certificate.caref,
                           actor=getattr(getattr(g, 'current_user', None), 'username', None))

        return created_response(
            data=cert_dict,
            message=f'Certificate "{certificate.descr}" imported successfully'
        )

    except FipsRestricted:
        db.session.rollback()
        raise  # the app handler answers 400 with the FIPS problem type
    except (MalformedKey, KeyPasswordError) as e:
        db.session.rollback()
        return error_response(str(e), 400)
    except ValueError as e:
        db.session.rollback()
        logger.error(f"Certificate import validation error: {e}")
        return error_response('Invalid input', 400)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Certificate Import Error: {e}")
        logger.error(traceback.format_exc())
        return error_response('Import failed', 500)
