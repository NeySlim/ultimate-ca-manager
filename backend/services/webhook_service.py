"""
Webhook Service - UCM
Sends HTTP notifications for certificate lifecycle events.
"""
import base64
from datetime import datetime, timedelta
from models import db, SystemConfig
from utils.encryption import decrypt_if_needed
import requests
import json
import hmac
import hashlib
import logging
from utils.datetime_utils import utc_now, utc_isoformat

logger = logging.getLogger(__name__)


def _safe_commit():
    """Commit, rolling back (never raising) on failure."""
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Webhook delivery commit failed: {e}")


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
    
    # Event types — certificate lifecycle
    CERT_ISSUED = 'certificate.issued'
    CERT_REVOKED = 'certificate.revoked'
    CERT_RENEWED = 'certificate.renewed'
    CERT_EXPIRING = 'certificate.expiring'
    CERT_EXPIRED = 'certificate.expired'
    CERT_IMPORTED = 'certificate.imported'
    CERT_DELETED = 'certificate.deleted'
    # CA lifecycle
    CA_CREATED = 'ca.created'
    CA_UPDATED = 'ca.updated'
    CA_DELETED = 'ca.deleted'
    # CSR / approval workflow
    CSR_SUBMITTED = 'csr.submitted'
    CSR_APPROVED = 'csr.approved'
    CSR_REJECTED = 'csr.rejected'
    # Templates
    TEMPLATE_CREATED = 'template.created'
    TEMPLATE_UPDATED = 'template.updated'
    # ACME client
    ACME_PREFLIGHT = 'acme.preflight'

    ALL_EVENTS = [
        CERT_ISSUED, CERT_REVOKED, CERT_RENEWED, CERT_EXPIRING,
        CERT_EXPIRED, CERT_IMPORTED, CERT_DELETED,
        CA_CREATED, CA_UPDATED, CA_DELETED,
        CSR_SUBMITTED, CSR_APPROVED, CSR_REJECTED,
        TEMPLATE_CREATED, TEMPLATE_UPDATED,
        ACME_PREFLIGHT,
    ]

    # Retry policy for asynchronous delivery
    DEFAULT_MAX_ATTEMPTS = 5
    _BACKOFF_BASE_SECONDS = 60      # 1st retry ~1 min
    _BACKOFF_CAP_SECONDS = 3600     # capped at 1 h
    _CLAIM_LEASE_SECONDS = 120      # delivery lease; longer than the POST timeout
                                    # so a crashed claim is reclaimed, not lost (#139)

    @staticmethod
    def send_event(event_type: str, payload: dict, ca_refid: str = None, meta: dict = None):
        """Publish a lifecycle event on the bus (never raises).

        The webhook subscriber turns it into durable, asynchronously-delivered
        WebhookDelivery rows — the triggering operation is never blocked on HTTP.
        """
        from services.events import event_bus
        event_bus.emit(event_type, payload, ca_refid, meta or {})

    @staticmethod
    def enqueue_deliveries(event_type: str, payload: dict, ca_refid: str = None, meta: dict = None):
        """Bus subscriber: queue one delivery per matching, enabled endpoint."""
        from models import WebhookDelivery
        try:
            endpoints = WebhookEndpoint.query.filter_by(enabled=True).all()
        except Exception as e:
            logger.error(f"Webhook enqueue skipped ({event_type}): {e}")
            return

        now = utc_now()
        payload_json = json.dumps(payload, default=str)
        ts = now.isoformat()
        queued = 0
        for endpoint in endpoints:
            subscribed = endpoint.get_events()
            if event_type not in subscribed and '*' not in subscribed:
                continue
            if endpoint.ca_filter and ca_refid and endpoint.ca_filter != ca_refid:
                continue
            db.session.add(WebhookDelivery(
                endpoint_id=endpoint.id,
                event_type=event_type,
                payload=payload_json,
                event_timestamp=ts,
                status=WebhookDelivery.STATUS_PENDING,
                next_attempt_at=now,
                max_attempts=WebhookService.DEFAULT_MAX_ATTEMPTS,
            ))
            queued += 1
        if not queued:
            return
        # This subscriber runs synchronously inside the originating request
        # (e.g. certificate issuance). Committing here must NOT expire the
        # caller's ORM instances, otherwise a freshly-created Certificate/CA
        # the caller still holds would be invalidated on next access and raise
        # ObjectDeletedError. Suspend expire-on-commit just for this commit
        # (on the underlying Session — the scoped_session proxy doesn't expose
        # the attribute).
        session = db.session()
        prev_expire = session.expire_on_commit
        try:
            session.expire_on_commit = False
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to queue webhook deliveries for {event_type}: {e}")
        finally:
            session.expire_on_commit = prev_expire

    @staticmethod
    def _build_body_json(event_type: str, payload: dict, timestamp: str) -> str:
        return json.dumps({'event': event_type, 'timestamp': timestamp, 'data': payload}, default=str)

    @staticmethod
    def _perform_delivery(endpoint: WebhookEndpoint, event_type: str, body_json: str):
        """Build headers, sign, and POST. Returns (ok, status_code, error)."""
        headers = {}
        headers.update(_safe_custom_headers(endpoint.get_headers()))
        headers.update(_build_auth_header(endpoint))
        headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'UCM-Webhook/2.0',
            'X-UCM-Event': event_type,
        })
        secret_plain = decrypt_if_needed(endpoint.secret) if endpoint.secret else None
        if secret_plain:
            signature = hmac.new(secret_plain.encode(), body_json.encode(), hashlib.sha256).hexdigest()
            headers['X-UCM-Signature'] = f'sha256={signature}'

        from utils.ssrf_protection import safe_request_post
        try:
            response = safe_request_post(endpoint.url, data=body_json, headers=headers, timeout=10)
            return bool(response.ok), response.status_code, (None if response.ok else f"HTTP {response.status_code}")
        except requests.RequestException as e:
            return False, None, str(e)
        except ValueError as e:  # SSRF / DNS rejection from safe_request_post
            return False, None, f"URL rejected: {e}"
        except Exception as e:
            return False, None, str(e)

    @staticmethod
    def _backoff_seconds(attempts: int) -> int:
        return min(WebhookService._BACKOFF_BASE_SECONDS * (2 ** max(attempts - 1, 0)),
                   WebhookService._BACKOFF_CAP_SECONDS)

    @staticmethod
    def process_pending_deliveries(limit: int = 50) -> dict:
        """Scheduler task: deliver due pending webhook deliveries with backoff."""
        from models import WebhookDelivery
        now = utc_now()
        result = {'attempted': 0, 'delivered': 0, 'retry': 0, 'failed': 0}
        try:
            due = (WebhookDelivery.query
                   .filter(WebhookDelivery.status == WebhookDelivery.STATUS_PENDING,
                           WebhookDelivery.next_attempt_at <= now)
                   .order_by(WebhookDelivery.next_attempt_at.asc())
                   .limit(limit).all())
        except Exception as e:
            logger.error(f"Webhook delivery query failed: {e}")
            return result

        for d in due:
            # Atomic claim (#139): only one scheduler/worker may send a row.
            # Bump attempts + push next_attempt_at forward (a lease) in a single
            # conditional UPDATE; if another process already claimed it the
            # rowcount is 0 and we skip — guarantees exactly-once delivery even
            # when the scheduler runs in multiple workers. A crashed claim is
            # reclaimed once the lease (next_attempt_at) elapses.
            from sqlalchemy import update as _sa_update
            claimed = db.session.execute(
                _sa_update(WebhookDelivery)
                .where(WebhookDelivery.id == d.id,
                       WebhookDelivery.status == WebhookDelivery.STATUS_PENDING,
                       WebhookDelivery.next_attempt_at <= now)
                .values(attempts=(WebhookDelivery.attempts + 1),
                        next_attempt_at=now + timedelta(seconds=WebhookService._CLAIM_LEASE_SECONDS))
            ).rowcount
            db.session.commit()
            if not claimed:
                continue  # already claimed by a concurrent scheduler
            db.session.refresh(d)

            result['attempted'] += 1
            endpoint = WebhookEndpoint.query.get(d.endpoint_id)
            if not endpoint or not endpoint.enabled:
                d.status = WebhookDelivery.STATUS_FAILED
                d.last_error = 'Endpoint missing or disabled'
                result['failed'] += 1
                _safe_commit()
                continue

            body_json = WebhookService._build_body_json(d.event_type, json.loads(d.payload), d.event_timestamp)
            ok, code, err = WebhookService._perform_delivery(endpoint, d.event_type, body_json)
            d.last_response_code = code
            d.last_error = err
            if ok:
                d.status = WebhookDelivery.STATUS_DELIVERED
                d.delivered_at = now
                endpoint.last_success = now
                endpoint.failure_count = 0
                result['delivered'] += 1
            elif d.attempts >= (d.max_attempts or WebhookService.DEFAULT_MAX_ATTEMPTS):
                d.status = WebhookDelivery.STATUS_FAILED
                endpoint.last_failure = now
                endpoint.failure_count = (endpoint.failure_count or 0) + 1
                result['failed'] += 1
            else:
                d.next_attempt_at = now + timedelta(seconds=WebhookService._backoff_seconds(d.attempts))
                endpoint.last_failure = now
                endpoint.failure_count = (endpoint.failure_count or 0) + 1
                result['retry'] += 1
            _safe_commit()
        if result['attempted']:
            logger.info(f"Webhook deliveries processed: {result}")
        return result
    
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
        # Test sends synchronously for immediate operator feedback (unlike real
        # lifecycle events, which are queued and delivered asynchronously).
        body_json = WebhookService._build_body_json('test', test_payload, utc_now().isoformat())
        ok, code, err = WebhookService._perform_delivery(endpoint, 'test', body_json)
        if ok:
            return True, f"Success: {code}"
        return False, f"Failed: {err or code}"


