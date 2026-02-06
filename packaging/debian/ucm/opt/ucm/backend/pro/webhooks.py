"""
Webhook API - UCM Pro
Endpoints for managing webhook configurations.
"""
from flask import Blueprint, request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db
from services.webhook_service import WebhookEndpoint, WebhookService
import json
import secrets

bp = Blueprint('webhooks_pro', __name__)


@bp.route('/api/v2/webhooks', methods=['GET'])
@require_auth(['read:settings'])
def list_webhooks():
    """List all webhook endpoints"""
    endpoints = WebhookEndpoint.query.all()
    return success_response(data=[e.to_dict() for e in endpoints])


@bp.route('/api/v2/webhooks/<int:endpoint_id>', methods=['GET'])
@require_auth(['read:settings'])
def get_webhook(endpoint_id):
    """Get webhook endpoint details"""
    endpoint = WebhookEndpoint.query.get_or_404(endpoint_id)
    return success_response(data=endpoint.to_dict())


@bp.route('/api/v2/webhooks', methods=['POST'])
@require_auth(['write:settings'])
def create_webhook():
    """Create new webhook endpoint"""
    data = request.get_json()
    
    if not data.get('name'):
        return error_response("Webhook name is required", 400)
    if not data.get('url'):
        return error_response("Webhook URL is required", 400)
    
    # Validate URL format
    url = data['url']
    if not url.startswith(('http://', 'https://')):
        return error_response("URL must start with http:// or https://", 400)
    
    endpoint = WebhookEndpoint(
        name=data['name'],
        url=url,
        secret=data.get('secret') or secrets.token_urlsafe(32),
        events=json.dumps(data.get('events', ['*'])),
        ca_filter=data.get('ca_filter'),
        enabled=data.get('enabled', True),
        custom_headers=json.dumps(data.get('custom_headers', {}))
    )
    
    db.session.add(endpoint)
    db.session.commit()
    
    return success_response(data=endpoint.to_dict(), message="Webhook created")


@bp.route('/api/v2/webhooks/<int:endpoint_id>', methods=['PUT'])
@require_auth(['write:settings'])
def update_webhook(endpoint_id):
    """Update webhook endpoint"""
    endpoint = WebhookEndpoint.query.get_or_404(endpoint_id)
    data = request.get_json()
    
    if 'name' in data:
        endpoint.name = data['name']
    if 'url' in data:
        url = data['url']
        if not url.startswith(('http://', 'https://')):
            return error_response("URL must start with http:// or https://", 400)
        endpoint.url = url
    if 'secret' in data:
        endpoint.secret = data['secret']
    if 'events' in data:
        endpoint.events = json.dumps(data['events'])
    if 'ca_filter' in data:
        endpoint.ca_filter = data['ca_filter']
    if 'enabled' in data:
        endpoint.enabled = data['enabled']
    if 'custom_headers' in data:
        endpoint.custom_headers = json.dumps(data['custom_headers'])
    
    db.session.commit()
    return success_response(data=endpoint.to_dict(), message="Webhook updated")


@bp.route('/api/v2/webhooks/<int:endpoint_id>', methods=['DELETE'])
@require_auth(['write:settings'])
def delete_webhook(endpoint_id):
    """Delete webhook endpoint"""
    endpoint = WebhookEndpoint.query.get_or_404(endpoint_id)
    db.session.delete(endpoint)
    db.session.commit()
    return success_response(message="Webhook deleted")


@bp.route('/api/v2/webhooks/<int:endpoint_id>/toggle', methods=['POST'])
@require_auth(['write:settings'])
def toggle_webhook(endpoint_id):
    """Enable/disable webhook endpoint"""
    endpoint = WebhookEndpoint.query.get_or_404(endpoint_id)
    endpoint.enabled = not endpoint.enabled
    db.session.commit()
    
    status = "enabled" if endpoint.enabled else "disabled"
    return success_response(data=endpoint.to_dict(), message=f"Webhook {status}")


@bp.route('/api/v2/webhooks/<int:endpoint_id>/test', methods=['POST'])
@require_auth(['write:settings'])
def test_webhook(endpoint_id):
    """Send test event to webhook endpoint"""
    success, message = WebhookService.test_endpoint(endpoint_id)
    
    if success:
        return success_response(message=message)
    else:
        return error_response(message, 400)


@bp.route('/api/v2/webhooks/<int:endpoint_id>/regenerate-secret', methods=['POST'])
@require_auth(['write:settings'])
def regenerate_secret(endpoint_id):
    """Regenerate webhook secret"""
    endpoint = WebhookEndpoint.query.get_or_404(endpoint_id)
    endpoint.secret = secrets.token_urlsafe(32)
    db.session.commit()
    
    return success_response(
        data={'secret': endpoint.secret},
        message="Secret regenerated"
    )


@bp.route('/api/v2/webhooks/events', methods=['GET'])
@require_auth(['read:settings'])
def list_events():
    """List available webhook event types"""
    return success_response(data={
        'events': WebhookService.ALL_EVENTS,
        'descriptions': {
            'certificate.issued': 'When a new certificate is issued',
            'certificate.revoked': 'When a certificate is revoked',
            'certificate.renewed': 'When a certificate is auto-renewed',
            'certificate.expiring': 'When a certificate is about to expire',
            'ca.created': 'When a new CA is created',
            'ca.updated': 'When a CA is updated',
            'csr.submitted': 'When a CSR is submitted',
            'csr.approved': 'When a CSR is approved',
            'csr.rejected': 'When a CSR is rejected',
        }
    })
