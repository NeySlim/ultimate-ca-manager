"""`Authorization: Bearer <api key>` is an alias of `X-API-Key`.

Same key lookup, same scopes, same CSRF exemption, and a presented key that
fails is refused rather than falling back to the browser session. `/metrics`
keeps its own bearer token and never accepts an API key.
"""
import json

import pytest
from flask import g

from models import db, SystemConfig
from tests.conftest import assert_success, get_json


@pytest.fixture(scope='module')
def read_certs_key(auth_client):
    r = auth_client.post(
        '/api/v2/account/apikeys',
        data=json.dumps({'name': 'bearer-alias', 'permissions': ['read:certificates']}),
        content_type='application/json',
    )
    return assert_success(r, 201)['key']


def _bearer(key, scheme='Bearer'):
    return {'Authorization': f'{scheme} {key}'}


def test_bearer_key_authenticates(app, read_certs_key):
    r = app.test_client().get('/api/v2/certificates', headers=_bearer(read_certs_key))
    assert r.status_code == 200, r.data


def test_scheme_is_case_insensitive(app, read_certs_key):
    r = app.test_client().get('/api/v2/certificates', headers=_bearer(read_certs_key, 'bearer'))
    assert r.status_code == 200, r.data


def test_bearer_key_is_reported_as_api_key(app, read_certs_key):
    data = get_json(app.test_client().get('/api/v2/auth/verify', headers=_bearer(read_certs_key)))['data']
    assert data['authenticated'] is True
    assert data['auth_method'] == 'api_key'


def test_bearer_key_keeps_its_scopes(app, read_certs_key):
    r = app.test_client().get('/api/v2/users', headers=_bearer(read_certs_key))
    assert r.status_code == 403


def test_invalid_bearer_key_is_refused(app):
    r = app.test_client().get('/api/v2/certificates', headers=_bearer('ucm_ak_not-a-real-key'))
    assert r.status_code == 401


def test_other_schemes_are_not_api_keys(app, read_certs_key):
    r = app.test_client().get('/api/v2/certificates', headers=_bearer(read_certs_key, 'Basic'))
    assert r.status_code == 401


@pytest.mark.parametrize('header', ['X-API-Key', 'Authorization'])
def test_failed_key_does_not_fall_back_to_the_session(auth_client, header):
    value = 'Bearer ucm_ak_bogus' if header == 'Authorization' else 'ucm_ak_bogus'
    r = auth_client.get('/api/v2/certificates', headers={header: value})
    assert r.status_code == 401
    assert auth_client.get('/api/v2/certificates').status_code == 200


def _csrf_middleware(app):
    return next(f for f in app.before_request_funcs.get(None, []) if f.__name__ == 'check_csrf')


@pytest.mark.parametrize('auth, refused', [('Bearer ucm_ak_x', False), ('Basic dXNlcjpwdw==', True)])
def test_bearer_request_skips_csrf(app, monkeypatch, auth, refused):
    monkeypatch.setenv('CSRF_DISABLED', 'false')
    with app.test_request_context('/api/v2/users', method='POST', headers={'Authorization': auth}):
        g.user_id = 1
        result = _csrf_middleware(app)()
        assert (result is not None and result[1] == 403) is refused


@pytest.fixture
def metrics_token(app):
    with app.app_context():
        SystemConfig.query.filter_by(key='metrics_token').delete()
        db.session.add(SystemConfig(key='metrics_token', value='scrape-token-bearer'))
        db.session.commit()
    yield 'scrape-token-bearer'
    with app.app_context():
        SystemConfig.query.filter_by(key='metrics_token').delete()
        db.session.commit()


@pytest.mark.parametrize('path', ['/metrics', '/api/v2/metrics'])
def test_metrics_keeps_its_own_bearer(app, metrics_token, read_certs_key, path):
    c = app.test_client()
    assert c.get(path, headers=_bearer(metrics_token)).status_code == 200
    assert c.get(path, headers=_bearer(read_certs_key)).status_code == 401
