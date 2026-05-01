"""
Settings - Webhooks CRUD + test routes
"""

from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from utils.ssrf_protection import validate_url_not_cloud_metadata
from models import db, SystemConfig
from services.audit_service import AuditService
from datetime import datetime, timezone
import json
import logging

from . import bp

logger = logging.getLogger(__name__)


# ============================================================================
# Webhooks (stored as JSON in SystemConfig)
# ============================================================================

def get_webhooks():
    """Get webhooks from SystemConfig"""
    config = SystemConfig.query.filter_by(key='webhooks').first()
    if config and config.value:
        try:
            return json.loads(config.value)
        except Exception:
            return []
    return []


def save_webhooks(webhooks):
    """Save webhooks to SystemConfig"""
    config = SystemConfig.query.filter_by(key='webhooks').first()
    if config:
        config.value = json.dumps(webhooks)
    else:
        config = SystemConfig(key='webhooks', value=json.dumps(webhooks))
        db.session.add(config)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to save webhooks: {e}")
        raise


@bp.route('/api/v2/settings/webhooks', methods=['GET'])
@require_auth(['read:settings'])
def list_webhooks():
    """List configured webhooks"""
    webhooks = get_webhooks()
    return success_response(data=webhooks, meta={'total': len(webhooks)})


@bp.route('/api/v2/settings/webhooks', methods=['POST'])
@require_auth(['write:settings'])
def create_webhook():
    """Create webhook"""
    data = request.json

    if not data or not data.get('name'):
        return error_response('Webhook name required', 400)

    if not data.get('url'):
        return error_response('Webhook URL required', 400)

    # Narrow SSRF guard — internal webhooks (Slack/Teams/Mattermost on LAN)
    # are legitimate. Block only cloud metadata + loopback.
    try:
        validate_url_not_cloud_metadata(data['url'])
    except ValueError:
        return error_response('Webhook URL must not target cloud metadata services or loopback', 400)

    if not data.get('events'):
        return error_response('At least one event required', 400)

    # Get existing webhooks
    webhooks = get_webhooks()

    # Generate new ID
    new_id = max([w.get('id', 0) for w in webhooks], default=0) + 1

    new_webhook = {
        'id': new_id,
        'name': data['name'],
        'url': data['url'],
        'events': data['events'],
        'enabled': data.get('enabled', True),
        'created_at': datetime.now(timezone.utc).isoformat()
    }

    webhooks.append(new_webhook)
    save_webhooks(webhooks)

    AuditService.log_action(
        action='webhook_create',
        resource_type='webhook',
        resource_id=str(new_id),
        resource_name=new_webhook['name'],
        details=f'Created webhook: {new_webhook["name"]}',
        success=True
    )

    return created_response(
        data=new_webhook,
        message='Webhook created successfully'
    )


@bp.route('/api/v2/settings/webhooks/<int:webhook_id>', methods=['DELETE'])
@require_auth(['delete:settings'])
def delete_webhook(webhook_id):
    """Delete webhook"""
    webhooks = get_webhooks()
    webhooks = [w for w in webhooks if w.get('id') != webhook_id]
    save_webhooks(webhooks)

    AuditService.log_action(
        action='webhook_delete',
        resource_type='webhook',
        resource_id=str(webhook_id),
        resource_name=f'Webhook {webhook_id}',
        details=f'Deleted webhook {webhook_id}',
        success=True
    )

    return no_content_response()


@bp.route('/api/v2/settings/webhooks/<int:webhook_id>/test', methods=['POST'])
@require_auth(['write:settings'])
def test_webhook(webhook_id):
    """Test webhook by sending a test event"""
    import requests as http_requests

    webhooks = get_webhooks()
    webhook = next((w for w in webhooks if w.get('id') == webhook_id), None)

    if not webhook:
        return error_response('Webhook not found', 404)

    # Re-validate stored URL before sending (defense-in-depth, narrow guard)
    try:
        validate_url_not_cloud_metadata(webhook['url'])
    except ValueError as e:
        logger.warning(f"Blocked test of webhook {webhook_id} — URL targets cloud metadata or loopback: {e}")
        return error_response('Webhook URL targets cloud metadata services or loopback', 400)

    test_payload = {
        'event': 'test',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'data': {'message': 'This is a test webhook from UCM'}
    }

    try:
        response = http_requests.post(
            webhook['url'],
            json=test_payload,
            timeout=10,
            headers={'Content-Type': 'application/json', 'User-Agent': 'UCM-Webhook/2.0'}
        )
        return success_response(
            data={'sent': True, 'status_code': response.status_code},
            message=f'Test webhook sent (status: {response.status_code})'
        )
    except Exception as e:
        logger.error(f"Failed to send test webhook: {e}")
        return error_response('Failed to send webhook', 500)
