"""
Webhook Service - UCM
Sends HTTP notifications for certificate lifecycle events.
"""
import base64
from datetime import datetime
from models import db, SystemConfig
from utils.encryption import decrypt_if_needed
import requests
import json
import hmac
import hashlib
import logging
from utils.datetime_utils import utc_now, utc_isoformat

logger = logging.getLogger(__name__)


# Headers that the operator-supplied custom_headers MUST NOT override
# (defence in depth — the API layer already filters these on write).
_RESERVED_HEADER_KEYS = {
    'content-type', 'user-agent', 'host', 'authorization',
    'cookie', 'content-length',
}
_RESERVED_HEADER_PREFIXES = ('x-ucm-',)


def _safe_custom_headers(custom: dict) -> dict:
    """Strip any reserved/security-critical headers from operator input."""
    if not isinstance(custom, dict):
        return {}
    out = {}
    for k, v in custom.items():
        if not isinstance(k, str):
            continue
        kl = k.lower()
        if kl in _RESERVED_HEADER_KEYS:
            continue
        if any(kl.startswith(p) for p in _RESERVED_HEADER_PREFIXES):
            continue
        out[k] = v
    return out


class WebhookEndpoint(db.Model):
    """Webhook endpoint configuration"""
    __tablename__ = 'webhook_endpoints'

    VALID_AUTH_TYPES = ('none', 'bearer', 'basic', 'api_key', 'custom')

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    secret = db.Column(db.String(255))  # For HMAC signature

    # Events to send
    events = db.Column(db.Text, default='[]')  # JSON array of event types

    # Filtering
    ca_filter = db.Column(db.String(100))  # Only for specific CA refid

    # Status
    enabled = db.Column(db.Boolean, default=True)
    last_success = db.Column(db.DateTime)
    last_failure = db.Column(db.DateTime)
    failure_count = db.Column(db.Integer, default=0)

    # Headers (JSON)
    custom_headers = db.Column(db.Text, default='{}')

    created_at = db.Column(db.DateTime, default=utc_now)

    # Auth fields (migration 036)
    auth_type = db.Column(db.String(20), nullable=False, default='none')
    _auth_token = db.Column(db.Text, nullable=True)
    auth_username = db.Column(db.String(255), nullable=True)
    auth_header_name = db.Column(db.String(100), nullable=True)

    @property
    def auth_token(self):
        if not self._auth_token:
            return None
        try:
            from utils.encryption import decrypt_if_needed
            return decrypt_if_needed(self._auth_token)
        except Exception:
            logger.error(f"Failed to decrypt auth_token for webhook {self.id}")
            return self._auth_token

    @auth_token.setter
    def auth_token(self, value):
        if not value:
            self._auth_token = None
            return
        try:
            from utils.encryption import encrypt_if_needed
            self._auth_token = encrypt_if_needed(value)
        except Exception:
            logger.error(f"Failed to encrypt auth_token for webhook {self.id}")
            self._auth_token = value

    def get_events(self):
        try:
            return json.loads(self.events) if self.events else []
        except Exception:
            return []

    def get_headers(self):
        try:
            return json.loads(self.custom_headers) if self.custom_headers else {}
        except Exception:
            return {}

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'events': self.get_events(),
            'ca_filter': self.ca_filter,
            'enabled': self.enabled,
            'last_success': utc_isoformat(self.last_success),
            'last_failure': utc_isoformat(self.last_failure),
            'failure_count': self.failure_count,
            'created_at': utc_isoformat(self.created_at),
            # Auth fields — token is NEVER included, only the boolean sentinel
            'auth_type': self.auth_type or 'none',
            'auth_token_set': bool(self._auth_token),
            'auth_username': self.auth_username,
            'auth_header_name': self.auth_header_name,
        }


_MAX_AUTH_TOKEN_BYTES = 8192


