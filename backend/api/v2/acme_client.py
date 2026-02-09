"""
ACME Client API Routes
Endpoints for requesting certificates from Let's Encrypt
"""
import json
from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, DnsProvider, AcmeClientOrder, SystemConfig
from services.acme.acme_client_service import AcmeClientService
from services.audit_service import AuditService

bp = Blueprint('acme_client', __name__)


# =============================================================================
# Settings
# =============================================================================

@bp.route('/api/v2/acme/client/settings', methods=['GET'])
@require_auth(['read:acme'])
def get_settings():
    """Get ACME client settings"""
    # Get configured email
    email_cfg = SystemConfig.query.filter_by(key='acme.client.email').first()
    
    # Get default environment
    env_cfg = SystemConfig.query.filter_by(key='acme.client.environment').first()
    
    # Get auto-renewal settings
    renewal_enabled = SystemConfig.query.filter_by(key='acme.client.renewal_enabled').first()
    renewal_days = SystemConfig.query.filter_by(key='acme.client.renewal_days').first()
    
    # Check if accounts exist
    staging_account = SystemConfig.query.filter_by(key='acme.client.staging.account_url').first()
    production_account = SystemConfig.query.filter_by(key='acme.client.production.account_url').first()
    
    return success_response(data={
        'email': email_cfg.value if email_cfg else None,
        'environment': env_cfg.value if env_cfg else 'staging',
        'renewal_enabled': renewal_enabled.value == 'true' if renewal_enabled else True,
        'renewal_days': int(renewal_days.value) if renewal_days else 30,
        'has_staging_account': bool(staging_account),
        'has_production_account': bool(production_account),
    })


@bp.route('/api/v2/acme/client/settings', methods=['PATCH'])
@require_auth(['write:acme'])
def update_settings():
    """Update ACME client settings"""
    data = request.json
    if not data:
        return error_response('Request body required', 400)
    
    updates = []
    
    if 'email' in data:
        _set_config('acme.client.email', data['email'], 'ACME client contact email')
        updates.append('email')
    
    if 'environment' in data:
        if data['environment'] not in ['staging', 'production']:
            return error_response('Environment must be staging or production', 400)
        _set_config('acme.client.environment', data['environment'], 'ACME client environment')
        updates.append('environment')
    
    if 'renewal_enabled' in data:
        _set_config('acme.client.renewal_enabled', 
                   'true' if data['renewal_enabled'] else 'false',
                   'ACME auto-renewal enabled')
        updates.append('renewal_enabled')
    
    if 'renewal_days' in data:
        days = int(data['renewal_days'])
        if days < 1 or days > 60:
            return error_response('Renewal days must be between 1 and 60', 400)
        _set_config('acme.client.renewal_days', str(days), 'ACME renewal days before expiry')
        updates.append('renewal_days')
    
    db.session.commit()
    
    AuditService.log_action(
        action='acme_client_settings_update',
        resource_type='acme_client',
        resource_name='ACME Client Settings',
        details=f'Updated ACME client settings: {", ".join(updates)}' if updates else 'No changes',
        success=True
    )
    
    return success_response(
        message=f'Settings updated: {", ".join(updates)}' if updates else 'No changes'
    )


def _set_config(key: str, value: str, description: str = ''):
    """Helper to set SystemConfig value"""
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value, description=description))


# =============================================================================
# Orders
# =============================================================================

@bp.route('/api/v2/acme/client/orders', methods=['GET'])
@require_auth(['read:acme'])
def list_orders():
    """List all ACME client orders"""
    status = request.args.get('status')
    environment = request.args.get('environment')
    
    query = AcmeClientOrder.query
    
    if status:
        query = query.filter_by(status=status)
    if environment:
        query = query.filter_by(environment=environment)
    
    orders = query.order_by(AcmeClientOrder.created_at.desc()).limit(100).all()
    
    return success_response(data=[o.to_dict() for o in orders])


@bp.route('/api/v2/acme/client/orders/<int:order_id>', methods=['GET'])
@require_auth(['read:acme'])
def get_order(order_id):
    """Get a specific ACME client order"""
    order = AcmeClientOrder.query.get(order_id)
    if not order:
        return error_response('Order not found', 404)
    
    return success_response(data=order.to_dict())


