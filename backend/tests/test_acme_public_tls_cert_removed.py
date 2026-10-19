"""`acme_public_tls_cert_id` is gone: it was stored as metadata and never
applied to any listener or deployment."""
import json

from models import SystemConfig


def test_it_is_neither_returned_nor_stored(app, auth_client, clear_acme_public_vhost_settings):
    r = auth_client.patch('/api/v2/settings/general', data=json.dumps({'acme_public_tls_cert_id': 1}),
                          content_type='application/json')
    assert r.status_code == 200, r.data
    assert 'acme_public_tls_cert_id' not in auth_client.get('/api/v2/settings/general').get_json()['data']
    with app.app_context():
        assert SystemConfig.query.filter_by(key='acme_public_tls_cert_id').first() is None
