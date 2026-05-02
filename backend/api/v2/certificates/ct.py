"""
Certificates CT Routes
/api/v2/certificates/*/submit-ct - Certificate Transparency submission
"""

import json
import base64
import logging
from flask import request
from auth.unified import require_auth
from models import Certificate, CA, SystemConfig, db
from services.audit_service import AuditService
from utils.response import success_response, error_response
from utils.ct_client import collect_scts
from . import bp

logger = logging.getLogger(__name__)


@bp.route('/api/v2/certificates/<int:cert_id>/submit-ct', methods=['POST'])
@require_auth(['write:certificates'])
def submit_to_ct(cert_id):
    """Submit a certificate to Certificate Transparency logs."""
    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    if not cert.crt:
        return error_response('Certificate has no PEM data', 400)

    ct_enabled = SystemConfig.query.filter_by(key='ct_enabled').first()
    if not ct_enabled or ct_enabled.value != 'true':
        return error_response('Certificate Transparency is not enabled', 400)

    try:
        ct_log_urls_config = SystemConfig.query.filter_by(key='ct_log_urls').first()
        ct_log_urls = json.loads(ct_log_urls_config.value) if ct_log_urls_config and ct_log_urls_config.value else None

        # Build cert chain
        cert_pem = base64.b64decode(cert.crt).decode('utf-8')
        chain = [cert_pem]

        # Add issuer cert if available
        if cert.ca_id:
            ca = CA.query.get(cert.ca_id)
            if ca and ca.crt:
                ca_pem = base64.b64decode(ca.crt).decode('utf-8')
                chain.append(ca_pem)

        scts = collect_scts(chain, ct_log_urls)

        if not scts:
            return error_response('No CT logs accepted the certificate', 400)

        # Store SCT info
        sct_data = json.dumps(scts)
        config_key = f'cert_scts_{cert_id}'
        config = SystemConfig.query.filter_by(key=config_key).first()
        if config:
            config.value = sct_data
        else:
            config = SystemConfig(key=config_key, value=sct_data)
            db.session.add(config)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to store SCTs: {e}")
            return error_response('Failed to store SCT data', 500)

        AuditService.log_action(
            'cert_ct_submitted',
            resource_type='certificate',
            resource_id=cert_id,
            details=f'Certificate submitted to {len(scts)} CT log(s)'
        )

        return success_response(data={
            'scts_count': len(scts),
            'logs': [{'log_url': s.get('log_url', 'unknown'), 'timestamp': s.get('timestamp')} for s in scts]
        }, message=f'Certificate submitted to {len(scts)} CT log(s)')

    except Exception as e:
        logger.error(f"CT submission failed for cert {cert_id}: {e}")
        return error_response('CT submission failed', 500)