@bp.route('/api/v2/acme/client/request', methods=['POST'])
@require_auth(['write:acme'])
def request_certificate():
    """
    Request a new certificate from Let's Encrypt.
    
    Body:
    {
        "domains": ["example.com", "www.example.com"],
        "email": "admin@example.com",  // Optional, uses default if not set
        "challenge_type": "dns-01",    // dns-01 or http-01
        "environment": "staging",      // staging or production
        "dns_provider_id": 1           // Required for dns-01
    }
    """
    data = request.json
    if not data:
        return error_response('Request body required', 400)
    
    domains = data.get('domains', [])
    if not domains:
        return error_response('At least one domain is required', 400)
    
    # Validate domains
    for domain in domains:
        if not domain or len(domain) < 3:
            return error_response(f'Invalid domain: {domain}', 400)
    
    # Get email (from request or settings)
    email = data.get('email')
    if not email:
        email_cfg = SystemConfig.query.filter_by(key='acme.client.email').first()
        if email_cfg:
            email = email_cfg.value
    if not email:
        return error_response('Email is required. Set it in settings or provide in request.', 400)
    
    # Challenge type
    challenge_type = data.get('challenge_type', 'dns-01')
    if challenge_type not in ['dns-01', 'http-01']:
        return error_response('Challenge type must be dns-01 or http-01', 400)
    
    # Environment
    environment = data.get('environment', 'staging')
    if environment not in ['staging', 'production']:
        return error_response('Environment must be staging or production', 400)
    
    # DNS provider (required for dns-01)
    dns_provider_id = data.get('dns_provider_id')
    if challenge_type == 'dns-01' and dns_provider_id:
        provider = DnsProvider.query.get(dns_provider_id)
        if not provider:
            return error_response('DNS provider not found', 404)
        if not provider.enabled:
            return error_response('DNS provider is disabled', 400)
    
    # Wildcard domains require dns-01
    has_wildcard = any(d.startswith('*.') for d in domains)
    if has_wildcard and challenge_type != 'dns-01':
        return error_response('Wildcard domains require DNS-01 challenge', 400)
    
    # Create order
    try:
        client = AcmeClientService(environment=environment)
        success, message, order = client.create_order(
            domains=domains,
            email=email,
            challenge_type=challenge_type,
            dns_provider_id=dns_provider_id
        )
        
        if not success:
            return error_response(message, 400)
        
        AuditService.log_action(
            action='acme_request',
            resource_type='acme_order',
            resource_id=str(order.id),
            resource_name=', '.join(domains),
            details=f'Requested certificate for {", ".join(domains)} ({environment})',
            success=True
        )
        
        # Set up DNS challenges if using dns-01
        challenge_info = {}
        if challenge_type == 'dns-01':
            _, setup_message, challenge_info = client.setup_dns_challenge(order)
        
        return success_response(
            data={
                'order': order.to_dict(),
                'challenges': challenge_info,
            },
            message=message,
            status=201
        )
        
    except Exception as e:
        return error_response(f'Failed to create order: {str(e)}', 500)


@bp.route('/api/v2/acme/client/orders/<int:order_id>/verify', methods=['POST'])
@require_auth(['write:acme'])
def verify_challenges(order_id):
    """
    Trigger challenge verification for an order.
    
    Body (optional):
    {
        "domain": "example.com"  // Verify specific domain, or all if not specified
    }
    """
    order = AcmeClientOrder.query.get(order_id)
    if not order:
        return error_response('Order not found', 404)
    
    if order.status not in ['pending', 'processing']:
        return error_response(f'Order cannot be verified (status: {order.status})', 400)
    
    data = request.json or {}
    specific_domain = data.get('domain')
    
    try:
        client = AcmeClientService(environment=order.environment)
        
        results = {}
        challenges = order.challenges_dict
        
        domains_to_verify = [specific_domain] if specific_domain else list(challenges.keys())
        
        for domain in domains_to_verify:
            if domain not in challenges:
                results[domain] = {'success': False, 'message': 'Domain not in order'}
                continue
            
            success, message = client.verify_challenge(order, domain)
            results[domain] = {'success': success, 'message': message}
        
        # Update order status
        order.status = 'validating'
        db.session.commit()
        
        all_success = all(r['success'] for r in results.values())
        
        return success_response(
            data={
                'results': results,
                'order': order.to_dict()
            },
            message='Challenges submitted for verification' if all_success else 'Some challenges failed'
        )
        
    except Exception as e:
        return error_response(f'Verification failed: {str(e)}', 500)


@bp.route('/api/v2/acme/client/orders/<int:order_id>/status', methods=['GET'])
@require_auth(['read:acme'])
def check_order_status(order_id):
    """Check current order status from ACME server"""
    order = AcmeClientOrder.query.get(order_id)
    if not order:
        return error_response('Order not found', 404)
    
    try:
        client = AcmeClientService(environment=order.environment)
        status, data = client.check_order_status(order)
        
        return success_response(data={
            'status': status,
            'order': order.to_dict(),
            'acme_data': data
        })
        
    except Exception as e:
        return error_response(f'Status check failed: {str(e)}', 500)


