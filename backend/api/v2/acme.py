from utils.datetime_utils import utc_isoformat
"""
ACME Configuration Routes v2.0
/api/acme/* - ACME settings and stats
"""
import logging
from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response

logger = logging.getLogger('ucm.acme')

bp = Blueprint('acme_bp', __name__)


@bp.route('/api/v2/acme/settings', methods=['GET'])
@require_auth(['read:acme'])
def get_acme_settings():
    """Get ACME configuration"""
    from models import SystemConfig, CA
    # Get settings from SystemConfig
    enabled_cfg = SystemConfig.query.filter_by(key='acme.enabled').first()
    ca_id_cfg = SystemConfig.query.filter_by(key='acme.issuing_ca_id').first()

    enabled = enabled_cfg.value == 'true' if enabled_cfg else True
    ca_id = ca_id_cfg.value if ca_id_cfg else None

    # Revoke on renewal setting
    revoke_on_renewal_cfg = SystemConfig.query.filter_by(key='acme.revoke_on_renewal').first()
    revoke_on_renewal = revoke_on_renewal_cfg.value == 'true' if revoke_on_renewal_cfg else False
    superseded_count = _count_superseded_certificates()

    # Get CA name if CA ID is set
    ca_name = None
    if ca_id:
        ca = CA.query.filter_by(refid=ca_id).first()
        if not ca:
            try:
                ca = CA.query.get(int(ca_id))
            except (ValueError, TypeError):
                pass
        if ca:
            ca_name = ca.common_name

    return success_response(data={
        'enabled': enabled,
        'issuing_ca_id': ca_id,
        'issuing_ca_name': ca_name,
        'provider': 'Built-in ACME Server',
        'contact_email': 'admin@ucm.local',
        'revoke_on_renewal': revoke_on_renewal,
        'superseded_count': superseded_count,
    })


def _count_superseded_certificates():
    """Count old Local ACME server certificates that have been replaced by renewals."""
    from models.acme_models import AcmeOrder
    from models import Certificate

    orders = AcmeOrder.query.filter(
        AcmeOrder.certificate_id.isnot(None),
        AcmeOrder.status == 'valid'
    ).order_by(AcmeOrder.created_at.desc()).all()

    if not orders:
        return 0

    current_cert_ids = set()
    seen_identifiers = set()
    all_cert_ids = set()
    for order in orders:
        all_cert_ids.add(order.certificate_id)
        ident_key = order.identifiers
        if ident_key not in seen_identifiers:
            seen_identifiers.add(ident_key)
            current_cert_ids.add(order.certificate_id)

    superseded_ids = all_cert_ids - current_cert_ids
    if not superseded_ids:
        return 0

    return Certificate.query.filter(
        Certificate.id.in_(superseded_ids),
        Certificate.revoked == False
    ).count()
