"""An intermediate CA names its parent: it is never created as a self-signed root."""
import pytest

from models import CA, db

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

BODY = {'commonName': 'Orphan Intermediate', 'organization': 'Test Org', 'country': 'US',
        'keyAlgo': 'RSA', 'keySize': 2048, 'validityYears': 5}


def _count(app):
    with app.app_context():
        db.session.expire_all()
        return CA.query.count()


@pytest.mark.parametrize('parent', [None, '', 0, 'missing'])
def test_intermediate_without_a_parent_is_refused(app, auth_client, parent):
    body = {**BODY, 'type': 'intermediate'}
    if parent != 'missing':
        body['parentCAId'] = parent
    before = _count(app)
    r = auth_client.post('/api/v2/cas', json=body)
    assert r.status_code == 400, r.data
    assert 'parentCAId' in r.get_json()['message']
    assert _count(app) == before


def test_intermediate_with_a_parent_is_created(auth_client, create_ca):
    parent = create_ca(cn='Parent For Orphan Test')
    r = auth_client.post('/api/v2/cas', json={**BODY, 'type': 'intermediate',
                                              'parentCAId': parent['id']})
    assert r.status_code in (200, 201), r.data


def test_a_root_needs_no_parent(auth_client):
    r = auth_client.post('/api/v2/cas', json={**BODY, 'type': 'root', 'commonName': 'Root No Parent'})
    assert r.status_code in (200, 201), r.data


def test_an_external_csr_ca_needs_no_parent(auth_client):
    r = auth_client.post('/api/v2/cas', json={**BODY, 'type': 'external',
                                              'commonName': 'External No Parent'})
    assert r.status_code in (200, 201), r.data
