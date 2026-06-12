"""Tests for the durable, async webhook delivery queue and the event bus."""
import json
from datetime import timedelta
import pytest

from models import db, WebhookDelivery
from services.webhook_service import WebhookService, WebhookEndpoint
from utils.datetime_utils import utc_now


@pytest.fixture
def endpoint(app):
    with app.app_context():
        # The app fixture is session-scoped with a shared DB and no per-test
        # rollback, so clear any transaction a prior test may have left dirty
        # and purge deliveries *before* creating the endpoint. Reading ep.id
        # then happens right after its own commit, with no intervening DML to
        # expire/invalidate the instance (avoids a flaky ObjectDeletedError).
        db.session.rollback()
        WebhookDelivery.query.delete()
        db.session.commit()
        ep = WebhookEndpoint(name='sink', url='https://example.invalid/h',
                             events=json.dumps(['*']), enabled=True)
        db.session.add(ep)
        db.session.commit()
        return ep.id


class TestEventBus:
    def test_emit_isolates_failing_handler(self):
        from services.events import EventBus
        bus = EventBus()
        seen = []
        bus.subscribe('x', lambda e, p, c, m: (_ for _ in ()).throw(RuntimeError('boom')))
        bus.subscribe('x', lambda e, p, c, m: seen.append(e))
        bus.emit('x', {})  # must not raise; second handler still runs
        assert seen == ['x']

    def test_wildcard_receives_all(self):
        from services.events import EventBus, ALL
        bus = EventBus()
        seen = []
        bus.subscribe(ALL, lambda e, p, c, m: seen.append(e))
        bus.emit('a', {}); bus.emit('b', {})
        assert seen == ['a', 'b']


class TestEnqueue:
    def test_event_creates_pending_delivery(self, app, endpoint):
        with app.app_context():
            WebhookService.enqueue_deliveries('certificate.issued', {'id': 1})
            rows = WebhookDelivery.query.filter_by(endpoint_id=endpoint).all()
            assert len(rows) == 1
            assert rows[0].status == 'pending' and rows[0].attempts == 0

    def test_enqueue_does_not_expire_caller_objects(self, app, endpoint):
        # enqueue_deliveries runs synchronously inside the originating request
        # and commits; that commit must not expire ORM instances the caller
        # still holds (which would raise ObjectDeletedError on next access).
        from sqlalchemy import inspect
        with app.app_context():
            held = WebhookEndpoint.query.get(endpoint)
            _ = held.name  # ensure loaded
            WebhookService.enqueue_deliveries('certificate.issued', {'id': 1})
            assert not inspect(held).expired  # still usable, no refresh needed
            assert held.name == 'sink'

    def test_ca_filter_excludes_non_matching(self, app):
        with app.app_context():
            ep = WebhookEndpoint(name='ca-scoped', url='https://x.invalid/h',
                                 events=json.dumps(['*']), enabled=True, ca_filter='ca-AAA')
            db.session.add(ep)
            db.session.commit()
            WebhookDelivery.query.filter_by(endpoint_id=ep.id).delete()
            db.session.commit()
            WebhookService.enqueue_deliveries('certificate.issued', {'id': 1}, ca_refid='ca-BBB')
            assert WebhookDelivery.query.filter_by(endpoint_id=ep.id).count() == 0


class TestProcessDeliveries:
    def _queue(self, app, endpoint, **overrides):
        with app.app_context():
            d = WebhookDelivery(endpoint_id=endpoint, event_type='certificate.issued',
                                payload=json.dumps({'id': 1}), event_timestamp=utc_now().isoformat(),
                                status='pending', next_attempt_at=utc_now(), max_attempts=3)
            for k, v in overrides.items():
                setattr(d, k, v)
            db.session.add(d)
            db.session.commit()
            return d.id

    def test_success_marks_delivered(self, app, endpoint, monkeypatch):
        did = self._queue(app, endpoint)
        monkeypatch.setattr(WebhookService, '_perform_delivery',
                            staticmethod(lambda ep, et, body: (True, 200, None)))
        with app.app_context():
            res = WebhookService.process_pending_deliveries()
            assert res['delivered'] == 1
            assert WebhookDelivery.query.get(did).status == 'delivered'

    def test_failure_retries_with_backoff(self, app, endpoint, monkeypatch):
        did = self._queue(app, endpoint)
        monkeypatch.setattr(WebhookService, '_perform_delivery',
                            staticmethod(lambda ep, et, body: (False, 503, 'HTTP 503')))
        with app.app_context():
            res = WebhookService.process_pending_deliveries()
            assert res['retry'] == 1
            d = WebhookDelivery.query.get(did)
            assert d.status == 'pending' and d.attempts == 1
            assert d.next_attempt_at > utc_now()  # backed off into the future

    def test_marks_failed_after_max_attempts(self, app, endpoint, monkeypatch):
        did = self._queue(app, endpoint, attempts=2)  # max_attempts=3, this is the 3rd
        monkeypatch.setattr(WebhookService, '_perform_delivery',
                            staticmethod(lambda ep, et, body: (False, 500, 'HTTP 500')))
        with app.app_context():
            res = WebhookService.process_pending_deliveries()
            assert res['failed'] == 1
            assert WebhookDelivery.query.get(did).status == 'failed'

    def test_future_deliveries_not_picked(self, app, endpoint, monkeypatch):
        self._queue(app, endpoint, next_attempt_at=utc_now() + timedelta(hours=1))
        calls = []
        monkeypatch.setattr(WebhookService, '_perform_delivery',
                            staticmethod(lambda ep, et, body: calls.append(1) or (True, 200, None)))
        with app.app_context():
            res = WebhookService.process_pending_deliveries()
            assert res['attempted'] == 0 and calls == []

    def test_disabled_endpoint_marks_failed(self, app, endpoint, monkeypatch):
        did = self._queue(app, endpoint)
        with app.app_context():
            WebhookEndpoint.query.get(endpoint).enabled = False
            db.session.commit()
            res = WebhookService.process_pending_deliveries()
            assert res['failed'] == 1
            assert WebhookDelivery.query.get(did).status == 'failed'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
