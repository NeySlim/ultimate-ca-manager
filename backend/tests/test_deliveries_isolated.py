"""A delivery row outlives neither its webhook endpoint nor its deploy binding in the shared suite database:
SQLite reuses the id and the next endpoint inherits the rows (the suite sweeps them after each file)."""
import json
import uuid

import pytest

from datetime import datetime

from models import DeployDelivery, db
from models.webhook_delivery import WebhookDelivery
from services.webhook_service import WebhookEndpoint
from tests import conftest


def test_orphan_webhook_deliveries_and_created_endpoints_are_swept(app):
    with app.app_context():
        if db.engine.dialect.name != 'sqlite':
            pytest.skip('PostgreSQL enforces the references the sweep repairs on SQLite')
        before = conftest._webhook_endpoint_ids()
        sink = WebhookEndpoint(name=f'swept-{uuid.uuid4().hex[:8]}', url='https://example.invalid/h',
                               events=json.dumps(['*']), enabled=True)
        db.session.add(sink)
        db.session.commit()
        sink_id = sink.id
        db.session.add(WebhookDelivery(endpoint_id=sink_id, event_type='x', payload='{}', event_timestamp=datetime.utcnow()))
        db.session.add(WebhookDelivery(endpoint_id=987654, event_type='x', payload='{}',
                                       event_timestamp=datetime.utcnow()))
        for kind in ('certificate', 'crl'):
            db.session.add(DeployDelivery(binding_id=987654, binding_type=kind, event_type='crl.updated'))
        db.session.commit()
    conftest._sweep_deliveries(before)
    with app.app_context():
        assert db.session.get(WebhookEndpoint, sink_id) is None
        assert WebhookDelivery.query.filter(WebhookDelivery.endpoint_id.in_([sink_id, 987654])).count() == 0
        assert DeployDelivery.query.filter_by(binding_id=987654).count() == 0
