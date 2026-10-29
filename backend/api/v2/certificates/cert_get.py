"""Certificate get route"""
import logging
import json
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import Certificate, CA, db
from models.truststore import TrustedCertificate
from services.compliance_service import calculate_compliance_score
from utils.cert_issuer import find_ca_by_ski
from . import bp

logger = logging.getLogger(__name__)


@bp.route('/api/v2/certificates/<int:cert_id>', methods=['GET'])
@require_auth(['read:certificates'])
def get_certificate(cert_id):
    """Get certificate details with chain validation status"""

    cert = db.session.get(Certificate, cert_id)
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
    variants = []
    status = 'unknown'
    trust_source = None
    trust_anchor = None

    # If cert has a caref, it's linked to a managed CA
    if cert.caref:
        ca = CA.query.filter_by(refid=cert.caref).first()
        if ca:
            chain.append({'name': ca.common_name or ca.descr, 'type': 'managed_ca'})
            # The chain the CA serves, the issuing CA plus ten levels at most; a cross-certificate is
            # not a root, so the walk goes on through its issuer when it is held.
            from utils.ca_chain import chain_variants, issuer_chain
            top_issuer = ca.issuer
            for link in issuer_chain(ca)[:11]:
                node = link.ca
                if node is not ca:
                    chain.append({'name': node.common_name or node.descr, 'type': 'managed_ca'})
                elif link.cross is not None:
                    chain[0]['cross_certificate_id'] = link.cross.id
                top_issuer = link.cross.issuer if link.cross is not None else node.issuer
                if link.cross is None and node.is_root:
                    status = 'complete'
                    trust_source = 'managed_ca'
                    trust_anchor = node.common_name or node.descr
                    break
            variants = chain_variants(ca)

            # If chain is not complete, check Trust Store for the top CA's issuer
            if status != 'complete':
                trusted = TrustedCertificate.query.filter_by(subject=top_issuer).first()
                if trusted:
                    chain.append({'name': trusted.name, 'type': 'trust_store'})
                    status = 'complete'
                    trust_source = 'trust_store'
                    trust_anchor = trusted.name
                else:
                    # A served cross-certificate whose issuer is not held leaves the primary anchor standing.
                    primary = issuer_chain(ca, 'primary')
                    primary_top = primary[-1].ca if primary else None
                    if primary_top is not None and primary_top.is_root:
                        status = 'complete'
                        trust_source = 'managed_ca'
                        trust_anchor = primary_top.common_name or primary_top.descr
                    else:
                        status = 'incomplete'
    else:
        # No caref — try AKI lookup
        if cert.aki:
            ca = find_ca_by_ski(cert.aki)
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
        'variants': variants,
    }
