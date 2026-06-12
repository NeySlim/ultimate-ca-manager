"""Regression tests proving webhook lifecycle events are actually wired.

Before this, WebhookService.send_event was never called from business logic —
the feature was configurable but dead. These tests assert (a) the advertised
event catalogue (15+), and (b) that issuing a certificate really dispatches
certificate.issued to a matching endpoint.
"""
import json
import pytest

from services.webhook_service import (
    WebhookService, WebhookEndpoint,
    emit_cert_issued, emit_template_created,
)
from models import db


def test_event_catalogue_has_15_plus():
    assert len(WebhookService.ALL_EVENTS) >= 15
    for ev in ('certificate.issued', 'certificate.expired', 'certificate.imported',
               'certificate.deleted', 'ca.deleted', 'template.created', 'template.updated'):
        assert ev in WebhookService.ALL_EVENTS


def test_emit_helper_calls_send_event(monkeypatch):
    calls = []
    monkeypatch.setattr(WebhookService, 'send_event',
                        staticmethod(lambda et, payload, ca_refid=None: calls.append(et)))
    emit_cert_issued({'id': 1}, ca_refid='abc')
    emit_template_created({'id': 2})
    assert 'certificate.issued' in calls
    assert 'template.created' in calls


def test_emit_never_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("webhook backend down")
    monkeypatch.setattr(WebhookService, 'send_event', staticmethod(_boom))
    # Must not propagate — a webhook failure can't break the caller
    emit_cert_issued({'id': 1})


class TestIssuanceFiresWebhook:
    def test_create_certificate_dispatches_issued(self, app, auth_client, create_ca, monkeypatch):
        ca = create_ca(cn='Webhook Fire CA')

        delivered = []

        with app.app_context():
            # Subscribe an endpoint to all events
            ep = WebhookEndpoint(
                name='test-sink', url='https://example.invalid/hook',
                events=json.dumps(['*']), enabled=True,
            )
            db.session.add(ep)
            db.session.commit()

        # Intercept the actual HTTP send so nothing leaves the box
        monkeypatch.setattr(
            WebhookService, '_send_webhook',
            staticmethod(lambda endpoint, event_type, payload: delivered.append(event_type)),
        )

        r = auth_client.post('/api/v2/certificates', data=json.dumps({
            'cn': 'fire.example.com',
            'ca_id': ca['id'],
            'key_type': 'RSA',
            'key_size': 2048,
            'validity_days': 90,
        }), content_type='application/json')
        assert r.status_code in (200, 201), r.data

        assert 'certificate.issued' in delivered


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
