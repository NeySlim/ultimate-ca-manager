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


@pytest.fixture
def enrolled_with_its_chain(app, auth_client, create_ca):
    """An enrolment whose stored certificate already carries leaf + intermediate (imported full chain)."""
    import base64
    from models import CA
    root = create_ca(cn='PEM inline root')
    inter = create_ca(cn='PEM inline intermediate', type='intermediate', parentCAId=root['id'])
    created = _post(auth_client, '/api/v2/mtls/certificates', {'ca_id': inter['id'], 'name': 'pem-inline'})
    assert created.status_code == 201, created.get_json()
    data = created.get_json()['data']
    with app.app_context():
        row = db.session.get(Certificate, data['certificate_id'])
        inter_pem = base64.b64decode(db.session.get(CA, inter['id']).crt)
        row.crt = base64.b64encode(base64.b64decode(row.crt).rstrip(b'\n') + b'\n' + inter_pem).decode()
        db.session.commit()
    yield f'/api/v2/mtls/certificates/{data["id"]}/download'
    with app.app_context():
        AuthCertificate.query.filter_by(id=data['id']).delete()
        row = db.session.get(Certificate, data['certificate_id'])
        if row:
            db.session.delete(row)
        db.session.commit()


def _subjects(response):
    from cryptography import x509
    assert response.status_code == 200, response.data[:200]
    pems = response.data.split(b'-----END CERTIFICATE-----')
    return [x509.load_pem_x509_certificate(p.strip() + b'\n-----END CERTIFICATE-----\n').subject.rfc4514_string()
            for p in pems if b'BEGIN CERTIFICATE' in p]


def test_an_imported_chain_is_cut_to_the_certificate_alone_by_default(auth_client, enrolled_with_its_chain):
    assert len(_subjects(_post(auth_client, enrolled_with_its_chain, {'format': 'pem'}))) == 1


def test_an_imported_chain_is_not_doubled_by_include_chain(auth_client, enrolled_with_its_chain):
    subjects = _subjects(_post(auth_client, enrolled_with_its_chain, {'format': 'pem', 'include_chain': True}))
    assert len(subjects) == len(set(subjects)) == 2
    assert 'PEM inline' not in subjects[0]  # the leaf comes first


def test_an_imported_chain_with_include_root_has_no_duplicate(auth_client, enrolled_with_its_chain):
    body = {'format': 'pem', 'include_chain': True, 'include_root': True}
    subjects = _subjects(_post(auth_client, enrolled_with_its_chain, body))
    assert len(subjects) == len(set(subjects)) == 3
    assert 'PEM inline' not in subjects[0]
