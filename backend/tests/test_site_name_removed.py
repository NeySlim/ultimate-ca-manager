"""`site_name` is gone; `system_name` is the syslog hostname it always was.

`site_name` was only a fallback the settings page showed in place of an
empty system name, which syslog never used.
"""
import json

from models import SystemConfig, db


def test_site_name_is_neither_returned_nor_stored(app, auth_client):
    r = auth_client.patch('/api/v2/settings/general', data=json.dumps({'site_name': 'Old PKI'}),
                          content_type='application/json')
    assert r.status_code == 200, r.data
    data = auth_client.get('/api/v2/settings/general').get_json()['data']
    assert 'site_name' not in data
    with app.app_context():
        assert SystemConfig.query.filter_by(key='site_name').first() is None


def test_an_unset_system_name_is_shown_empty(app, auth_client):
    with app.app_context():
        SystemConfig.query.filter_by(key='system_name').delete()
        db.session.commit()
    assert auth_client.get('/api/v2/settings/general').get_json()['data']['system_name'] == ''
