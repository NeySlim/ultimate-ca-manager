"""SCEP on the plain HTTP protocol port (RFC 8894 §7.10: the CMS envelope
already protects the messages), behind an opt-in that is off by default."""
import json
import uuid

import pytest
from werkzeug.test import Client

from models import SystemConfig, db
from protocol_http_server import ProtocolOnlyMiddleware

CAPS = '?operation=GetCACaps'


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if value is None:
        if row:
            db.session.delete(row)
    elif row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


@pytest.fixture
def plain(app, create_ca):
    ca = create_ca(cn=f'SCEP Plain HTTP CA {uuid.uuid4().hex[:8]}')
    with app.app_context():
        _set('scep_ca_id', str(ca['id']))
    yield Client(ProtocolOnlyMiddleware(app))
    with app.app_context():
        _set('scep_ca_id', None)
        _set('scep_plain_http', None)


@pytest.mark.parametrize('path', ['/scep/pkiclient.exe', '/cgi-bin/pkiclient.exe'])
def test_plain_http_scep_is_off_by_default(plain, path):
    assert plain.get(path + CAPS).status_code == 404


@pytest.mark.parametrize('path', ['/scep/pkiclient.exe', '/cgi-bin/pkiclient.exe'])
def test_plain_http_scep_when_enabled(app, plain, path):
    with app.app_context():
        _set('scep_plain_http', 'true')
    r = plain.get(path + CAPS)
    assert r.status_code == 200
    assert b'SCEPStandard' in r.data


def test_plain_http_serves_scep_routes_only(app, plain):
    with app.app_context():
        _set('scep_plain_http', 'true')
    assert plain.get('/scep').status_code == 404
    assert plain.get('/scep/anything/else').status_code == 404


def test_https_scep_ignores_the_option(app, client, plain):
    assert client.get('/scep/pkiclient.exe' + CAPS).status_code == 200


def test_option_round_trips_through_the_api(app, auth_client):
    try:
        assert auth_client.get('/api/v2/scep/config').get_json()['data']['plain_http'] is False
        r = auth_client.patch('/api/v2/scep/config', data=json.dumps({'plain_http': True}),
                              content_type='application/json')
        assert r.status_code == 200
        assert auth_client.get('/api/v2/scep/config').get_json()['data']['plain_http'] is True
    finally:
        with app.app_context():
            _set('scep_plain_http', None)
