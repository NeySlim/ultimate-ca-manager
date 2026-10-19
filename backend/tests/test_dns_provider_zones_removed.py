"""A DNS provider has no zone list in the API.

`zones` was stored and returned but never read: which provider answers for a
domain is decided by ACME > Domains. The field is ignored and not returned.
"""
import json
import uuid

from models import db
from models.acme_models import DnsProvider


def test_zones_are_ignored_and_not_returned(app, auth_client):
    r = auth_client.post('/api/v2/dns-providers', data=json.dumps({
        'name': f'zones-{uuid.uuid4().hex[:8]}', 'provider_type': 'manual', 'zones': ['example.com']}),
        content_type='application/json')
    assert r.status_code == 201, r.data
    created = r.get_json()['data']
    assert 'zones' not in created
    r = auth_client.patch(f"/api/v2/dns-providers/{created['id']}", data=json.dumps({'zones': ['example.org']}),
                          content_type='application/json')
    assert r.status_code == 200, r.data
    assert 'zones' not in auth_client.get(f"/api/v2/dns-providers/{created['id']}").get_json()['data']
    with app.app_context():
        assert db.session.get(DnsProvider, created['id']).zones is None
        db.session.delete(db.session.get(DnsProvider, created['id']))
        db.session.commit()
