"""
Certificates Bulk Operations Routes
/api/v2/certificates/bulk/* - Bulk revoke, renew, delete, export
"""

import base64
import logging
from datetime import timedelta
from flask import request, g, Response
from auth.unified import require_auth, has_permission
from sqlalchemy import or_
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID

from models import Certificate, CA, db
from services.cert_service import CertificateService
from services.audit_service import AuditService
from utils.response import success_response, error_response
from utils.datetime_utils import utc_now
from security.encryption import decrypt_private_key
from . import bp

logger = logging.getLogger(__name__)


@bp.route('/api/v2/certificates/bulk/revoke', methods=['POST'])
@require_auth(['write:certificates'])
def bulk_revoke_certificates():
    """Bulk revoke certificates"""

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
            logger.error(f"Bulk revoke failed for cert {cert_id}: {e}")
            results['failed'].append({'id': cert_id, 'error': 'Revocation failed'})

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
            ca_key_pem = base64.b64decode(decrypt_private_key(ca.prv))
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
            now = utc_now()

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
            logger.error(f"Bulk renew failed for cert {cert_id}: {e}")
            results['failed'].append({'id': cert_id, 'error': 'Renewal failed'})

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

            from models import ApprovalRequest
            ApprovalRequest.query.filter_by(certificate_id=cert_id).delete()

            db.session.delete(cert)
            db.session.commit()
            results['success'].append(cert_id)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Bulk delete failed for cert {cert_id}: {e}")
            results['failed'].append({'id': cert_id, 'error': 'Deletion failed'})

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
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                for cert in certs:
                    f.write(base64.b64decode(cert.crt))
                    f.write(b'\n')
                pem_file = f.name
            try:
                p7b_output = subprocess.check_output(
                    ['openssl', 'crl2pkcs7', '-nocrl', '-certfile', pem_file, '-outform', 'DER'],
                    stderr=subprocess.DEVNULL, timeout=30)
                return Response(p7b_output, mimetype='application/x-pkcs7-certificates',
                    headers={'Content-Disposition': 'attachment; filename="certificates.p7b"'})
            finally:
                os.unlink(pem_file)
        else:
            return error_response('Supported formats: pem, p7b', 400)
    except Exception as e:
        logger.error(f"Bulk export failed: {e}")
        return error_response('Export failed', 500)