@bp.route('/api/v2/acme/client/orders/<int:order_id>/finalize', methods=['POST'])
@require_auth(['write:acme'])
def finalize_order(order_id):
    """Finalize order and obtain certificate"""
    order = AcmeClientOrder.query.get(order_id)
    if not order:
        return error_response('Order not found', 404)
    
    if order.status == 'issued':
        return error_response('Order already issued', 400)
    
    try:
        client = AcmeClientService(environment=order.environment)
        success, message, cert_id = client.finalize_order(order)
        
        if success:
            # Clean up DNS records
            client.cleanup_dns_challenge(order)
            
            AuditService.log_action(
                action='acme_finalize',
                resource_type='acme_order',
                resource_id=str(order_id),
                resource_name=f'Order {order_id}',
                details=f'Finalized ACME order {order_id}, certificate ID: {cert_id}',
                success=True
            )
            
            return success_response(
                data={
                    'order': order.to_dict(),
                    'certificate_id': cert_id
                },
                message=message
            )
        else:
            return error_response(message, 400)
            
    except Exception as e:
        return error_response(f'Finalization failed: {str(e)}', 500)


@bp.route('/api/v2/acme/client/orders/<int:order_id>', methods=['DELETE'])
@require_auth(['write:acme'])
def cancel_order(order_id):
    """Cancel/delete an order"""
    order = AcmeClientOrder.query.get(order_id)
    if not order:
        return error_response('Order not found', 404)
    
    # Clean up DNS if needed
    if order.challenge_type == 'dns-01' and order.dns_provider_id:
        try:
            client = AcmeClientService(environment=order.environment)
            client.cleanup_dns_challenge(order)
        except Exception:
            pass  # Best effort cleanup
    
    order_domains = ', '.join([d.get('value', '') for d in (order.identifiers_list if hasattr(order, 'identifiers_list') else [])]) or f'Order {order_id}'
    db.session.delete(order)
    db.session.commit()
    
    AuditService.log_action(
        action='acme_order_cancel',
        resource_type='acme_order',
        resource_id=str(order_id),
        resource_name=order_domains,
        details=f'Cancelled/deleted ACME order {order_id}',
        success=True
    )
    
    return success_response(message='Order deleted')


@bp.route('/api/v2/acme/client/orders/<int:order_id>/renew', methods=['POST'])
@require_auth(['write:acme'])
def renew_order(order_id):
    """Manually trigger renewal for an order"""
    order = AcmeClientOrder.query.get(order_id)
    if not order:
        return error_response('Order not found', 404)
    
    if order.status not in ('valid', 'issued'):
        return error_response('Only valid/issued orders can be renewed', 400)
    
    try:
        from services.acme_renewal_service import renew_certificate
        
        success, message = renew_certificate(order)
        
        if success:
            AuditService.log_action(
                action='acme_renew',
                resource_type='acme_order',
                resource_id=str(order_id),
                resource_name=f'Order {order_id}',
                details=f'Renewed ACME order {order_id}',
                success=True
            )
            return success_response(
                data={'order': order.to_dict()},
                message=message
            )
        else:
            return error_response(message, 400)
            
    except Exception as e:
        return error_response(f'Renewal failed: {str(e)}', 500)


# =============================================================================
# Account Management
# =============================================================================

@bp.route('/api/v2/acme/client/account', methods=['POST'])
@require_auth(['write:acme'])
def register_account():
    """
    Register ACME account with Let's Encrypt.
    
    Body:
    {
        "email": "admin@example.com",
        "environment": "staging"  // or "production"
    }
    """
    data = request.json
    if not data:
        return error_response('Request body required', 400)
    
    email = data.get('email')
    if not email:
        return error_response('Email is required', 400)
    
    environment = data.get('environment', 'staging')
    if environment not in ['staging', 'production']:
        return error_response('Environment must be staging or production', 400)
    
    try:
        client = AcmeClientService(environment=environment)
        success, message, account_url = client.register_account(email)
        
        if success:
            # Save email as default
            _set_config('acme.client.email', email, 'ACME client contact email')
            db.session.commit()
            
            AuditService.log_action(
                action='acme_account_register',
                resource_type='acme_account',
                resource_name=email,
                details=f'Registered ACME account for {email} ({environment})',
                success=True
            )
            
            return success_response(
                data={'account_url': account_url},
                message=message
            )
        else:
            return error_response(message, 400)
            
    except Exception as e:
        return error_response(f'Registration failed: {str(e)}', 500)
