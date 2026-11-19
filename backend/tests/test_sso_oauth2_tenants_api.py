"""The accepted tenants of an OIDC provider through the provider API: validated GUIDs, no wildcard,
never without ID token verification; a provider without them answers as before. GUIDs invented."""
import json

import pytest

from models import db
from models.sso import SSOProvider, SSOSession
from tests.sso_identity_support import step_aside

TENANT_A = '0f1e2d3c-4b5a-4968-8778-a6b5c4d3e2f1'
TENANT_B = '1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d'
NAME = 'Entra tenants API'


def _payload(**extra):
    payload = {
        'name': NAME, 'provider_type': 'oauth2', 'enabled': False,
        'oauth2_client_id': 'ucm-client', 'oauth2_client_secret': 'secret',
        'oauth2_auth_url': 'https://idp.example/organizations/oauth2/v2.0/authorize',
        'oauth2_token_url': 'https://idp.example/organizations/oauth2/v2.0/token',
        'oauth2_userinfo_url': 'https://idp.example/oidc/userinfo',
        'oauth2_issuer': 'https://idp.example/organizations/v2.0',
    }
    payload.update(extra)
    return payload


@pytest.fixture
def api(app, auth_client):
    with app.app_context():
        aside = step_aside('oauth2')
    yield auth_client
    with app.app_context():
        for provider in SSOProvider.query.filter_by(name=NAME).all():
            SSOSession.query.filter_by(provider_id=provider.id).delete()
            db.session.delete(provider)
        db.session.commit()
        aside.back()


def _stored(app):
    with app.app_context():
        return SSOProvider.query.filter_by(name=NAME).one().oauth2_tenants


def test_create_stores_the_tenants_normalized(app, api):
    r = api.post('/api/v2/sso/providers', json=_payload(
        oauth2_tenants=[TENANT_A.upper(), f' {TENANT_B} ', TENANT_A]))
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['oauth2_tenants'] == [TENANT_A, TENANT_B]
    assert json.loads(_stored(app)) == [TENANT_A, TENANT_B]


@pytest.mark.parametrize('tenants', [['*'], ['common'], ['organizations'], [42], 'x', {'a': TENANT_A},
                                     [f'{{{TENANT_A}}}'], [f'{TENANT_A}/x']],
                         ids=['star', 'common', 'organizations', 'number', 'word', 'object',
                              'braces', 'slash'])
def test_create_refuses_anything_but_guids(app, api, tenants):
    r = api.post('/api/v2/sso/providers', json=_payload(oauth2_tenants=tenants))
    assert r.status_code == 400
    assert 'tenant' in r.get_json()['message']
    with app.app_context():
        assert SSOProvider.query.filter_by(name=NAME).first() is None


def test_create_refuses_tenants_without_id_token_verification(app, api):
    r = api.post('/api/v2/sso/providers', json=_payload(oauth2_tenants=[TENANT_A], id_token_verify=False))
    assert r.status_code == 400
    assert 'verification' in r.get_json()['message']


def test_create_refuses_tenants_without_an_issuer(app, api):
    r = api.post('/api/v2/sso/providers', json=_payload(oauth2_tenants=[TENANT_A], oauth2_issuer=''))
    assert r.status_code == 400
    assert 'issuer' in r.get_json()['message']


def test_without_tenants_nothing_is_stored_and_the_answer_lists_none(app, api):
    r = api.post('/api/v2/sso/providers', json=_payload())
    assert r.status_code == 200
    assert r.get_json()['data']['oauth2_tenants'] == []
    assert _stored(app) is None


def test_update_adds_removes_and_clears_the_tenants(app, api):
    pid = api.post('/api/v2/sso/providers', json=_payload(oauth2_tenants=[TENANT_A])).get_json()['data']['id']
    r = api.put(f'/api/v2/sso/providers/{pid}', json={'oauth2_tenants': [TENANT_A, TENANT_B]})
    assert r.status_code == 200 and r.get_json()['data']['oauth2_tenants'] == [TENANT_A, TENANT_B]
    r = api.put(f'/api/v2/sso/providers/{pid}', json={'oauth2_tenants': [TENANT_B]})
    assert r.get_json()['data']['oauth2_tenants'] == [TENANT_B]
    r = api.put(f'/api/v2/sso/providers/{pid}', json={'oauth2_tenants': ['*']})
    assert r.status_code == 400
    assert json.loads(_stored(app)) == [TENANT_B]
    r = api.put(f'/api/v2/sso/providers/{pid}', json={'oauth2_tenants': []})
    assert r.status_code == 200 and r.get_json()['data']['oauth2_tenants'] == []
    assert _stored(app) is None


def test_update_refuses_turning_verification_off_while_tenants_are_set(app, api):
    pid = api.post('/api/v2/sso/providers', json=_payload(oauth2_tenants=[TENANT_A])).get_json()['data']['id']
    r = api.put(f'/api/v2/sso/providers/{pid}', json={'id_token_verify': False})
    assert r.status_code == 400
    with app.app_context():
        assert db.session.get(SSOProvider, pid).id_token_verify is True
    r = api.put(f'/api/v2/sso/providers/{pid}', json={'id_token_verify': False, 'oauth2_tenants': []})
    assert r.status_code == 200


def test_an_unchanged_form_round_trips(app, api):
    data = api.post('/api/v2/sso/providers', json=_payload(oauth2_tenants=[TENANT_A])).get_json()['data']
    r = api.put(f"/api/v2/sso/providers/{data['id']}", json=data)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['oauth2_tenants'] == [TENANT_A]
