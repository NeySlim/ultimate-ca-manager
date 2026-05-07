"""
Webhook API - UCM
Endpoints for managing webhook configurations.
"""
from flask import Blueprint, request
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from utils.ssrf_protection import validate_url_not_cloud_metadata
from utils.encryption import encrypt_if_needed
from models import db
from services.webhook_service import WebhookEndpoint, WebhookService
import json
import logging

logger = logging.getLogger(__name__)
import secrets

bp = Blueprint('webhooks', __name__)


# Forbidden custom headers — would let the operator override security-critical
# fields (Stripe-style attack: replace HMAC, inject Authorization, MITM via Host).
_FORBIDDEN_HEADER_PREFIXES = ('x-ucm-',)
_FORBIDDEN_HEADERS = {
    'content-type', 'user-agent', 'host', 'authorization',
    'cookie', 'content-length',
}
_MAX_EVENTS = 64
_VALID_EVENTS_LITERAL_STAR = '*'


def _validate_events(events):
    if not isinstance(events, list):
        return False, 'Events must be an array'
    if len(events) > _MAX_EVENTS:
        return False, f'Too many events (max {_MAX_EVENTS})'
    valid = set(WebhookService.ALL_EVENTS) | {_VALID_EVENTS_LITERAL_STAR}
    for ev in events:
        if not isinstance(ev, str):
            return False, 'Event names must be strings'
        if ev not in valid:
            return False, f'Unknown event: {ev}'
    return True, None


def _validate_custom_headers(headers):
    if headers is None or headers == {}:
        return True, None
    if not isinstance(headers, dict):
        return False, 'Custom headers must be an object'
    for k, v in headers.items():
        if not isinstance(k, str) or not isinstance(v, str):
            return False, 'Header names and values must be strings'
        kl = k.lower()
        if kl in _FORBIDDEN_HEADERS or any(kl.startswith(p) for p in _FORBIDDEN_HEADER_PREFIXES):
            return False, f'Header "{k}" is reserved and cannot be overridden'
    return True, None


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
    
    # Narrow SSRF guard — UCM is on-prem, internal webhooks (Slack/Mattermost/
    # Teams/Jenkins/Gitea/Home Assistant on RFC1918) are a primary use case.
    # Only block cloud metadata endpoints + loopback (high-impact targets).
    try:
        validate_url_not_cloud_metadata(url)
    except ValueError as e:
        logger.warning(f"Webhook SSRF blocked: {e}")
        return error_response("Webhook URL must not target cloud metadata services or loopback", 400)
    
    events = data.get('events', ['*'])
    ok, err = _validate_events(events)
    if not ok:
        return error_response(err, 400)
    custom_headers = data.get('custom_headers') or {}
    ok, err = _validate_custom_headers(custom_headers)
    if not ok:
        return error_response(err, 400)

    # Reject empty-string secret (would silently disable HMAC)
    secret_in = data.get('secret')
    if secret_in is not None and not isinstance(secret_in, str):
        return error_response('Secret must be a string', 400)
    if isinstance(secret_in, str) and not secret_in.strip():
        return error_response('Secret cannot be empty (omit field for auto-generation)', 400)
    secret_value = secret_in or secrets.token_urlsafe(32)

    endpoint = WebhookEndpoint(
        name=data['name'],
        url=url,
        secret=encrypt_if_needed(secret_value),
        events=json.dumps(events),
        ca_filter=data.get('ca_filter'),
        enabled=data.get('enabled', True),
        custom_headers=json.dumps(custom_headers)
    )
    
    db.session.add(endpoint)
    ok, _err = safe_commit(logger, "Failed to create webhook")
    if not ok:
        return _err
    
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
        try:
            validate_url_not_cloud_metadata(url)
        except ValueError as e:
            logger.warning(f"Webhook SSRF blocked: {e}")
            return error_response("Webhook URL must not target cloud metadata services or loopback", 400)
        endpoint.url = url
    if 'secret' in data:
        secret_in = data['secret']
        if not isinstance(secret_in, str) or not secret_in.strip():
            return error_response('Secret must be a non-empty string', 400)
        endpoint.secret = encrypt_if_needed(secret_in)
    if 'events' in data:
        ok, err = _validate_events(data['events'])
        if not ok:
            return error_response(err, 400)
        endpoint.events = json.dumps(data['events'])
    if 'ca_filter' in data:
        endpoint.ca_filter = data['ca_filter']
    if 'enabled' in data:
        endpoint.enabled = data['enabled']
    if 'custom_headers' in data:
        ok, err = _validate_custom_headers(data['custom_headers'])
        if not ok:
            return error_response(err, 400)
        endpoint.custom_headers = json.dumps(data['custom_headers'] or {})
    
    ok, _err = safe_commit(logger, "Failed to update webhook")
    if not ok:
        return _err
    return success_response(data=endpoint.to_dict(), message="Webhook updated")


@bp.route('/api/v2/webhooks/<int:endpoint_id>', methods=['DELETE'])
@require_auth(['delete:settings'])
def delete_webhook(endpoint_id):
    """Delete webhook endpoint"""
    endpoint = WebhookEndpoint.query.get_or_404(endpoint_id)
    db.session.delete(endpoint)
    ok, _err = safe_commit(logger, "Failed to delete webhook")
    if not ok:
        return _err
    return success_response(message="Webhook deleted")


@bp.route('/api/v2/webhooks/<int:endpoint_id>/toggle', methods=['POST'])
@require_auth(['write:settings'])
def toggle_webhook(endpoint_id):
    """Enable/disable webhook endpoint"""
    endpoint = WebhookEndpoint.query.get_or_404(endpoint_id)
    endpoint.enabled = not endpoint.enabled
    ok, _err = safe_commit(logger, "Failed to toggle webhook")
    if not ok:
        return _err
    
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
    new_secret = secrets.token_urlsafe(32)
    endpoint.secret = encrypt_if_needed(new_secret)
    ok, _err = safe_commit(logger, "Failed to regenerate webhook secret")
    if not ok:
        return _err

    # Return plaintext one time so the operator can configure their receiver
    return success_response(
        data={'secret': new_secret},
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