# ---------------------------------------------------------------------------
# Lifecycle emit helpers — call these from business logic. Each is wrapped so
# a webhook problem can never propagate into (and abort) the operation that
# triggered it. send_event() is already non-raising; the extra guard here is
# belt-and-braces for payload construction.
# ---------------------------------------------------------------------------
def _emit(event_type: str, payload: dict, ca_refid: str = None, meta: dict = None):
    try:
        from services.events import event_bus
        event_bus.emit(event_type, payload, ca_refid, meta or {})
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Event emit failed for {event_type}: {e}")


def _meta(actor=None, **extra):
    m = {k: v for k, v in extra.items() if v is not None}
    if actor is not None:
        m['actor'] = actor
    return m


def emit_cert_issued(cert: dict, ca_refid: str = None, actor: str = None):
    _emit(WebhookService.CERT_ISSUED, {'certificate': cert}, ca_refid, _meta(actor))


def emit_cert_revoked(cert: dict, reason: str = None, ca_refid: str = None, actor: str = None):
    _emit(WebhookService.CERT_REVOKED, {'certificate': cert, 'reason': reason}, ca_refid, _meta(actor, reason=reason))


def emit_cert_renewed(cert: dict, ca_refid: str = None, actor: str = None):
    _emit(WebhookService.CERT_RENEWED, {'certificate': cert}, ca_refid, _meta(actor))


