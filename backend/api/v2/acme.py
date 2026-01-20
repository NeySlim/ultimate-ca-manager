"""
ACME Configuration Routes v2.0
/api/acme/* - ACME settings and stats
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge

bp = Blueprint('acme_v2', __name__)


@bp.route('/api/acme/settings', methods=['GET'])
@require_auth(['read:acme'])
def get_acme_settings():
    """Get ACME configuration"""
    # For now returning static config, could be moved to SystemConfig
    return success_response(data={
        'enabled': True,
        'provider': 'Built-in ACME Server',
        'contact_email': 'admin@ucm.local'
    })


@bp.route('/api/acme/settings', methods=['PATCH'])
@require_auth(['write:acme'])
def update_acme_settings():
    """Update ACME configuration"""
    data = request.json
    # Implement logic to save to SystemConfig
    return success_response(
        data=data,
        message='ACME settings updated'
    )


@bp.route('/api/acme/stats', methods=['GET'])
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


@bp.route('/api/acme/accounts', methods=['GET'])
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


@bp.route('/api/acme/orders', methods=['GET'])
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


@bp.route('/api/acme/proxy/register', methods=['POST'])
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
