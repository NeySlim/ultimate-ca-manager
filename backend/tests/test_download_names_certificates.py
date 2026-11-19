"""Certificate, CA, CSR, cross-certificate and external-CSR downloads named in Japanese (#448).

The test app refuses a non Latin-1 response header like the real server, so an unfixed route
raises here instead of answering 200.
"""
import pytest

from models import AuditLog, CA, Certificate, db
from tests.download_names import JAPANESE, assert_named

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates', 'drop_new_users')

PASSWORD = 'Export-Passw0rd!'


def _rename(app, model, row_id, descr):
    with app.app_context():
        row = db.session.get(model, row_id)
        row.descr = descr
        db.session.commit()
        return row.refid


@pytest.fixture(scope='module')
def cert(app, create_cert):
    row = create_cert(cn='jp-download.example.com')
    return row['id'], _rename(app, Certificate, row['id'], JAPANESE)


@pytest.fixture(scope='module')
def ca(app, create_ca):
    row = create_ca(cn='JP Download CA')
    return row['id'], _rename(app, CA, row['id'], JAPANESE)


def _key_audits(app, resource_type, resource_id):
    with app.app_context():
        return AuditLog.query.filter_by(action='private_key_exported', resource_type=resource_type,
                                        resource_id=str(resource_id)).count()


CERT_CASES = [
    ({'format': 'pem'}, '.crt'),
    ({'format': 'pem', 'include_chain': True}, '_chain.pem'),
    ({'format': 'pem', 'include_key': True}, '_with_key.pem'),
    ({'format': 'pem', 'include_key': True, 'include_chain': True}, '_full_chain.pem'),
    ({'format': 'der'}, '.der'),
    ({'format': 'pkcs7'}, '.p7b'),
    ({'format': 'p7b'}, '.p7b'),
    ({'format': 'key'}, '.key'),
    ({'format': 'pkcs12', 'password': PASSWORD}, '.p12'),
    ({'format': 'pfx', 'password': PASSWORD}, '.pfx'),
]


@pytest.mark.parametrize('body, ext', CERT_CASES, ids=[c[1] + str(i) for i, c in enumerate(CERT_CASES)])
def test_certificate_export(app, auth_client, cert, body, ext):
    cert_id, refid = cert
    before = _key_audits(app, 'certificate', cert_id)
    r = auth_client.post(f'/api/v2/certificates/{cert_id}/export', json=body)
    assert_named(r, JAPANESE, ext, fallback_stem=refid)
    keyed = body['format'] in ('key', 'pkcs12', 'pfx') or body.get('include_key')
    assert _key_audits(app, 'certificate', cert_id) == before + (1 if keyed else 0)


def test_certificate_export_get(auth_client, cert):
    cert_id, refid = cert
    assert_named(auth_client.get(f'/api/v2/certificates/{cert_id}/export?format=pem'), JAPANESE, '.crt', refid)


def test_certificate_jks_export(app, auth_client, cert):
    pytest.importorskip('jks')
    cert_id, refid = cert
    r = auth_client.post(f'/api/v2/certificates/{cert_id}/export', json={'format': 'jks', 'password': PASSWORD})
    assert_named(r, JAPANESE, '.jks', refid)


CA_CASES = [
    ({'format': 'pem'}, '.crt'),
    ({'format': 'pem', 'include_chain': True}, '_chain.pem'),
    ({'format': 'pem', 'include_key': True}, '_with_key.pem'),
    ({'format': 'der'}, '.der'),
    ({'format': 'pkcs7'}, '.p7b'),
    ({'format': 'key'}, '.key'),
    ({'format': 'pkcs12', 'password': PASSWORD}, '.p12'),
    ({'format': 'pfx', 'password': PASSWORD}, '.pfx'),
]


@pytest.mark.parametrize('body, ext', CA_CASES, ids=[c[1] + str(i) for i, c in enumerate(CA_CASES)])
def test_ca_export(app, auth_client, ca, body, ext):
    ca_id, refid = ca
    before = _key_audits(app, 'ca', ca_id)
    r = auth_client.post(f'/api/v2/cas/{ca_id}/export', json=body)
    assert_named(r, JAPANESE, ext, fallback_stem=refid)
    keyed = body['format'] in ('key', 'pkcs12', 'pfx') or body.get('include_key')
    assert _key_audits(app, 'ca', ca_id) == before + (1 if keyed else 0)


def test_ca_jks_export(auth_client, ca):
    pytest.importorskip('jks')
    ca_id, refid = ca
    r = auth_client.post(f'/api/v2/cas/{ca_id}/export', json={'format': 'jks', 'password': PASSWORD})
    assert_named(r, JAPANESE, '.jks', refid)


def test_ca_taken_offline_to_a_file(auth_client, create_ca, app):
    row = create_ca(cn='JP Offline CA')
    refid = _rename(app, CA, row['id'], JAPANESE)
    r = auth_client.post(f'/api/v2/cas/{row["id"]}/offline', json={'password': 'OfflineP@ss2026!', 'mode': 'file_exported'})
    assert_named(r, JAPANESE, '-offline.key', refid)


def test_external_ca_csr(app, auth_client):
    r = auth_client.post('/api/v2/cas', json={'type': 'external', 'commonName': 'JP External CSR CA'})
    assert r.status_code in (200, 201), r.data
    data = r.get_json()['data']
    refid = _rename(app, CA, data['id'], JAPANESE)
    assert_named(auth_client.get(f"/api/v2/cas/{data['id']}/csr"), JAPANESE, '.csr', refid)


def _csr(auth_client, cn):
    r = auth_client.post('/api/v2/csrs', json={'cn': cn, 'key_type': 'RSA', 'key_size': 2048})
    assert r.status_code in (200, 201), r.data
    return r.get_json()['data']['id']


def test_csr_and_its_key(app, auth_client):
    csr_id = _csr(auth_client, 'jp-csr.example.com')
    refid = _rename(app, Certificate, csr_id, JAPANESE)
    assert_named(auth_client.get(f'/api/v2/csrs/{csr_id}/export'), JAPANESE, '.csr', refid)
    assert_named(auth_client.get(f'/api/v2/csrs/{csr_id}/export?format=key'), JAPANESE, '.key', refid)
