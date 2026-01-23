"""
ACME Configuration Routes v2.0
/api/acme/* - ACME settings and stats
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge, SystemConfig, CA

bp = Blueprint('acme_v2', __name__)


@bp.route('/api/v2/acme/settings', methods=['GET'])
@require_auth(['read:acme'])
def get_acme_settings():
    """Get ACME configuration"""
    # Get settings from SystemConfig
    enabled_cfg = SystemConfig.query.filter_by(key='acme.enabled').first()
    ca_id_cfg = SystemConfig.query.filter_by(key='acme.issuing_ca_id').first()
    
    enabled = enabled_cfg.value == 'true' if enabled_cfg else True
    ca_id = ca_id_cfg.value if ca_id_cfg else None
    
    # Get CA name if CA ID is set
    ca_name = None
    if ca_id:
        ca = CA.query.filter_by(refid=ca_id).first()
        if ca:
            ca_name = ca.common_name
    
    return success_response(data={
        'enabled': enabled,
        'issuing_ca_id': ca_id,
        'issuing_ca_name': ca_name,
        'provider': 'Built-in ACME Server',
        'contact_email': 'admin@ucm.local'
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
    
    db.session.commit()
    
    return success_response(
        data=data,
        message='ACME settings updated'
    )


@bp.route('/api/v2/acme/stats', methods=['GET'])
@require_auth(['read:acme'])
def get_acme_stats():
    """Get ACME statistics"""
    total_orders = AcmeOrder.query.count()
    pending_orders = AcmeOrder.query.filter_by(status='pending').count()
    valid_orders = AcmeOrder.query.filter_by(status='valid').count()
    invalid_orders = AcmeOrder.query.filter_by(status='invalid').count()
    active_accounts = AcmeAccount.query.filter_by(status='valid').count()
    
    return success_response(data={
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'valid_orders': valid_orders,
        'invalid_orders': invalid_orders,
        'active_accounts': active_accounts
    })


@bp.route('/api/v2/acme/accounts', methods=['GET'])
@require_auth(['read:acme'])
def list_acme_accounts():
    """List ACME accounts"""
    accounts = AcmeAccount.query.order_by(AcmeAccount.created_at.desc()).limit(100).all()
    data = []
    for acc in accounts:
        # Convert contact array to string for display if needed
        data.append({
            'id': acc.id,
            'account_id': acc.account_id,
            'status': acc.status,
            'contact': acc.contact_list,
            'created_at': acc.created_at.isoformat()
        })
        
    return success_response(data=data)


@bp.route('/api/v2/acme/orders', methods=['GET'])
@require_auth(['read:acme'])
def list_acme_orders():
    """List ACME orders"""
    status = request.args.get('status')
    query = AcmeOrder.query
    if status:
        query = query.filter_by(status=status)
        
    orders = query.order_by(AcmeOrder.created_at.desc()).limit(50).all()
    
    data = []
    for order in orders:
        # Extract identifiers for display
        identifiers_str = ", ".join([i.get('value', '') for i in order.identifiers_list])
        
        # Get account info
        account = order.account
        account_name = account.account_id if account else "Unknown"
        
        # Get challenge type (from first authz)
        method = "N/A"
        if order.authorizations.count() > 0:
            first_authz = order.authorizations.first()
            if first_authz.challenges.count() > 0:
                method = first_authz.challenges.first().type.upper()
        
        data.append({
            'id': order.id,
            'order_id': order.order_id,
            'domain': identifiers_str,
            'account': account_name,
            'status': order.status.capitalize(),
            'expires': order.expires.strftime('%Y-%m-%d'),
            'method': method,
            'created_at': order.created_at.isoformat()
        })
        
    return success_response(data=data)


@bp.route('/api/v2/acme/proxy/register', methods=['POST'])
@require_auth(['write:acme'])
def register_proxy_account():
    """Register ACME proxy account"""
    data = request.json
    
    if not data or not data.get('email'):
        return error_response('Email is required', 400)
    
    return success_response(
        data={'registered': True, 'email': data['email']},
        message='Proxy account registered'
    )
