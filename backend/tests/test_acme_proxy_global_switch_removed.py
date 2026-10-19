"""The ACME proxy has no global on/off switch.

`acme.proxy_enabled` was saved by the Let's Encrypt tab and read by nothing:
turning it off left every proxy endpoint answering. Each CA account's
"Expose via ACME proxy" is what publishes an endpoint.
"""
import json

from models import SystemConfig, db


def test_the_switch_is_neither_stored_nor_returned(app, auth_client):
    with app.app_context():
        SystemConfig.query.filter_by(key='acme.proxy_enabled').delete()
        db.session.commit()
    r = auth_client.patch('/api/v2/acme/client/settings', data=json.dumps({'proxy_enabled': False}),
                          content_type='application/json')
    assert r.status_code == 200, r.data
    with app.app_context():
        assert SystemConfig.query.filter_by(key='acme.proxy_enabled').first() is None
    data = auth_client.get('/api/v2/acme/client/settings').get_json()['data']
    assert 'proxy_enabled' not in data