def _build_auth_header(webhook) -> dict:
    """Return dict of headers to merge into the outbound request.

    Returns {} for auth_type='none' or any misconfiguration (fail open
    from a transport perspective — the receiver will reject the request
    if auth is required, making the misconfiguration visible in logs).
    Never logs header *values*.
    """
    auth_type = (webhook.auth_type or 'none').strip().lower()

    if auth_type == 'none':
        return {}

    if auth_type not in WebhookEndpoint.VALID_AUTH_TYPES:
        logger.error(f"Webhook {getattr(webhook, 'id', '?')}: unknown auth_type '{auth_type}'")
        return {}

    token = webhook.auth_token
    if token and len(token.encode('utf-8')) > _MAX_AUTH_TOKEN_BYTES:
        logger.error(
            f"Webhook {getattr(webhook, 'id', '?')}: auth_token exceeds "
            f"{_MAX_AUTH_TOKEN_BYTES}-byte cap — dropping auth header"
        )
        return {}

    if auth_type == 'bearer':
        if not token:
            logger.error(
                f"Webhook {getattr(webhook, 'id', '?')}: bearer auth_type but no token stored"
            )
            return {}
        return {'Authorization': f'Bearer {token}'}

    if auth_type == 'basic':
        username = webhook.auth_username or ''
        if not username:
            logger.error(
                f"Webhook {getattr(webhook, 'id', '?')}: basic auth_type but auth_username is empty"
            )
            return {}
        if ':' in username:
            logger.error(
                f"Webhook {getattr(webhook, 'id', '?')}: basic auth_username contains ':' — invalid"
            )
            return {}
        if not token:
            logger.error(
                f"Webhook {getattr(webhook, 'id', '?')}: basic auth_type but no token (password) stored"
            )
            return {}
        encoded = base64.b64encode(f'{username}:{token}'.encode('utf-8')).decode('ascii')
        return {'Authorization': f'Basic {encoded}'}

    if auth_type == 'api_key':
        header_name = webhook.auth_header_name or ''
        if not header_name:
            logger.error(
                f"Webhook {getattr(webhook, 'id', '?')}: api_key auth_type but auth_header_name is empty"
            )
            return {}
        if header_name.lower() == 'authorization':
            logger.error(
                f"Webhook {getattr(webhook, 'id', '?')}: api_key auth_header_name must not be 'Authorization'"
            )
            return {}
        if not token:
            logger.error(
                f"Webhook {getattr(webhook, 'id', '?')}: api_key auth_type but no token stored"
            )
            return {}
        return {header_name: token}

    if auth_type == 'custom':
        header_name = webhook.auth_header_name or ''
        if not header_name:
            logger.error(
                f"Webhook {getattr(webhook, 'id', '?')}: custom auth_type but auth_header_name is empty"
            )
            return {}
        if not token:
            logger.error(
                f"Webhook {getattr(webhook, 'id', '?')}: custom auth_type but no token stored"
            )
            return {}
        return {header_name: token}

    # Unreachable given the membership check above, but defensive
    logger.error(f"Webhook {getattr(webhook, 'id', '?')}: unhandled auth_type '{auth_type}'")
    return {}


