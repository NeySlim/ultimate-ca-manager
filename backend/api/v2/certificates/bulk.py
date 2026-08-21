"""
Certificates Bulk Operations Routes
/api/v2/certificates/bulk/* - Bulk revoke, renew, delete, export
"""

import base64
import json
import logging
import os
import subprocess
import tempfile
import uuid
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
from utils.db_transaction import safe_commit
from utils.response import success_response, error_response
from utils.datetime_utils import utc_now
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
            cert = db.session.get(Certificate, cert_id)
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
            cert = db.session.get(Certificate, cert_id)
            if not cert:
                results['failed'].append({'id': cert_id, 'error': 'Not found'})
                continue
            if not cert.crt:
                results['failed'].append({'id': cert_id, 'error': 'No certificate data'})
                continue

            ca = CA.query.filter_by(refid=cert.caref).first()
            if not ca or not ca.has_private_key:
                results['failed'].append({'id': cert_id, 'error': 'Issuing CA not found or no private key'})
                continue
            if ca.offline:
                results['failed'].append({'id': cert_id, 'error': 'CA is offline'})
                continue

            orig_cert_pem = base64.b64decode(cert.crt)
            orig_cert = x509.load_pem_x509_certificate(orig_cert_pem, default_backend())
            ca_cert_pem = base64.b64decode(ca.crt)
            ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
            from services.hsm.ca_key_loader import get_ca_signing_key
            ca_key = get_ca_signing_key(ca)

            orig_pub_key = orig_cert.public_key()
            if isinstance(orig_pub_key, rsa.RSAPublicKey):
                new_key = rsa.generate_private_key(65537, orig_pub_key.key_size, default_backend())
            elif isinstance(orig_pub_key, ec.EllipticCurvePublicKey):
                new_key = ec.generate_private_key(orig_pub_key.curve, default_backend())
            else:
                new_key = rsa.generate_private_key(65537, 2048, default_backend())

            orig_duration = orig_cert.not_valid_after_utc - orig_cert.not_valid_before_utc
            validity_days = orig_duration.days if orig_duration.days > 0 else 365
            if validity_days > 3650:
                validity_days = 3650
            now = utc_now()
            not_after = now + timedelta(days=validity_days)
            ca_not_after = ca_cert.not_valid_after_utc.replace(tzinfo=None)
            if not_after > ca_not_after:
                not_after = ca_not_after

            try:
                _bulk_sans = list(
                    orig_cert.extensions.get_extension_for_oid(
                        ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                    ).value
                )
            except x509.ExtensionNotFound:
                _bulk_sans = None
            try:
                from services.trust_store.constraints_mixin import validate_name_constraints
                validate_name_constraints(ca_cert, orig_cert.subject, _bulk_sans,
                                          renewal_of=orig_cert)
            except ValueError as exc:
                results['failed'].append({'id': cert_id, 'error': f'Name constraints: {exc}'})
                continue

            builder = (x509.CertificateBuilder()
                .subject_name(orig_cert.subject)
                .issuer_name(ca_cert.subject)
                .public_key(new_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now)
                .not_valid_after(not_after))

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

            # Snapshot old cert fields before revoke/delete (commits expire the ORM object)
            username = g.current_user.username if hasattr(g, 'current_user') else 'system'
            old_descr = cert.descr
            old_caref = cert.caref
            old_cert_type = cert.cert_type
            old_subject = cert.subject
            old_subject_cn = cert.subject_cn
            old_ocsp_uri = cert.ocsp_uri
            old_ocsp_must_staple = cert.ocsp_must_staple
            old_private_key_location = cert.private_key_location
            old_source = cert.source or 'manual'
            old_template_id = cert.template_id
            old_template_overrides = cert.template_overrides
            old_owner_group_id = cert.owner_group_id

            # Create new certificate row — build and commit BEFORE
            # revoking/deleting the old one so a commit failure doesn't
            # destroy the old cert with no replacement.
            new_serial_hex = format(new_cert.serial_number, 'x')
            new_refid = str(uuid.uuid4())
            new_cert_pem = new_cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
            new_key_pem = new_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption()
            ).decode('utf-8')

            # Extract SKI/AKI from new cert
            try:
                ski_ext = new_cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
                new_ski = ':'.join(f'{b:02x}' for b in ski_ext.value.digest)
            except x509.ExtensionNotFound:
                new_ski = None
            try:
                aki_ext = new_cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
                new_aki = ':'.join(f'{b:02x}' for b in aki_ext.value.key_identifier) if aki_ext.value.key_identifier else None
            except x509.ExtensionNotFound:
                new_aki = None

            # Extract SANs from new cert
            new_san_dns, new_san_ip, new_san_email, new_san_uri, new_san_upn = [], [], [], [], []
            try:
                san_ext = new_cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                for name in san_ext.value:
                    if name.type == x509.DNSName:
                        new_san_dns.append(name.value)
                    elif name.type == x509.IPAddress:
                        new_san_ip.append(str(name.value))
                    elif name.type == x509.RFC822Name:
                        new_san_email.append(name.value)
                    elif name.type == x509.UniformResourceIdentifier:
                        new_san_uri.append(name.value)
                    elif name.type == x509.OtherName:
                        if name.type_id.dotted_string == '1.3.6.1.4.1.311.20.2.3':
                            new_san_upn.append(name.value.decode('utf-8', errors='replace'))
            except x509.ExtensionNotFound:
                pass

            new_pub = new_cert.public_key()
            if isinstance(new_pub, rsa.RSAPublicKey):
                key_algo_str = f'RSA {new_pub.key_size}'
            elif isinstance(new_pub, ec.EllipticCurvePublicKey):
                key_algo_str = f'EC {new_pub.curve.name}'
            else:
                key_algo_str = 'Unknown'

            new_cert_row = Certificate(
                refid=new_refid,
                descr=old_descr,
                caref=old_caref,
                crt=base64.b64encode(new_cert_pem.encode()).decode(),
                prv=base64.b64encode(new_key_pem.encode()).decode(),
                cert_type=old_cert_type,
                subject=old_subject,
                subject_cn=old_subject_cn,
                issuer=ca_cert.subject.rfc4514_string(),
                serial_number=new_serial_hex,
                aki=new_aki,
                ski=new_ski,
                valid_from=now,
                valid_to=not_after,
                key_algo=key_algo_str,
                san_dns=json.dumps(new_san_dns) if new_san_dns else None,
                san_ip=json.dumps([str(ip) for ip in new_san_ip]) if new_san_ip else None,
                san_email=json.dumps(new_san_email) if new_san_email else None,
                san_uri=json.dumps(new_san_uri) if new_san_uri else None,
                san_upn=json.dumps(new_san_upn) if new_san_upn else None,
                ocsp_uri=old_ocsp_uri,
                ocsp_must_staple=old_ocsp_must_staple,
                private_key_location=old_private_key_location,
                revoked=False,
                source=old_source,
                template_id=old_template_id,
                template_overrides=old_template_overrides,
                owner_group_id=old_owner_group_id,
                created_by=username,
            )
            db.session.add(new_cert_row)
            ok, err = safe_commit(logger, f"Bulk renew failed for cert {cert_id}")
            if not ok:
                results['failed'].append({'id': cert_id, 'error': 'Renewal failed'})
                continue

            # Revoke old cert so its serial appears on CRL/OCSP
            # _suppress_events=True avoids emitting cert_revoked/cert_deleted
            # events — the bulk renewal emits a single cert_renewed per cert.
            try:
                CertificateService.revoke_certificate(
                    cert_id=cert_id, reason='superseded', username=username,
                    _suppress_events=True)
            except ValueError:
                pass  # Already revoked — RevokedSerial already exists
            except RuntimeError as e:
                logger.warning(f"Revocation failed for old cert {cert_id} after bulk renewal: {e}")

            # Delete old cert row (RevokedSerial persists revocation data)
            if not CertificateService.delete_certificate(cert_id=cert_id, username=username, _suppress_events=True):
                logger.warning(f"Failed to delete old certificate {cert_id} after bulk renewal")

            # Write cert/key files to disk for the new row (consistent with
            # create_certificate which writes human-readable filenames).
            try:
                from utils.file_naming import cert_cert_path, cert_key_path
                _cert_path = cert_cert_path(new_cert_row)
                _key_path = cert_key_path(new_cert_row)
                _cert_path.parent.mkdir(parents=True, exist_ok=True)
                _key_path.parent.mkdir(parents=True, exist_ok=True)
                _cert_path.write_bytes(new_cert_pem.encode())
                _key_path.write_bytes(new_key_pem.encode())
                try:
                    _key_path.chmod(0o600)
                except (OSError, PermissionError):
                    pass
            except Exception as e:
                logger.warning(f"Failed to write cert/key files for renewed cert {new_cert_row.id}: {e}")

            results['success'].append({'old_id': cert_id, 'new_id': new_cert_row.id})
        except Exception as e:
            db.session.rollback()
            logger.error(f"Bulk renew failed for cert {cert_id}: {e}")
            results['failed'].append({'id': cert_id, 'error': 'Renewal failed'})

    AuditService.log_action(
        action='certificates_bulk_renewed',
        resource_type='certificate',
        resource_id=','.join(str(r['new_id']) for r in results['success']),
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
    username = g.current_user.username if hasattr(g, 'current_user') else 'system'
    results = {'success': [], 'failed': []}

    for cert_id in ids:
        try:
            cert = db.session.get(Certificate, cert_id)
            if not cert:
                results['failed'].append({'id': cert_id, 'error': 'Not found'})
                continue

            # Prevent deletion of valid (non-revoked, non-expired) certificates.
            if cert.crt and not cert.revoked:
                if not cert.valid_to or cert.valid_to >= utc_now():
                    results['failed'].append({
                        'id': cert_id,
                        'error': 'Cannot delete a valid certificate — revoke it first',
                    })
                    continue

            # Delegate to the service so cert/key/csr files on disk are
            # unlinked along with the DB row instead of leaving them orphaned.
            if CertificateService.delete_certificate(cert_id=cert_id, username=username):
                results['success'].append(cert_id)
            else:
                results['failed'].append({'id': cert_id, 'error': 'Deletion failed'})
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
