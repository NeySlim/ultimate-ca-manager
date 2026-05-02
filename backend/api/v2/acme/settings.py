"""ACME settings and stats routes"""
from flask import request
from models import db, AcmeOrder, SystemConfig, CA, Certificate
from services.audit_service import AuditService
from services.cert_service import CertificateService
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit

from . import bp, logger


def _count_superseded_certificates():
    """Count old Local ACME server certificates that have been replaced by renewals.
    For each unique set of identifiers, only the latest order's certificate is current."""
    # Get all valid orders with certificates
    orders = AcmeOrder.query.filter(
        AcmeOrder.certificate_id.isnot(None),
        AcmeOrder.status == 'valid'
    ).order_by(AcmeOrder.created_at.desc()).all()

    if not orders:
        return 0

    # For each unique identifiers set, keep only the latest cert_id
    current_cert_ids = set()
    seen_identifiers = set()
    all_cert_ids = set()
    for order in orders:
        all_cert_ids.add(order.certificate_id)
        ident_key = order.identifiers  # JSON string, same domains = same key
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


def _revoke_superseded_certificates():
    """Revoke all superseded Local ACME server certificates"""
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

    superseded = Certificate.query.filter(
        Certificate.id.in_(superseded_ids),
        Certificate.revoked == False
    ).all()

    revoked_count = 0
    for cert in superseded:
        try:
            CertificateService.revoke_certificate(
                cert_id=cert.id, reason='superseded', username='system'
            )
            revoked_count += 1
        except Exception as e:
            logger.warning(f"Failed to revoke superseded cert {cert.id}: {e}")

    return revoked_count


@bp.route('/api/v2/acme/settings', methods=['GET'])
@require_auth(['read:acme'])
def get_acme_settings():
    """Get ACME configuration"""
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
            # Try by ID
            try:
                ca = CA.query.get(int(ca_id))
            except (ValueError, TypeError):
                pass  # ca_id is not a valid integer
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


@bp.route('/api/v2/acme/settings', methods=['PATCH'])
@require_auth(['write:acme'])
def update_acme_settings():
    """Update ACME configuration"""
    data = request.json

    # Update enabled status
    if 'enabled' in data:
        enabled_cfg = SystemConfig.query.filter_by(key='acme.enabled').first()
        if not enabled_cfg:
            enabled_cfg = SystemConfig(key='acme.enabled', description='ACME server enabled')
            db.session.add(enabled_cfg)
        enabled_cfg.value = 'true' if data['enabled'] else 'false'

    # Update issuing CA
    if 'issuing_ca_id' in data:
        ca_id_cfg = SystemConfig.query.filter_by(key='acme.issuing_ca_id').first()
        if not ca_id_cfg:
            ca_id_cfg = SystemConfig(key='acme.issuing_ca_id', description='ACME issuing CA refid')
            db.session.add(ca_id_cfg)
        ca_id_cfg.value = data['issuing_ca_id'] if data['issuing_ca_id'] else ''

    # Update revoke on renewal
    if 'revoke_on_renewal' in data:
        revoke_cfg = SystemConfig.query.filter_by(key='acme.revoke_on_renewal').first()
        if not revoke_cfg:
            revoke_cfg = SystemConfig(key='acme.revoke_on_renewal', description='Revoke old certificate after ACME renewal')
            db.session.add(revoke_cfg)
        revoke_cfg.value = 'true' if data['revoke_on_renewal'] else 'false'

    ok, _err = safe_commit(logger, "Failed to update ACME settings")
    if not ok:
        return _err

    # Revoke existing superseded certs if requested
    revoked_count = 0
    if data.get('revoke_on_renewal') and data.get('revoke_superseded'):
        revoked_count = _revoke_superseded_certificates()

    AuditService.log_action(
        action='acme_settings_update',
        resource_type='acme',
        resource_name='ACME Settings',
        details=f'Updated ACME server settings' + (f', revoked {revoked_count} superseded cert(s)' if revoked_count else ''),
        success=True
    )

    return success_response(
        data={**data, 'revoked_count': revoked_count},
        message='ACME settings updated'
    )


@bp.route('/api/v2/acme/stats', methods=['GET'])
@require_auth(['read:acme'])
def get_acme_stats():
    """Get ACME statistics"""
    from models import AcmeOrder as _AcmeOrder, AcmeAccount as _AcmeAccount
    total_orders = _AcmeOrder.query.count()
    pending_orders = _AcmeOrder.query.filter_by(status='pending').count()
    valid_orders = _AcmeOrder.query.filter_by(status='valid').count()
    invalid_orders = _AcmeOrder.query.filter_by(status='invalid').count()
    active_accounts = _AcmeAccount.query.filter_by(status='valid').count()

    return success_response(data={
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'valid_orders': valid_orders,
        'invalid_orders': invalid_orders,
        'active_accounts': active_accounts
    })
