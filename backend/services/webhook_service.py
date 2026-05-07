"""
Webhook Service - UCM
Sends HTTP notifications for certificate lifecycle events.
"""
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
        }


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
            
            # Send webhook
            WebhookService._send_webhook(endpoint, event_type, payload)
    
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
                endpoint.last_success = utc_now()
                endpoint.failure_count = 0
                logger.info(f"Webhook sent to {endpoint.name}: {event_type}")
            else:
                endpoint.last_failure = utc_now()
                endpoint.failure_count += 1
                logger.warning(f"Webhook failed for {endpoint.name}: {response.status_code}")
            
            db.session.commit()
            
        except requests.RequestException as e:
            endpoint.last_failure = utc_now()
            endpoint.failure_count += 1
            db.session.commit()
            logger.error(f"Webhook error for {endpoint.name}: {e}")
        except ValueError as e:
            # Raised by safe_request_post when the URL targets cloud
            # metadata or loopback, or fails DNS resolution.
            endpoint.last_failure = utc_now()
            endpoint.failure_count += 1
            db.session.commit()
            logger.warning(f"Webhook URL rejected for {endpoint.name}: {e}")
        except Exception as e:
            logger.error(f"Unexpected webhook error: {e}")
    
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
