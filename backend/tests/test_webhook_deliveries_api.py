"""Tests for the webhook delivery history + retry endpoints."""
import json
import pytest

from models import db, WebhookDelivery
from services.webhook_service import WebhookEndpoint
from utils.datetime_utils import utc_now


@pytest.fixture
def endpoint_with_deliveries(app):
    with app.app_context():
        # Shared session-scoped DB with no per-test rollback: clear any dirty
        # transaction left by a prior test before creating the endpoint.
        db.session.rollback()
        ep = WebhookEndpoint(name='hist', url='https://x.invalid/h',
                             events=json.dumps(['*']), enabled=True)
        db.session.add(ep)
        db.session.commit()
        eid = ep.id
        WebhookDelivery.query.filter_by(endpoint_id=eid).delete()
        for st in ('delivered', 'failed', 'pending'):
            db.session.add(WebhookDelivery(
                endpoint_id=eid, event_type='certificate.issued',
                payload='{"certificate":{"id":1}}', event_timestamp=utc_now().isoformat(),
                status=st, next_attempt_at=utc_now(),
                attempts=3 if st == 'failed' else 0, max_attempts=5,
                last_error='HTTP 500' if st == 'failed' else None,
            ))
        db.session.commit()
        return eid


class TestDeliveriesList:
    def test_requires_auth(self, client, endpoint_with_deliveries):
        assert client.get(f'/api/v2/webhooks/{endpoint_with_deliveries}/deliveries').status_code == 401

    def test_lists_all(self, auth_client, endpoint_with_deliveries):
        r = auth_client.get(f'/api/v2/webhooks/{endpoint_with_deliveries}/deliveries')
        assert r.status_code == 200
        body = json.loads(r.data)
        assert body['meta']['total'] == 3
        assert all('status' in d and 'attempts' in d for d in body['data'])

    def test_status_filter(self, auth_client, endpoint_with_deliveries):
        r = auth_client.get(f'/api/v2/webhooks/{endpoint_with_deliveries}/deliveries?status=failed')
        body = json.loads(r.data)
        assert body['meta']['total'] == 1
        assert body['data'][0]['status'] == 'failed'

    def test_unknown_endpoint_404(self, auth_client):
        assert auth_client.get('/api/v2/webhooks/999999/deliveries').status_code == 404


class TestRetry:
    def test_retry_requeues_failed_delivery(self, app, auth_client, endpoint_with_deliveries):
        with app.app_context():
            failed = WebhookDelivery.query.filter_by(
                endpoint_id=endpoint_with_deliveries, status='failed').first()
            fid = failed.id
        r = auth_client.post(f'/api/v2/webhooks/{endpoint_with_deliveries}/deliveries/{fid}/retry')
        assert r.status_code == 200
        with app.app_context():
            d = WebhookDelivery.query.get(fid)
            assert d.status == 'pending'
            assert d.attempts == 0 and d.last_error is None

    def test_retry_unknown_delivery_404(self, auth_client, endpoint_with_deliveries):
        assert auth_client.post(
            f'/api/v2/webhooks/{endpoint_with_deliveries}/deliveries/999999/retry').status_code == 404


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