class WebhookService:
    """Service for sending webhook notifications"""
    
    # Event types
    CERT_ISSUED = 'certificate.issued'
    CERT_REVOKED = 'certificate.revoked'
    CERT_RENEWED = 'certificate.renewed'
    CERT_EXPIRING = 'certificate.expiring'
    CA_CREATED = 'ca.created'
    CA_UPDATED = 'ca.updated'
    CSR_SUBMITTED = 'csr.submitted'
    CSR_APPROVED = 'csr.approved'
    CSR_REJECTED = 'csr.rejected'
    
    ALL_EVENTS = [
        CERT_ISSUED, CERT_REVOKED, CERT_RENEWED, CERT_EXPIRING,
        CA_CREATED, CA_UPDATED,
        CSR_SUBMITTED, CSR_APPROVED, CSR_REJECTED
    ]
    
    @staticmethod
    def send_event(event_type: str, payload: dict, ca_refid: str = None):
        """
        Send webhook event to all matching endpoints.
        
        Args:
            event_type: One of the event type constants
            payload: Event data to send
            ca_refid: Optional CA filter for targeted webhooks
        """
        # Get matching endpoints
        endpoints = WebhookEndpoint.query.filter_by(enabled=True).all()
        
        for endpoint in endpoints:
            # Check event type subscription
            subscribed_events = endpoint.get_events()
            if event_type not in subscribed_events and '*' not in subscribed_events:
                continue

            # Check CA filter
            if endpoint.ca_filter and ca_refid and endpoint.ca_filter != ca_refid:
                continue

            # One failing endpoint must not break delivery to the others
            # nor the business operation that triggered the event
            try:
                WebhookService._send_webhook(endpoint, event_type, payload)
            except Exception as e:
                logger.error(f"Webhook delivery failed for {endpoint.name}: {e}")
    
    @staticmethod
    def _record_result(endpoint: WebhookEndpoint, success: bool):
        """Persist delivery bookkeeping; never let a commit failure propagate."""
        if success:
            endpoint.last_success = utc_now()
            endpoint.failure_count = 0
        else:
            endpoint.last_failure = utc_now()
            endpoint.failure_count = (endpoint.failure_count or 0) + 1
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Webhook bookkeeping commit failed for {endpoint.name}: {e}")

    @staticmethod
    def _send_webhook(endpoint: WebhookEndpoint, event_type: str, payload: dict):
        """Send single webhook to endpoint"""
        try:
            # Build request body
            body = {
                'event': event_type,
                'timestamp': utc_now().isoformat(),
                'data': payload
            }
            body_json = json.dumps(body, default=str)

            # Custom headers FIRST, so security/identity headers below override
            # whatever the operator put in (defence in depth).
            headers = {}
            headers.update(_safe_custom_headers(endpoint.get_headers()))
            # Auth headers come after custom_headers so they always win,
            # but before UCM identity headers so HMAC signature is last.
            auth_headers = _build_auth_header(endpoint)
            headers.update(auth_headers)
            headers.update({
                'Content-Type': 'application/json',
                'User-Agent': 'UCM-Webhook/2.0',
                'X-UCM-Event': event_type,
            })

            # Add HMAC signature if secret configured
            secret_plain = decrypt_if_needed(endpoint.secret) if endpoint.secret else None
            if secret_plain:
                signature = hmac.new(
                    secret_plain.encode(),
                    body_json.encode(),
                    hashlib.sha256
                ).hexdigest()
                headers['X-UCM-Signature'] = f'sha256={signature}'
            
            # Send request with timeout. UCM is on-prem: LAN/RFC1918/.lan
            # targets MUST keep working. We resolve the hostname once,
            # block only cloud-metadata + loopback, and pin the TCP
            # connection to that IP so a hostile DNS server cannot
            # rebind us to 169.254.169.254 between validation and
            # connect.
            from utils.ssrf_protection import safe_request_post
            response = safe_request_post(
                endpoint.url,
                data=body_json,
                headers=headers,
                timeout=10
            )
            
            if response.ok:
                logger.info(f"Webhook sent to {endpoint.name}: {event_type}")
            else:
                logger.warning(f"Webhook failed for {endpoint.name}: {response.status_code}")
            WebhookService._record_result(endpoint, response.ok)

        except requests.RequestException as e:
            logger.error(f"Webhook error for {endpoint.name}: {e}")
            WebhookService._record_result(endpoint, False)
        except ValueError as e:
            # Raised by safe_request_post when the URL targets cloud
            # metadata or loopback, or fails DNS resolution.
            logger.warning(f"Webhook URL rejected for {endpoint.name}: {e}")
            WebhookService._record_result(endpoint, False)
        except Exception as e:
            logger.error(f"Unexpected webhook error: {e}")
            WebhookService._record_result(endpoint, False)
    
    @staticmethod
    def test_endpoint(endpoint_id: int) -> tuple:
        """
        Test webhook endpoint with a test event.
        
        Returns:
            (success: bool, message: str)
        """
        endpoint = WebhookEndpoint.query.get(endpoint_id)
        if not endpoint:
            return False, "Endpoint not found"
        
        test_payload = {
            'message': 'This is a test webhook from UCM',
            'endpoint_name': endpoint.name,
            'test_timestamp': utc_now().isoformat()
        }
        
        try:
            body = {
                'event': 'test',
                'timestamp': utc_now().isoformat(),
                'data': test_payload
            }
            body_json = json.dumps(body)

            headers = {}
            headers.update(_safe_custom_headers(endpoint.get_headers()))
            auth_headers = _build_auth_header(endpoint)
            headers.update(auth_headers)
            headers.update({
                'Content-Type': 'application/json',
                'User-Agent': 'UCM-Webhook/2.0',
                'X-UCM-Event': 'test',
            })

            secret_plain = decrypt_if_needed(endpoint.secret) if endpoint.secret else None
            if secret_plain:
                signature = hmac.new(
                    secret_plain.encode(),
                    body_json.encode(),
                    hashlib.sha256
                ).hexdigest()
                headers['X-UCM-Signature'] = f'sha256={signature}'
            
            from utils.ssrf_protection import safe_request_post
            response = safe_request_post(
                endpoint.url,
                data=body_json,
                headers=headers,
                timeout=10
            )
            
            if response.ok:
                return True, f"Success: {response.status_code}"
            else:
                return False, f"Failed: {response.status_code} {response.text[:200]}"
                
        except requests.RequestException as e:
            return False, f"Request error: {str(e)}"
        except ValueError as e:
            return False, f"URL rejected: {str(e)}"
        except Exception as e:
            return False, f"Error: {str(e)}"


# Helper functions for triggering webhooks from other services
def trigger_cert_issued(cert: dict, ca_refid: str = None):
    """Trigger webhook when certificate is issued"""
    WebhookService.send_event(
        WebhookService.CERT_ISSUED,
        {'certificate': cert},
        ca_refid
    )


def trigger_cert_revoked(cert: dict, reason: str = None, ca_refid: str = None):
    """Trigger webhook when certificate is revoked"""
    WebhookService.send_event(
        WebhookService.CERT_REVOKED,
        {'certificate': cert, 'reason': reason},
        ca_refid
    )
