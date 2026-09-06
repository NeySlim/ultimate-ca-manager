"""
Certificates Bulk Operations Routes
/api/v2/certificates/bulk/* - Bulk revoke, renew, delete, export
"""

import base64
import logging
import os
import subprocess
import tempfile
from flask import request, g, Response
from auth.unified import require_auth, has_permission
from sqlalchemy import or_

from models import Certificate, CA, db
from services.cert_service import CertificateService
from services.cert.renewal import RenewalError, renew_certificate_in_place
from services.audit_service import AuditService
from utils.response import success_response, error_response
from utils.datetime_utils import utc_now
from utils.revocation_reasons import normalize_revocation_reason, invalid_reason_message
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
    reason = normalize_revocation_reason(data.get('reason', 'unspecified'))
    if reason is None:
        return error_response(invalid_reason_message(data.get('reason')), 400)
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
    # CAs whose CRL must be regenerated once the loop finishes — every
    # renewal records the superseded serial in revoked_serials, and that
    # entry only reaches relying parties through a fresh CRL.
    renewed_ca_ids = set()

    username = g.current_user.username if hasattr(g, 'current_user') else 'system'
    actor_user_id = g.current_user.id if hasattr(g, 'current_user') else None

    for cert_id in ids:
        try:
            cert = db.session.get(Certificate, cert_id)
            if not cert:
                results['failed'].append({'id': cert_id, 'error': 'Not found'})
                continue

            # Identical semantics to POST /<id>/renew — same shared routine,
            # so the superseded serial, renewed_at/renewed_times, on-disk
            # files, OCSP cache, audit entry and webhook all behave the same.
            outcome = renew_certificate_in_place(
                cert,
                username=username,
                actor_user_id=actor_user_id,
                rekey=True,
                # CRLs are published once per CA after the loop instead of
                # once per certificate.
                regenerate_crl=False,
                trigger='bulk',
            )
            renewed_ca_ids.add(outcome['ca_id'])
            results['success'].append(cert_id)
        except RenewalError as e:
            db.session.rollback()
            results['failed'].append({'id': cert_id, 'error': e.message})
        except Exception as e:
            db.session.rollback()
            logger.error(f"Bulk renew failed for cert {cert_id}: {e}", exc_info=True)
            results['failed'].append({'id': cert_id, 'error': 'Renewal failed'})

    # Publish the superseded serials once per CA instead of once per cert.
    if renewed_ca_ids:
        from services.crl_service import CRLService
        for ca_id in renewed_ca_ids:
            ca = db.session.get(CA, ca_id)
            if not ca or not ca.cdp_enabled:
                continue
            try:
                CRLService.generate_crl(ca_id, username=username)
            except Exception as e:
                logger.warning(f"Failed to auto-generate CRL for CA {ca_id} after bulk renewal: {e}")

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
