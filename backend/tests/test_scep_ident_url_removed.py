"""The SCEP "CA identifier" and URL settings are gone.

Both were stored and shown to clients' operators, but no SCEP exchange read
them: the CA comes from the endpoint or profile, and the URL is fixed.
"""
import json

from models import SystemConfig, db


def test_neither_is_returned_nor_stored(app, auth_client):
    r = auth_client.patch('/api/v2/scep/config', data=json.dumps({'ca_ident': 'x', 'url': '/elsewhere'}),
                          content_type='application/json')
    assert r.status_code == 200, r.data
    data = auth_client.get('/api/v2/scep/config').get_json()['data']
    assert 'ca_ident' not in data and 'url' not in data
    with app.app_context():
        assert SystemConfig.query.filter(SystemConfig.key.in_(['scep_ca_ident', 'scep_url'])).count() == 0
