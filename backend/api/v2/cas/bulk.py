"""
CAs Bulk Operations
"""

from . import bp
from flask import request, Response
import base64
import subprocess
import tempfile
import os
import logging

from auth.unified import require_auth
from utils.response import success_response, error_response
from services.audit_service import AuditService
from models import CA, Certificate, db

logger = logging.getLogger(__name__)


@bp.route('/api/v2/cas/bulk/delete', methods=['POST'])
@require_auth(['delete:cas'])
def bulk_delete_cas():
    """Bulk delete CAs"""

    data = request.get_json()
    if not data or not data.get('ids'):
        return error_response('ids array required', 400)

    ids = data['ids']
    results = {'success': [], 'failed': []}

    for ca_id in ids:
        try:
            ca = CA.query.get(ca_id)
            if not ca:
                results['failed'].append({'id': ca_id, 'error': 'Not found'})
                continue
            
            ca_name = ca.descr or f'CA #{ca_id}'
            
            # Check for child CAs
            child_cas = CA.query.filter_by(caref=ca.refid).count()
            if child_cas > 0:
                results['failed'].append({'id': ca_id, 'error': f'{child_cas} intermediate CA(s) depend on it'})
                continue
            
            # Check for issued certificates
            issued_certs = Certificate.query.filter_by(caref=ca.refid).count()
            if issued_certs > 0:
                results['failed'].append({'id': ca_id, 'error': f'{issued_certs} certificate(s) issued by it'})
                continue
            
            # Clean up dependent records
            from models.crl import CRLMetadata
            from models.ocsp import OCSPResponse
            CRLMetadata.query.filter_by(ca_id=ca_id).delete()
            OCSPResponse.query.filter_by(ca_id=ca_id).delete()
            
            db.session.delete(ca)
            db.session.commit()
            results['success'].append(ca_id)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete CA {ca_id}: {e}")
            results['failed'].append({'id': ca_id, 'error': 'Deletion failed'})

    AuditService.log_action(
        action='cas_bulk_deleted',
        resource_type='ca',
        resource_id=','.join(str(i) for i in results['success']),
        resource_name=f"{len(results['success'])} CAs",
        details=f'Bulk deleted {len(results["success"])} CAs',
        success=True
    )

    return success_response(data=results, message=f"{len(results['success'])} CAs deleted")


@bp.route('/api/v2/cas/bulk/export', methods=['POST'])
@require_auth(['read:cas'])
def bulk_export_cas():
    """Export selected CAs"""

    data = request.get_json()
    if not data or not data.get('ids'):
        return error_response('ids array required', 400)

    export_format = data.get('format', 'pem').lower()
    cas = CA.query.filter(CA.id.in_(data['ids']), CA.crt.isnot(None)).all()

    if not cas:
        return error_response('No CAs found', 404)

    try:
        if export_format == 'pem':
            pem_data = b''
            for ca in cas:
                pem_data += base64.b64decode(ca.crt)
                if not pem_data.endswith(b'\n'):
                    pem_data += b'\n'
            return Response(pem_data, mimetype='application/x-pem-file',
                headers={'Content-Disposition': 'attachment; filename="ca-certificates.pem"'})
        elif export_format in ('pkcs7', 'p7b'):
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                for ca in cas:
                    f.write(base64.b64decode(ca.crt))
                    f.write(b'\n')
                pem_file = f.name
            try:
                p7b_output = subprocess.check_output(
                    ['openssl', 'crl2pkcs7', '-nocrl', '-certfile', pem_file, '-outform', 'DER'],
                    stderr=subprocess.DEVNULL, timeout=30)
                return Response(p7b_output, mimetype='application/x-pkcs7-certificates',
                    headers={'Content-Disposition': 'attachment; filename="ca-certificates.p7b"'})
            finally:
                os.unlink(pem_file)
        else:
            return error_response('Supported formats: pem, p7b', 400)
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return error_response('Export failed', 500)
