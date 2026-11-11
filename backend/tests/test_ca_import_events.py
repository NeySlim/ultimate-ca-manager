"""A CA brought in through the certificate import or the Smart Import tells the bus."""
import json

import pytest

from tests.deploy_leftovers import delete_leftovers
from tests.test_import_review import _cert, _gen, _import, _pem

IMPORT = '/api/v2/certificates/import'
_cleanup = pytest.fixture(autouse=True)(delete_leftovers)


@pytest.fixture
def ca_events(monkeypatch):
    from services.events import event_bus
    seen, real = [], event_bus.emit

    def record(event_type, payload, ca_refid=None, meta=None):
        if event_type.startswith('ca.'):
            seen.append((event_type, ((payload or {}).get('ca') or {}).get('id')))
        return real(event_type, payload, ca_refid, meta)

    monkeypatch.setattr(event_bus, 'emit', record)
    return seen


def test_certificate_import_of_a_ca_fires_created_then_updated(app, auth_client, ca_events):
    key = _gen()
    cert = _cert('ev-ca-import Root', key, ca=True)
    r = _import(auth_client, IMPORT, cert)
    assert r.status_code == 201, r.data
    ca_id = json.loads(r.data)['data']['id']
    assert ca_events == [('ca.created', ca_id)]
    r = _import(auth_client, IMPORT, cert, key, update_existing='true')
    assert r.status_code == 200, r.data
    assert ca_events == [('ca.created', ca_id), ('ca.updated', ca_id)]


def test_smart_import_of_a_ca_fires_created_once(app, auth_client, ca_events):
    cert = _cert('ev-ca-smart Root', _gen(), ca=True)
    r = auth_client.post('/api/v2/import/execute', data=json.dumps({
        'content': _pem(cert), 'options': {'import_cas': True, 'import_certs': True}}),
        content_type='application/json')
    assert r.status_code in (200, 201), r.data
    assert [e for e, _ in ca_events] == ['ca.created']
