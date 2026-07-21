"""Certificate renewal route"""
import logging
import base64
from datetime import timedelta
from flask import request, g
from auth.unified import require_auth
from utils.db_transaction import safe_commit
from utils.response import success_response, error_response
from models import Certificate, CA, db
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID
from services.audit_service import AuditService
from websocket.emitters import on_certificate_renewed
from utils.datetime_utils import utc_now
from . import bp

logger = logging.getLogger(__name__)


@bp.route('/api/v2/certificates/<int:cert_id>/renew', methods=['POST'])
@require_auth(['write:certificates'])
def renew_certificate(cert_id):
    """
    Renew certificate - Creates a new certificate with same subject/SANs but new validity
    """

    # Get original certificate
    cert = db.session.get(Certificate, cert_id)
    if not cert:
        return error_response('Certificate not found', 404)

    if not cert.crt:
        return error_response('Certificate data not available', 400)

    # Certificates issued by a Microsoft AD CS connection can't be re-signed
    # locally (the issuing CA's key lives on the Windows CA) — resubmit the
    # original CSR through the connector instead.
    if cert.source == 'msca':
        return _renew_msca_certificate(cert)

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

    if not ca.has_private_key:
        return error_response('CA private key not available. Cannot renew without CA private key.', 400)
    if ca.offline:
        return error_response('CA is offline; restore it before renewing', 400)

    try:
        # Load original certificate
        orig_cert_pem = base64.b64decode(cert.crt)
        orig_cert = x509.load_pem_x509_certificate(orig_cert_pem, default_backend())

        # Load CA certificate and key
        ca_cert_pem = base64.b64decode(ca.crt)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
        from services.hsm.ca_key_loader import get_ca_signing_key
        ca_key = get_ca_signing_key(ca)

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

        # Calculate new validity (same duration as original, starting now; cap 1..3650)
        orig_duration = orig_cert.not_valid_after_utc - orig_cert.not_valid_before_utc
        validity_days = orig_duration.days if orig_duration.days > 0 else 365
        if validity_days > 3650:
            validity_days = 3650

        now = utc_now()
        not_before = now
        not_after = now + timedelta(days=validity_days)
        # Don't exceed CA expiration
        ca_not_after = ca_cert.not_valid_after_utc.replace(tzinfo=None)
        if not_after > ca_not_after:
            not_after = ca_not_after

        # Re-validate the subject/SANs against the CA chain's NameConstraints
        # before re-issuing: the CA's constraints may have been tightened since
        # the original certificate was signed, so a renewal must not blindly
        # reproduce a now-out-of-scope name (RFC 5280 §4.2.1.10).
        try:
            renew_sans = list(
                orig_cert.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                ).value
            )
        except x509.ExtensionNotFound:
            renew_sans = None
        try:
            from services.trust_store.constraints_mixin import validate_name_constraints
            validate_name_constraints(ca_cert, orig_cert.subject, renew_sans)
        except ValueError as exc:
            logger.info(f"Renewal rejected by CA NameConstraints: {exc}")
            return error_response(f"Renewal violates CA name constraints: {exc}", 400)

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

        ok, err = safe_commit(logger, "Failed to renew certificate")
        if not ok:
            return err

        # Audit log
        try:
            AuditService.log_action(
                action='certificate_renewed',
                resource_type='certificate',
                resource_id=str(cert_id),
                resource_name=cert.subject,
                details=f"Renewed until {not_after.isoformat()}",
                user_id=g.current_user.id if hasattr(g, 'current_user') else None
            )
        except Exception:
            pass

        username = g.current_user.username if hasattr(g, 'current_user') else 'system'
        cert_dict = cert.to_dict()
        cert_caref = cert.caref
        from services.webhook_service import emit_cert_renewed
        emit_cert_renewed(cert_dict, ca_refid=cert_caref, actor=username)

        return success_response(
            data=cert_dict,
            message='Certificate renewed successfully'
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to renew certificate: {e}")
        return error_response('Failed to renew certificate', 500)


def _renew_msca_certificate(cert):
    """Renew a Microsoft-CA-issued certificate through its AD CS connection."""
    from api.v2.msca import renew_via_msca  # deferred: avoids circular import

    username = g.current_user.username if hasattr(g, 'current_user') else 'system'
    cert_id = cert.id

    try:
        result = renew_via_msca(cert, username=username)
    except PermissionError as e:
        return error_response(str(e), 403)
    except ValueError as e:
        logger.error(f"Cannot renew certificate {cert_id} via Microsoft CA: {e}")
        return error_response(str(e), 400)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to renew certificate {cert_id} via Microsoft CA: {e}", exc_info=True)
        return error_response('Failed to renew certificate via Microsoft CA', 500)

    if result.get('status') == 'pending':
        return success_response(
            data=cert.to_dict(),
            message='Renewal submitted to Microsoft CA — pending CA manager approval',
            meta={'msca_status': 'pending'}
        )

    # Issued: the certificate row was updated in place by the import
    try:
        AuditService.log_action(
            action='certificate_renewed',
            resource_type='certificate',
            resource_id=str(cert_id),
            resource_name=cert.subject,
            details=f"Renewed via Microsoft CA until {cert.valid_to.isoformat() if cert.valid_to else 'unknown'}",
            user_id=g.current_user.id if hasattr(g, 'current_user') else None
        )
    except Exception:
        pass

    cert_dict = cert.to_dict()
    cert_caref = cert.caref
    from services.webhook_service import emit_cert_renewed
    emit_cert_renewed(cert_dict, ca_refid=cert_caref, actor=username)

    return success_response(
        data=cert_dict,
        message='Certificate renewed by Microsoft CA',
        meta={'msca_status': 'issued'}
    )