def emit_cert_expiring(cert: dict, days_left: int = None, ca_refid: str = None):
    _emit(WebhookService.CERT_EXPIRING, {'certificate': cert, 'days_left': days_left}, ca_refid)


def emit_cert_expired(cert: dict, ca_refid: str = None):
    _emit(WebhookService.CERT_EXPIRED, {'certificate': cert}, ca_refid)


def emit_cert_imported(cert: dict, ca_refid: str = None, actor: str = None):
    _emit(WebhookService.CERT_IMPORTED, {'certificate': cert}, ca_refid, _meta(actor))


def emit_cert_deleted(cert: dict, ca_refid: str = None, actor: str = None):
    _emit(WebhookService.CERT_DELETED, {'certificate': cert}, ca_refid, _meta(actor))


def emit_ca_created(ca: dict, actor: str = None):
    refid = ca.get('refid') if isinstance(ca, dict) else None
    _emit(WebhookService.CA_CREATED, {'ca': ca}, refid, _meta(actor))


def emit_ca_updated(ca: dict, actor: str = None, changes: dict = None):
    refid = ca.get('refid') if isinstance(ca, dict) else None
    _emit(WebhookService.CA_UPDATED, {'ca': ca}, refid, _meta(actor, changes=changes))


def emit_ca_deleted(ca: dict, actor: str = None):
    refid = ca.get('refid') if isinstance(ca, dict) else None
    _emit(WebhookService.CA_DELETED, {'ca': ca}, refid, _meta(actor))


def emit_csr_submitted(csr: dict, actor: str = None):
    _emit(WebhookService.CSR_SUBMITTED, {'csr': csr}, None, _meta(actor))


def emit_csr_approved(csr: dict, actor: str = None):
    _emit(WebhookService.CSR_APPROVED, {'csr': csr}, None, _meta(actor))


def emit_csr_rejected(csr: dict, reason: str = None, actor: str = None):
    _emit(WebhookService.CSR_REJECTED, {'csr': csr, 'reason': reason}, None, _meta(actor, reason=reason))


def emit_template_created(template: dict, actor: str = None):
    _emit(WebhookService.TEMPLATE_CREATED, {'template': template}, None, _meta(actor))


def emit_template_updated(template: dict, actor: str = None):
    _emit(WebhookService.TEMPLATE_UPDATED, {'template': template}, None, _meta(actor))


def emit_acme_preflight(
    domains: list,
    ok: bool,
    mode: str,
    steps: list,
    actor: str = None,
):
    _emit(
        WebhookService.ACME_PREFLIGHT,
        {
            'domains': domains,
            'ok': ok,
            'mode': mode,
            'steps': steps,
        },
        None,
        _meta(actor),
    )


# Backward-compatible aliases (previous names)
trigger_cert_issued = emit_cert_issued
trigger_cert_revoked = emit_cert_revoked


# Register the webhook delivery handler on the event bus exactly once. Importing
# this module (which the lifecycle emit_* helpers all do) wires the subscriber,
# so any bus event is turned into durable, async WebhookDelivery rows.
def _register_bus_subscriber():
    from services.events import event_bus, ALL
    if not getattr(_register_bus_subscriber, '_done', False):
        event_bus.subscribe(ALL, WebhookService.enqueue_deliveries)
        _register_bus_subscriber._done = True


_register_bus_subscriber()
