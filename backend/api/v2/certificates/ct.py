"""
Certificates CT Routes
/api/v2/certificates/*/submit-ct - Certificate Transparency submission
"""

import json
import re
import base64
import logging
from flask import request
from auth.unified import require_auth
from models import Certificate, SystemConfig, db
from services.audit_service import AuditService
from utils.response import success_response, error_response
from utils.ca_chain import issuer_chain, PRIMARY
from utils.ct_client import collect_scts, _configured_log_urls
from . import bp

logger = logging.getLogger(__name__)

_PEM_CERT = re.compile(r'-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----', re.S)


@bp.route('/api/v2/certificates/<int:cert_id>/submit-ct', methods=['POST'])
@require_auth(['write:certificates'])
def submit_to_ct(cert_id):
    """Submit a certificate to Certificate Transparency logs."""
    cert = db.session.get(Certificate, cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    if not cert.crt:
        return error_response('Certificate has no PEM data', 400)

    ct_enabled = SystemConfig.query.filter_by(key='ct_enabled').first()
    if not ct_enabled or ct_enabled.value != 'true':
        return error_response('Certificate Transparency is not enabled', 400)

    try:
        ct_log_urls = _configured_log_urls()
        if ct_log_urls == []:
            return error_response('No valid CT log configured', 400)

        # add-chain takes one certificate per element (RFC 6962 §4.1): split an
        # inline chain, else complete the leaf with its issuers up to the root.
        chain = _PEM_CERT.findall(base64.b64decode(cert.crt).decode('utf-8'))
        if not chain:
            return error_response('Certificate has no PEM data', 400)
        if len(chain) == 1:
            # cert.ca is None for an orphan: issuer_chain gives [], the leaf goes alone.
            chain += [link.pem.decode('ascii') for link in issuer_chain(cert.ca, PRIMARY)]

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
