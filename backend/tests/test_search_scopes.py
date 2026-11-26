"""The global search shows certificates, CAs and templates only to who may read their
lists (read:certificates, read:cas, read:templates), as it already does for users,
ACME accounts and SCEP profiles."""
import json
import uuid

import pytest

pytestmark = pytest.mark.usefixtures('drop_new_users', 'drop_new_cas_and_certificates')

TOKEN = 'srchscope' + uuid.uuid4().hex[:6]


@pytest.fixture(scope='module')
def objects(auth_client, create_ca, create_cert):
    ca = create_ca(cn=f'{TOKEN} CA')
    create_cert(cn=f'{TOKEN}.example.com', ca_id=ca['id'])
    r = auth_client.post('/api/v2/templates', data=json.dumps(
        {'name': f'{TOKEN} template', 'template_type': 'web_server', 'description': 'search scopes'}),
        content_type='application/json')
    assert r.status_code in (200, 201), r.data
    template_id = (r.get_json().get('data') or {}).get('id')
    yield
    if template_id:
        auth_client.delete(f'/api/v2/templates/{template_id}')


@pytest.fixture
def key_client(app, auth_client):
    """A client sending an admin-owned API key minted with the given scopes."""
    made = []

    def _mint(permissions):
        r = auth_client.post('/api/v2/account/apikeys', data=json.dumps(
            {'password': 'changeme123', 'name': f'search-scope-{len(made)}', 'permissions': permissions}),
            content_type='application/json')
        assert r.status_code == 201, r.data
        data = r.get_json()['data']
        made.append(data['id'])
        return {'X-API-Key': data['key']}
    yield _mint
    for key_id in made:
        auth_client.delete(f'/api/v2/account/apikeys/{key_id}')


def _search(client, headers=None):
    r = client.get(f'/api/v2/search?q={TOKEN}&limit=20', headers=headers or {})
    assert r.status_code == 200, r.data
    return r.get_json()['data']


def test_a_key_without_the_read_scopes_lists_none(app, objects, key_client):
    data = _search(app.test_client(), key_client(['read:acme']))
    assert (data['certificates'], data['cas'], data['templates']) == ([], [], [])


@pytest.mark.parametrize('scope, shown', [
    ('read:certificates', 'certificates'), ('read:cas', 'cas'), ('read:templates', 'templates'),
])
def test_each_scope_opens_its_own_category(app, objects, key_client, scope, shown):
    data = _search(app.test_client(), key_client([scope]))
    assert data[shown], data
    for other in {'certificates', 'cas', 'templates'} - {shown}:
        assert data[other] == [], (other, data)


@pytest.mark.parametrize('role', ['auditor', 'operator', 'admin'])
def test_the_built_in_roles_keep_their_results(app, objects, create_user, role):
    create_user(username=f'srch_{role}', role=role)
    c = app.test_client()
    r = c.post('/api/v2/auth/login', data=json.dumps(
        {'username': f'srch_{role}', 'password': 'TestPass123!'}), content_type='application/json')
    assert r.status_code == 200, r.data
    data = _search(c)
    assert data['certificates'] and data['cas'] and data['templates'], data
