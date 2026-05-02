"""Certificate get route"""
import logging
import json
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import Certificate, CA, db
from models.truststore import TrustedCertificate
from services.compliance_service import calculate_compliance_score
from . import bp

logger = logging.getLogger(__name__)


@bp.route('/api/v2/certificates/<int:cert_id>', methods=['GET'])
@require_auth(['read:certificates'])
def get_certificate(cert_id):
    """Get certificate details with chain validation status"""

    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)

    data = cert.to_dict()

    # Parse X.509 extensions from PEM
    from utils.cert_extensions import parse_certificate_extensions
    data['extensions'] = parse_certificate_extensions(cert.crt)

    # Build chain validation status
    chain_status = _validate_cert_chain(cert)
    data['chain_status'] = chain_status

    # Full compliance breakdown for detail view
    compliance = calculate_compliance_score(data)
    data['compliance'] = compliance

    # CT SCT info
    from models import SystemConfig
    sct_config = SystemConfig.query.filter_by(key=f'cert_scts_{cert_id}').first()
    if sct_config and sct_config.value:
        try:
            data['ct_scts'] = json.loads(sct_config.value)
        except Exception:
            data['ct_scts'] = None
    else:
        data['ct_scts'] = None

    return success_response(data=data)


def _validate_cert_chain(cert):
    """Validate certificate chain and return status info"""

    chain = []
    status = 'unknown'
    trust_source = None
    trust_anchor = None

    # If cert has a caref, it's linked to a managed CA
    if cert.caref:
        ca = CA.query.filter_by(refid=cert.caref).first()
        if ca:
            chain.append({'name': ca.common_name or ca.descr, 'type': 'managed_ca'})
            # Walk up to root
            current_ca = ca
            depth = 0
            while current_ca and depth < 10:
                if current_ca.is_root:
                    status = 'complete'
                    trust_source = 'managed_ca'
                    trust_anchor = current_ca.common_name or current_ca.descr
                    break
                if current_ca.caref:
                    parent = CA.query.filter_by(refid=current_ca.caref).first()
                    if parent:
                        chain.append({'name': parent.common_name or parent.descr, 'type': 'managed_ca'})
                        current_ca = parent
                        depth += 1
                    else:
                        break
                else:
                    break

            # If chain is not complete, check Trust Store for the top CA's issuer
            if status != 'complete' and current_ca:
                trusted = TrustedCertificate.query.filter_by(subject=current_ca.issuer).first()
                if trusted:
                    chain.append({'name': trusted.name, 'type': 'trust_store'})
                    status = 'complete'
                    trust_source = 'trust_store'
                    trust_anchor = trusted.name
                else:
                    status = 'incomplete'
    else:
        # No caref — try AKI lookup
        if cert.aki:
            ca = CA.query.filter(CA.ski == cert.aki).first()
            if ca:
                chain.append({'name': ca.common_name or ca.descr, 'type': 'managed_ca'})
                status = 'partial'
                trust_source = 'managed_ca'
            else:
                trusted = TrustedCertificate.query.filter_by(subject=cert.issuer).first()
                if trusted:
                    chain.append({'name': trusted.name, 'type': 'trust_store'})
                    status = 'complete'
                    trust_source = 'trust_store'
                    trust_anchor = trusted.name
                else:
                    status = 'incomplete'
        elif cert.issuer:
            # Fallback: issuer DN matching
            ca = CA.query.filter(CA.subject == cert.issuer).first()
            if ca:
                chain.append({'name': ca.common_name or ca.descr, 'type': 'managed_ca'})
                status = 'partial'
                trust_source = 'managed_ca'
            else:
                trusted = TrustedCertificate.query.filter_by(subject=cert.issuer).first()
                if trusted:
                    chain.append({'name': trusted.name, 'type': 'trust_store'})
                    status = 'complete'
                    trust_source = 'trust_store'
                    trust_anchor = trusted.name
                else:
                    status = 'incomplete'

    return {
        'status': status,  # complete, incomplete, partial, unknown
        'trust_source': trust_source,
        'trust_anchor': trust_anchor,
        'chain': chain,
        'chain_length': len(chain),
    }
