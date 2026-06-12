"""Durable webhook delivery queue.

Each lifecycle event that matches an enabled endpoint creates one
WebhookDelivery row (status=pending). A scheduler task delivers pending rows
with exponential backoff, so delivery is asynchronous, survives restarts, is
retried on failure, and leaves an auditable per-endpoint history.
"""
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class WebhookDelivery(db.Model):
    __tablename__ = 'webhook_deliveries'

    STATUS_PENDING = 'pending'
    STATUS_DELIVERED = 'delivered'
    STATUS_FAILED = 'failed'

    id = db.Column(db.Integer, primary_key=True)
    # Logical reference to webhook_endpoints.id. No DB-level FK: WebhookEndpoint
    # is defined in services/ and isn't in this metadata at mapper-config time.
    endpoint_id = db.Column(db.Integer, nullable=False, index=True)
    event_type = db.Column(db.String(64), nullable=False)
    # JSON of the event 'data' payload, plus the original event timestamp so
    # the delivered body (and therefore the HMAC signature) is reproducible.
    payload = db.Column(db.Text, nullable=False)
    event_timestamp = db.Column(db.String(40), nullable=False)

    status = db.Column(db.String(16), nullable=False, default=STATUS_PENDING, index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=5)
    next_attempt_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)

    last_response_code = db.Column(db.Integer)
    last_error = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    delivered_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'endpoint_id': self.endpoint_id,
            'event_type': self.event_type,
            'status': self.status,
            'attempts': self.attempts,
            'max_attempts': self.max_attempts,
            'next_attempt_at': utc_isoformat(self.next_attempt_at),
            'last_response_code': self.last_response_code,
            'last_error': self.last_error,
            'created_at': utc_isoformat(self.created_at),
            'delivered_at': utc_isoformat(self.delivered_at),
        }
