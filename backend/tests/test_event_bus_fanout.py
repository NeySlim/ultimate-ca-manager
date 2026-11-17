"""Verify the event bus fans a single lifecycle event out to all three
notification systems (webhook delivery queue, email, WebSocket)."""
import json
import pytest

from models import db, WebhookDelivery
from services.webhook_service import WebhookEndpoint, emit_cert_issued, emit_ca_created


@pytest.fixture
def all_events_endpoint(app):
    with app.app_context():
        # Shared session-scoped DB with no per-test rollback: clear any dirty
        # transaction and purge deliveries before creating the endpoint so
        # ep.id is read right after its own commit (avoids ObjectDeletedError).
        db.session.rollback()
        WebhookDelivery.query.delete()
        db.session.commit()
        ep = WebhookEndpoint(name='fanout', url='https://x.invalid/h',
                             events=json.dumps(['*']), enabled=True)
        db.session.add(ep)
        db.session.commit()
        return ep.id


class TestFanout:
    def test_cert_issued_reaches_webhook_email_and_ws(self, app, create_ca, create_cert,
                                                      all_events_endpoint, monkeypatch):
        # Capture email + WS without sending anything
        email_calls, ws_calls = [], []
        monkeypatch.setattr('services.notification.NotificationService.on_certificate_issued',
                            staticmethod(lambda cert, actor=None: email_calls.append((cert.id, actor))))
        monkeypatch.setattr('websocket.emitters.on_certificate_issued',
                            lambda *a, **k: ws_calls.append(a))

        with app.app_context():
            ca = create_ca(cn='Fanout CA')
            cert = create_cert(cn='fanout.example.com', ca_id=ca['id'])
            cert_obj = __import__('models').db.session.get(__import__('models').Certificate, cert['id'])

            # create_cert already issued one event via the real path — reset so
            # we assert exactly on our explicit emit below.
            WebhookDelivery.query.delete()
            db.session.commit()
            email_calls.clear()
            ws_calls.clear()

            emit_cert_issued(cert_obj.to_dict(), ca_refid=cert_obj.caref, actor='alice')

            # 1) webhook → durable delivery row
            assert WebhookDelivery.query.filter_by(
                endpoint_id=all_events_endpoint, event_type='certificate.issued').count() == 1
            # 2) email subscriber invoked with the model + actor
            assert email_calls and email_calls[0][1] == 'alice'
            # 3) WebSocket subscriber invoked
            assert ws_calls

    def test_ca_created_reaches_email_and_ws(self, app, create_ca, monkeypatch):
        email_calls, ws_calls = [], []
        monkeypatch.setattr('services.notification.NotificationService.on_ca_created',
                            staticmethod(lambda ca, actor=None: email_calls.append(actor)))
        monkeypatch.setattr('websocket.emitters.on_ca_created',
                            lambda *a, **k: ws_calls.append(a))
        with app.app_context():
            ca = create_ca(cn='Fanout CA2')
            ca_obj = __import__('models').db.session.get(__import__('models').CA, ca['id'])
            email_calls.clear()  # create_ca already fired one event via the real path
            ws_calls.clear()
            emit_ca_created(ca_obj.to_dict(), actor='bob')
            assert email_calls and email_calls[0] == 'bob'
            assert ws_calls

    def test_handler_failure_isolated(self, app, create_ca, create_cert, monkeypatch):
        # A throwing email handler must not break the WS handler or the caller
        ws_calls = []
        monkeypatch.setattr('services.notification.NotificationService.on_certificate_issued',
                            staticmethod(lambda cert, actor=None: (_ for _ in ()).throw(RuntimeError('smtp down'))))
        monkeypatch.setattr('websocket.emitters.on_certificate_issued',
                            lambda *a, **k: ws_calls.append(a))
        with app.app_context():
            ca = create_ca(cn='Iso CA')
            cert = create_cert(cn='iso.example.com', ca_id=ca['id'])
            cert_obj = __import__('models').db.session.get(__import__('models').Certificate, cert['id'])
            emit_cert_issued(cert_obj.to_dict(), ca_refid=cert_obj.caref)  # must not raise
            assert ws_calls  # WS still fired despite email throwing


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
