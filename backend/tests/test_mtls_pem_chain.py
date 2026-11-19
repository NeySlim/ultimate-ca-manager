"""mTLS PEM download: include_chain / include_root apply when the caller sends them."""
import json

import pytest

from models import Certificate, db
from models.auth_certificate import AuthCertificate

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _post(client, url, data):
    return client.post(url, data=json.dumps(data), content_type='application/json')


def _count(response):
    assert response.status_code == 200, response.data[:200]
    return response.data.count(b'-----BEGIN CERTIFICATE-----')


@pytest.fixture
def enrolled(app, auth_client, create_ca):
    root = create_ca(cn='PEM chain root')
    inter = create_ca(cn='PEM chain intermediate', type='intermediate', parentCAId=root['id'])
    created = _post(auth_client, '/api/v2/mtls/certificates', {'ca_id': inter['id'], 'name': 'pem-chain'})
    assert created.status_code == 201, created.get_json()
    data = created.get_json()['data']
    yield f'/api/v2/mtls/certificates/{data["id"]}/download'
    with app.app_context():
        AuthCertificate.query.filter_by(id=data['id']).delete()
        row = db.session.get(Certificate, data['certificate_id'])
        if row:
            db.session.delete(row)
        db.session.commit()


def test_pem_without_the_flags_is_the_certificate_alone(auth_client, enrolled):
    assert _count(_post(auth_client, enrolled, {'format': 'pem'})) == 1
    assert _count(auth_client.get(enrolled + '?format=pem')) == 1


def test_pem_with_include_chain_appends_the_intermediates(auth_client, enrolled):
    assert _count(_post(auth_client, enrolled, {'format': 'pem', 'include_chain': True})) == 2
    assert _count(auth_client.get(enrolled + '?format=pem&include_chain=true')) == 2


def test_pem_with_include_root_appends_the_root_too(auth_client, enrolled):
    body = {'format': 'pem', 'include_chain': True, 'include_root': True}
    assert _count(_post(auth_client, enrolled, body)) == 3
    assert _count(auth_client.get(enrolled + '?format=pem&include_root=true')) == 3


def test_pem_with_include_chain_false_stays_the_certificate_alone(auth_client, enrolled):
    assert _count(_post(auth_client, enrolled, {'format': 'pem', 'include_chain': False})) == 1
