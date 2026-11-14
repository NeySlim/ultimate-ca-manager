"""One webhook subsystem, and the settings-stored one is migrated into it.

UCM carried two. ``/api/v2/settings/webhooks`` kept its entries as a JSON
blob in ``system_config['webhooks']``; no delivery path, no scheduler task
and no frontend screen ever read that blob back. It answered 201 Created,
wrote an audit entry, and dropped every event the operator subscribed to.
``/api/v2/webhooks`` writes ``webhook_endpoints`` rows, which is what the
event bus fans out to.

The settings-backed routes are gone. Migration 087 moves anything an
operator configured through them into ``webhook_endpoints``, so those
subscriptions start being delivered rather than silently disappearing.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from models import SystemConfig, db
from models.webhook_delivery import WebhookDelivery
from services.webhook_service import WebhookEndpoint

LEGACY_ROUTES = (
    ('get', '/api/v2/settings/webhooks'),
    ('post', '/api/v2/settings/webhooks'),
    ('delete', '/api/v2/settings/webhooks/1'),
    ('post', '/api/v2/settings/webhooks/1/test'),
)


class TestLegacyRoutesAreGone:
    def test_no_rule_is_registered_for_them(self, app):
        """Checked on the URL map: the SPA catch-all answers 404/405 for any
        unknown path, so a status code alone would not prove the routes are
        gone."""
        rules = [str(r) for r in app.url_map.iter_rules()
                 if str(r).startswith('/api/v2/settings/webhooks')]
        assert rules == [], f'settings webhook routes still registered: {rules}'

    def test_they_no_longer_answer(self, auth_client):
        for method, path in LEGACY_ROUTES:
            call = getattr(auth_client, method)
            r = call(path, data='{}', content_type='application/json') \
                if method in ('post', 'put') else call(path)
            assert r.status_code in (404, 405), (
                f'{method.upper()} {path} still answers {r.status_code}')

    def test_no_module_writes_the_settings_blob(self):
        """Nothing may start writing system_config['webhooks'] again."""
        import pathlib

        backend = pathlib.Path(__file__).resolve().parent.parent
        offenders = []
        for path in backend.rglob('*.py'):
            if 'tests' in path.parts or 'migrations' in path.parts:
                continue
            text = path.read_text()
            if "key='webhooks'" in text or 'key="webhooks"' in text:
                offenders.append(str(path.relative_to(backend)))
        assert not offenders, f'settings-stored webhooks are back in {offenders}'


class TestTheSurvivingSubsystemDelivers:
    def test_endpoint_receives_a_delivery(self, app, auth_client):
        r = auth_client.post(
            '/api/v2/webhooks',
            data=json.dumps({'name': 'kept', 'url': 'https://hook.example.com/kept',
                             'events': ['certificate.issued']}),
            content_type='application/json')
        assert r.status_code == 201, r.get_data(as_text=True)
        endpoint_id = r.get_json()['data']['id']

        with app.app_context():
            before = WebhookDelivery.query.filter_by(endpoint_id=endpoint_id).count()
            from services.webhook_service import emit_cert_issued
            emit_cert_issued({'refid': 'x', 'descr': 'x'}, actor='test')
            after = WebhookDelivery.query.filter_by(endpoint_id=endpoint_id).count()
        assert after == before + 1
