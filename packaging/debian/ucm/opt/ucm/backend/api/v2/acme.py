"""
ACME Configuration Routes v2.0
/api/acme/* - ACME settings and stats
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge, SystemConfig, CA, Certificate

bp = Blueprint('acme_v2', __name__)


@bp.route('/api/v2/acme/settings', methods=['GET'])
@require_auth(['read:acme'])
def get_acme_settings():
    """Get ACME configuration"""
    # Get settings from SystemConfig
    enabled_cfg = SystemConfig.query.filter_by(key='acme.enabled').first()
    ca_id_cfg = SystemConfig.query.filter_by(key='acme.issuing_ca_id').first()
    proxy_email_cfg = SystemConfig.query.filter_by(key='acme.proxy_email').first()
    proxy_enabled_cfg = SystemConfig.query.filter_by(key='acme.proxy_enabled').first()
    
    enabled = enabled_cfg.value == 'true' if enabled_cfg else True
    ca_id = ca_id_cfg.value if ca_id_cfg else None
    proxy_email = proxy_email_cfg.value if proxy_email_cfg else None
    proxy_enabled = proxy_enabled_cfg.value == 'true' if proxy_enabled_cfg else False
    
    # Get CA name if CA ID is set
    ca_name = None
    if ca_id:
        ca = CA.query.filter_by(refid=ca_id).first()
        if not ca:
            # Try by ID
            try:
                ca = CA.query.get(int(ca_id))
            except:
                pass
        if ca:
            ca_name = ca.common_name
    
    return success_response(data={
        'enabled': enabled,
        'issuing_ca_id': ca_id,
        'issuing_ca_name': ca_name,
        'provider': 'Built-in ACME Server',
        'contact_email': 'admin@ucm.local',
        'proxy_enabled': proxy_enabled,
        'proxy_email': proxy_email,
        'proxy_registered': bool(proxy_email)
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
    
    # Update proxy enabled
    if 'proxy_enabled' in data:
        proxy_cfg = SystemConfig.query.filter_by(key='acme.proxy_enabled').first()
        if not proxy_cfg:
            proxy_cfg = SystemConfig(key='acme.proxy_enabled', description='ACME proxy enabled')
            db.session.add(proxy_cfg)
        proxy_cfg.value = 'true' if data['proxy_enabled'] else 'false'
    
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
        data.append({
            'id': acc.id,
            'account_id': acc.account_id,
            'status': acc.status,
            'contact': acc.contact_list,
            'terms_of_service_agreed': acc.terms_of_service_agreed,
            'jwk_thumbprint': acc.jwk_thumbprint,
            'created_at': acc.created_at.isoformat()
        })
        
    return success_response(data=data)


@bp.route('/api/v2/acme/accounts/<int:account_id>', methods=['GET'])
@require_auth(['read:acme'])
def get_acme_account(account_id):
    """Get single ACME account details"""
    acc = AcmeAccount.query.get(account_id)
    if not acc:
        return error_response('Account not found', 404)
    
    return success_response(data={
        'id': acc.id,
        'account_id': acc.account_id,
        'status': acc.status,
        'contact': acc.contact_list,
        'terms_of_service_agreed': acc.terms_of_service_agreed,
        'jwk_thumbprint': acc.jwk_thumbprint,
        'created_at': acc.created_at.isoformat()
    })


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


@bp.route('/api/v2/acme/accounts/<int:account_id>/orders', methods=['GET'])
@require_auth(['read:acme'])
def list_account_orders(account_id):
    """List orders for a specific ACME account"""
    account = AcmeAccount.query.get_or_404(account_id)
    
    orders = AcmeOrder.query.filter_by(account_id=account.id).order_by(
        AcmeOrder.created_at.desc()
    ).limit(50).all()
    
    data = []
    for order in orders:
        identifiers_str = ", ".join([i.get('value', '') for i in order.identifiers_list])
        
        method = "N/A"
        if order.authorizations.count() > 0:
            first_authz = order.authorizations.first()
            if first_authz.challenges.count() > 0:
                method = first_authz.challenges.first().type.upper()
        
        data.append({
            'id': order.id,
            'order_id': order.order_id,
            'domain': identifiers_str,
            'status': order.status.capitalize(),
            'expires': order.expires.strftime('%Y-%m-%d') if order.expires else None,
            'method': method,
            'created_at': order.created_at.isoformat()
        })
        
    return success_response(data=data)


@bp.route('/api/v2/acme/accounts/<int:account_id>/challenges', methods=['GET'])
@require_auth(['read:acme'])
def list_account_challenges(account_id):
    """List challenges for a specific ACME account"""
    account = AcmeAccount.query.get_or_404(account_id)
    
    # Get all orders for this account
    orders = AcmeOrder.query.filter_by(account_id=account.id).all()
    
    data = []
    for order in orders:
        for authz in order.authorizations:
            for challenge in authz.challenges:
                data.append({
                    'id': challenge.id,
                    'type': challenge.type.upper(),
                    'status': challenge.status.capitalize(),
                    'domain': authz.identifier_value,
                    'token': challenge.token[:20] + '...' if challenge.token and len(challenge.token) > 20 else challenge.token,
                    'validated': challenge.validated.isoformat() if challenge.validated else None,
                    'order_id': order.order_id,
                    'created_at': challenge.created_at.isoformat() if hasattr(challenge, 'created_at') and challenge.created_at else None
                })
    
    return success_response(data=data)


@bp.route('/api/v2/acme/proxy/register', methods=['POST'])
@require_auth(['write:acme'])
def register_proxy_account():
    """Register ACME proxy account"""
    data = request.json
    
    if not data or not data.get('email'):
        return error_response('Email is required', 400)
    
    email = data['email']
    
    # Store proxy email in SystemConfig
    proxy_cfg = SystemConfig.query.filter_by(key='acme.proxy_email').first()
    if not proxy_cfg:
        proxy_cfg = SystemConfig(key='acme.proxy_email', description='ACME proxy account email')
        db.session.add(proxy_cfg)
    proxy_cfg.value = email
    db.session.commit()
    
    return success_response(
        data={'registered': True, 'email': email},
        message='Proxy account registered'
    )


@bp.route('/api/v2/acme/proxy/unregister', methods=['POST'])
@require_auth(['write:acme'])
def unregister_proxy_account():
    """Unregister ACME proxy account"""
    proxy_cfg = SystemConfig.query.filter_by(key='acme.proxy_email').first()
    if proxy_cfg:
        db.session.delete(proxy_cfg)
        db.session.commit()
    
    return success_response(
        data={'registered': False},
        message='Proxy account unregistered'
    )


@bp.route('/api/v2/acme/history', methods=['GET'])
@require_auth(['read:acme'])
def get_acme_history():
    """Get history of certificates issued via ACME
    
    Query params:
        page: Page number (default: 1)
        per_page: Items per page (default: 50, max: 100)
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)
    
    # Get certificates with source='acme'
    query = Certificate.query.filter_by(source='acme').order_by(
        Certificate.created_at.desc()
    )
    total = query.count()
    certs = query.offset((page - 1) * per_page).limit(per_page).all()
    
    # Batch fetch CAs and orders to avoid N+1
    cert_ids = [c.id for c in certs]
    ca_refs = [c.caref for c in certs if c.caref]
    
    # Fetch all CAs at once
    cas_map = {}
    if ca_refs:
        cas = CA.query.filter(CA.refid.in_(ca_refs)).all()
        cas_map = {ca.refid: ca.common_name for ca in cas}
    
    # Fetch all orders at once
    orders_map = {}
    if cert_ids:
        orders = AcmeOrder.query.filter(AcmeOrder.certificate_id.in_(cert_ids)).all()
        for order in orders:
            account = order.account
            orders_map[order.certificate_id] = {
                'order_id': order.order_id,
                'account': account.account_id if account else 'Unknown',
                'status': order.status
            }
    
    data = []
    for cert in certs:
        data.append({
            'id': cert.id,
            'refid': cert.refid,
            'common_name': cert.subject_cn or cert.descr,
            'serial': cert.serial_number,
            'issuer': cas_map.get(cert.caref) if cert.caref else None,
            'valid_from': cert.valid_from.isoformat() if cert.valid_from else None,
            'valid_to': cert.valid_to.isoformat() if cert.valid_to else None,
            'revoked': cert.revoked,
            'created_at': cert.created_at.isoformat() if cert.created_at else None,
            'order': orders_map.get(cert.id)
        })
    
    return success_response(
        data=data,
        meta={'total': total, 'page': page, 'per_page': per_page}
    )
