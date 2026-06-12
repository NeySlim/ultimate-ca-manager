"""
Webhook API - UCM
Endpoints for managing webhook configurations.
"""
import json
import logging
import re
import secrets

from flask import Blueprint, g, request
from auth.unified import require_auth
from models import db
from services.audit_service import AuditService
from services.webhook_service import WebhookEndpoint, WebhookService
from utils.db_transaction import safe_commit
from utils.datetime_utils import utc_now
from utils.decorators import require_json_body
from utils.encryption import encrypt_if_needed
from utils.response import created_response, error_response, no_content_response, success_response
from utils.ssrf_protection import validate_url_not_cloud_metadata

logger = logging.getLogger(__name__)

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

# Auth validation constants
_VALID_AUTH_TYPES = {'none', 'bearer', 'basic', 'api_key', 'custom'}
_MAX_AUTH_TOKEN_BYTES = 8192
_MAX_AUTH_USERNAME_LEN = 255
_MAX_AUTH_HEADER_NAME_LEN = 100
# RFC 7230 token characters
_AUTH_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+\-.^_`|~]+$")


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


def _validate_auth(payload, *, is_create, endpoint=None):
    """Validate auth_* fields with PUT semantics.

    On create (is_create=True): auth_type defaults to 'none' if absent.
    On update (is_create=False): absent fields are left unchanged.
      - field = ""  → 400 (must use null to clear)
      - field = null → clear (None / 'none' for auth_type)

    Returns (fields_to_apply: dict, error: str | None).
    fields_to_apply maps column names to values to set on the endpoint.
    auth_token in the returned dict is the plaintext value (None = clear).
    """
    fields = {}
    auth_type_explicit = 'auth_type' in payload

    # ── auth_type ──────────────────────────────────────────────────────────
    if auth_type_explicit:
        at_raw = payload['auth_type']
        if at_raw is None:
            auth_type = 'none'
        elif at_raw == '':
            return {}, "auth_type cannot be empty (use null to clear)"
        elif not isinstance(at_raw, str):
            return {}, "auth_type must be a string"
        else:
            auth_type = at_raw
        if auth_type not in _VALID_AUTH_TYPES:
            return {}, "Invalid auth_type"
        fields['auth_type'] = auth_type
    elif is_create:
        auth_type = 'none'
        fields['auth_type'] = 'none'
    else:
        # Absent on PUT — keep current value; resolve for type-specific checks
        auth_type = (endpoint.auth_type or 'none') if endpoint else 'none'

    # ── auth_token ─────────────────────────────────────────────────────────
    if 'auth_token' in payload:
        tok = payload['auth_token']
        if tok == '':
            return {}, "Auth token cannot be empty (use null to clear)"
        if tok is not None:
            if not isinstance(tok, str):
                return {}, "auth_token must be a string"
            if len(tok.encode('utf-8')) > _MAX_AUTH_TOKEN_BYTES:
                return {}, f"auth_token exceeds {_MAX_AUTH_TOKEN_BYTES}-byte limit"
        fields['auth_token'] = tok  # None means clear

    # ── auth_username ──────────────────────────────────────────────────────
    if 'auth_username' in payload:
        u = payload['auth_username']
        if u == '':
            return {}, "auth_username cannot be empty (use null to clear)"
        if u is not None:
            if not isinstance(u, str):
                return {}, "auth_username must be a string"
            if len(u) > _MAX_AUTH_USERNAME_LEN:
                return {}, f"auth_username exceeds {_MAX_AUTH_USERNAME_LEN} characters"
            if ':' in u:
                return {}, "auth_username must not contain ':'"
        fields['auth_username'] = u

    # ── auth_header_name ───────────────────────────────────────────────────
    if 'auth_header_name' in payload:
        h = payload['auth_header_name']
        if h == '':
            return {}, "auth_header_name cannot be empty (use null to clear)"
        if h is not None:
            if not isinstance(h, str):
                return {}, "auth_header_name must be a string"
            if len(h) > _MAX_AUTH_HEADER_NAME_LEN:
                return {}, f"auth_header_name exceeds {_MAX_AUTH_HEADER_NAME_LEN} characters"
            if not _AUTH_HEADER_NAME_RE.match(h):
                return {}, "auth_header_name contains invalid characters (RFC 7230 token required)"
        fields['auth_header_name'] = h

    # ── type-specific required-field checks ────────────────────────────────
    # Run when auth_type is explicitly set (or on create) so we validate the
    # final state that will be persisted.
    if auth_type_explicit or is_create:
        def _has_token():
            if 'auth_token' in fields:
                return fields['auth_token'] is not None
            return bool(endpoint._auth_token) if endpoint else False

        def _get_username():
            if 'auth_username' in fields:
                return fields['auth_username']
            return endpoint.auth_username if endpoint else None

        def _get_header_name():
            if 'auth_header_name' in fields:
                return fields['auth_header_name']
            return endpoint.auth_header_name if endpoint else None

        if auth_type == 'none':
            # Clear all related fields unless explicitly provided
            fields.setdefault('auth_token', None)
            fields.setdefault('auth_username', None)
            fields.setdefault('auth_header_name', None)

        elif auth_type == 'bearer':
            if not _has_token():
                return {}, "auth_token is required for bearer auth"
            fields['auth_username'] = None
            fields['auth_header_name'] = None

        elif auth_type == 'basic':
            if not _has_token():
                return {}, "auth_token (password) is required for basic auth"
            if not _get_username():
                return {}, "auth_username is required for basic auth"
            fields['auth_header_name'] = None

        elif auth_type == 'api_key':
            if not _has_token():
                return {}, "auth_token is required for api_key auth"
            hn = _get_header_name()
            if not hn:
                return {}, "auth_header_name is required for api_key auth"
            if hn.lower() == 'authorization':
                return {}, "Use auth_type=custom for the Authorization header"
            fields['auth_username'] = None

        elif auth_type == 'custom':
            if not _has_token():
                return {}, "auth_token is required for custom auth"
            if not _get_header_name():
                return {}, "auth_header_name is required for custom auth"
            fields['auth_username'] = None

    else:
        # auth_type not changing on PUT: still enforce api_key header restriction
        # if the operator is updating auth_header_name on an existing api_key endpoint.
        if auth_type == 'api_key' and 'auth_header_name' in fields:
            hn = fields['auth_header_name']
            if hn and hn.lower() == 'authorization':
                return {}, "Use auth_type=custom for the Authorization header"

    return fields, None


def _apply_auth_fields(endpoint, fields):
    """Write validated auth fields onto the endpoint model instance."""
    for key, value in fields.items():
        if key == 'auth_token':
            endpoint.auth_token = value  # uses encrypted property setter
        else:
            setattr(endpoint, key, value)


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
@require_json_body
def create_webhook():
    """Create new webhook endpoint"""
    data = g.json_data

    if not data.get('name'):
        return error_response("Webhook name is required", 400)
    if not data.get('url'):
        return error_response("Webhook URL is required", 400)

    url = data['url']
    if not url.startswith(('http://', 'https://')):
        return error_response("URL must start with http:// or https://", 400)

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

    secret_in = data.get('secret')
    if secret_in is not None and not isinstance(secret_in, str):
        return error_response('Secret must be a string', 400)
    if isinstance(secret_in, str) and not secret_in.strip():
        return error_response('Secret cannot be empty (omit field for auto-generation)', 400)
    secret_value = secret_in or secrets.token_urlsafe(32)

    # Validate auth fields
    auth_fields, auth_err = _validate_auth(data, is_create=True)
    if auth_err:
        return error_response(auth_err, 400)

    endpoint = WebhookEndpoint(
        name=data['name'],
        url=url,
        secret=encrypt_if_needed(secret_value),
        events=json.dumps(events),
        ca_filter=data.get('ca_filter'),
        enabled=data.get('enabled', True),
        custom_headers=json.dumps(custom_headers)
    )
    _apply_auth_fields(endpoint, auth_fields)

    db.session.add(endpoint)
    ok, _err = safe_commit(logger, "Failed to create webhook")
    if not ok:
        return _err

    if endpoint.auth_type and endpoint.auth_type != 'none':
        AuditService.log_action(
            action='webhook.auth_configured',
            resource_type='webhook',
            resource_id=str(endpoint.id),
            resource_name=endpoint.name,
            details=json.dumps({'auth_type': endpoint.auth_type}),
        )

    return created_response(data=endpoint.to_dict(), message="Webhook created")


@bp.route('/api/v2/webhooks/<int:endpoint_id>', methods=['PUT'])
@require_auth(['write:settings'])
@require_json_body
def update_webhook(endpoint_id):
    """Update webhook endpoint"""
    endpoint = WebhookEndpoint.query.get_or_404(endpoint_id)
    data = g.json_data

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

    # Validate auth fields and detect transitions for audit
    prev_auth_type = endpoint.auth_type or 'none'
    prev_token_set = bool(endpoint._auth_token)

    auth_fields, auth_err = _validate_auth(data, is_create=False, endpoint=endpoint)
    if auth_err:
        AuditService.log_action(
            action='webhook.auth_token_invalid',
            resource_type='webhook',
            resource_id=str(endpoint_id),
            resource_name=endpoint.name,
            details=json.dumps({'reason': auth_err, 'auth_type': data.get('auth_type')}),
            success=False,
        )
        return error_response(auth_err, 400)

    _apply_auth_fields(endpoint, auth_fields)
    new_auth_type = endpoint.auth_type or 'none'

    ok, _err = safe_commit(logger, "Failed to update webhook")
    if not ok:
        return _err

    # Emit audit events for auth transitions
    if prev_auth_type == 'none' and new_auth_type != 'none':
        AuditService.log_action(
            action='webhook.auth_configured',
            resource_type='webhook',
            resource_id=str(endpoint.id),
            resource_name=endpoint.name,
            details=json.dumps({'auth_type': new_auth_type}),
        )
    elif prev_auth_type != 'none' and new_auth_type == 'none':
        AuditService.log_action(
            action='webhook.auth_disabled',
            resource_type='webhook',
            resource_id=str(endpoint.id),
            resource_name=endpoint.name,
            details=json.dumps({'prev_auth_type': prev_auth_type}),
        )
    elif new_auth_type != 'none' and prev_token_set and 'auth_token' in auth_fields and auth_fields['auth_token'] is not None:
        AuditService.log_action(
            action='webhook.auth_token_rotated',
            resource_type='webhook',
            resource_id=str(endpoint.id),
            resource_name=endpoint.name,
            details=json.dumps({'auth_type': new_auth_type}),
        )

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
    return no_content_response()


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


@bp.route('/api/v2/webhooks/<int:endpoint_id>/deliveries', methods=['GET'])
@require_auth(['read:settings'])
def list_deliveries(endpoint_id):
    """Per-endpoint webhook delivery history (newest first), optional status filter."""
    from models import WebhookDelivery
    from utils.pagination import parse_request_pagination, paginate
    WebhookEndpoint.query.get_or_404(endpoint_id)

    page, per_page = parse_request_pagination(default_per_page=25, max_per_page=100)
    query = WebhookDelivery.query.filter_by(endpoint_id=endpoint_id)
    status = request.args.get('status')
    if status in (WebhookDelivery.STATUS_PENDING, WebhookDelivery.STATUS_DELIVERED, WebhookDelivery.STATUS_FAILED):
        query = query.filter_by(status=status)
    query = query.order_by(WebhookDelivery.id.desc())

    result = paginate(query, page, per_page)
    return success_response(data=[d.to_dict() for d in result['items']], meta=result['meta'])


@bp.route('/api/v2/webhooks/<int:endpoint_id>/deliveries/<int:delivery_id>/retry', methods=['POST'])
@require_auth(['write:settings'])
def retry_delivery(endpoint_id, delivery_id):
    """Re-queue a delivery for immediate redelivery."""
    from models import WebhookDelivery
    d = WebhookDelivery.query.filter_by(id=delivery_id, endpoint_id=endpoint_id).first()
    if not d:
        return error_response('Delivery not found', 404)

    d.status = WebhookDelivery.STATUS_PENDING
    d.attempts = 0
    d.max_attempts = WebhookService.DEFAULT_MAX_ATTEMPTS
    d.next_attempt_at = utc_now()
    d.last_error = None
    ok, _err = safe_commit(logger, "Failed to re-queue webhook delivery")
    if not ok:
        return _err
    return success_response(data=d.to_dict(), message="Delivery re-queued")


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
