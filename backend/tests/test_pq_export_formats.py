"""Exports of ML-DSA keys: PKCS#12 and JKS, which pyca cannot write for them, are
refused with a 400 and the stable reason ``unsupported_for_key_algorithm`` on every
route instead of a 500; PEM, DER and PKCS#8 keep working, and P7B bundles are built
in-process, without the openssl binary."""
import base64
import json
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs7

from models import db
from tests.pqc_fixtures import fixture_bytes

PASSWORD = 'pqc-export-pw-123'
PROBLEM = 'urn:ucm:problem:unsupported-for-key-algorithm'
CERT = fixture_bytes('mldsa65-cert.pem')
SEED = fixture_bytes('mldsa65-seed.pem')


@pytest.fixture(scope='module')
def material(app):
    """An ML-DSA certificate row with its key, its enrolment by admin, and an ML-DSA CA."""
    from models import CA, Certificate, User
    from models.auth_certificate import AuthCertificate
    from utils.key_codec import store_pem_bytes
    tag = uuid.uuid4().hex[:8]
    cert = x509.load_pem_x509_certificate(CERT)
    subject = cert.subject.rfc4514_string()
    with app.app_context():
        row = Certificate(refid=f'pq-export-{tag}', descr=f'pq-export-{tag}',
                          crt=base64.b64encode(CERT).decode(), prv=store_pem_bytes(SEED),
                          subject=subject, issuer=subject, serial_number=str(cert.serial_number),
                          valid_from=cert.not_valid_before_utc, valid_to=cert.not_valid_after_utc)
        ca = CA(refid=f'pq-export-ca-{tag}', descr=f'pq-export-ca-{tag}', serial=0,
                crt=base64.b64encode(CERT).decode(), prv=store_pem_bytes(SEED),
                subject=subject, issuer=subject, serial_number=str(cert.serial_number),
                imported_from='manual')
        db.session.add_all([row, ca])
        db.session.commit()
        admin = User.query.filter_by(username='admin').first()
        enrolment = AuthCertificate(
            user_id=admin.id, cert_serial=row.serial_number, cert_pem=CERT,
            cert_subject=subject, cert_issuer=subject, cert_fingerprint='',
            name=f'pq-export-{tag}', enabled=True)
        db.session.add(enrolment)
        db.session.commit()
        ids = {'cert': row.id, 'ca': ca.id, 'enrolment': enrolment.id}
    yield ids
    with app.app_context():
        from models.key_recovery import KeyRecoveryRequest
        db.session.rollback()
        KeyRecoveryRequest.query.filter_by(cert_id=ids['cert']).delete()
        AuthCertificate.query.filter_by(id=ids['enrolment']).delete()
        Certificate.query.filter_by(id=ids['cert']).delete()
        CA.query.filter_by(id=ids['ca']).delete()
        db.session.commit()


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


def _route(path, fmt):
    def call(client, app, ids, **extra):
        return _post(client, path.format(**ids), {'format': fmt, 'password': PASSWORD, **extra})
    return call


def _converter(fmt):
    def call(client, app, ids, **extra):
        return _post(client, '/api/v2/tools/convert', {
            'pem': CERT.decode(), 'private_key': SEED.decode(), 'pkcs12_password': PASSWORD,
            'output_format': fmt, **extra})
    return call


def _key_recovery(client, app, ids, **extra):
    from models import SystemConfig
    with app.app_context():
        row = SystemConfig.query.filter_by(key='key_recovery_dual_control').first()
        if not row:
            row = SystemConfig(key='key_recovery_dual_control', value='')
            db.session.add(row)
        row.value = 'false'
        db.session.commit()
    r = _post(client, f"/api/v2/certificates/{ids['cert']}/key-recovery", {'reason': 'pq test'})
    assert r.status_code == 201, r.data
    rid = r.get_json()['data']['id']
    assert _post(client, f'/api/v2/key-recovery/{rid}/approve', {}).status_code == 200
    return _post(client, f'/api/v2/key-recovery/{rid}/recover', {'password': PASSWORD, **extra})


CONTAINER_SITES = {
    'certificate-pkcs12': (_route('/api/v2/certificates/{cert}/export', 'pkcs12'), 'PKCS#12'),
    'certificate-pfx': (_route('/api/v2/certificates/{cert}/export', 'pfx'), 'PKCS#12'),
    'certificate-jks': (_route('/api/v2/certificates/{cert}/export', 'jks'), 'JKS'),
    'ca-pkcs12': (_route('/api/v2/cas/{ca}/export', 'pkcs12'), 'PKCS#12'),
    'ca-pfx': (_route('/api/v2/cas/{ca}/export', 'pfx'), 'PKCS#12'),
    'ca-jks': (_route('/api/v2/cas/{ca}/export', 'jks'), 'JKS'),
    'user-certificate-pkcs12': (_route('/api/v2/user-certificates/{enrolment}/export', 'pkcs12'), 'PKCS#12'),
    'user-certificate-jks': (_route('/api/v2/user-certificates/{enrolment}/export', 'jks'), 'JKS'),
    'mtls-download': (_route('/api/v2/mtls/certificates/{enrolment}/download', 'pkcs12'), 'PKCS#12'),
    'converter-pkcs12': (_converter('pkcs12'), 'PKCS#12'),
    'converter-jks': (_converter('jks'), 'JKS'),
    'key-recovery': (_key_recovery, 'PKCS#12'),
}


@pytest.mark.parametrize('site', CONTAINER_SITES)
def test_key_containers_refuse_ml_dsa_with_a_stable_reason(site, auth_client, app, material):
    call, name = CONTAINER_SITES[site]
    r = call(auth_client, app, material)
    body = r.get_json()
    assert r.status_code == 400, (r.status_code, r.data[:300])
    assert body['type'] == PROBLEM, body
    assert body['details'] == {'reason': 'unsupported_for_key_algorithm',
                               'key_algorithm': 'ML-DSA-65', 'format': name}
    assert 'PEM' in body['message']


def test_trust_store_service_refuses_ml_dsa_pkcs12():
    from services.trust_store.trust_store_service import TrustStoreService
    from utils.algorithm_refusal import UnsupportedForKeyAlgorithm
    with pytest.raises(UnsupportedForKeyAlgorithm):
        TrustStoreService.export_pkcs12(CERT, SEED, PASSWORD)


@pytest.mark.parametrize('fmt,check', [
    ('pem', lambda data: b'BEGIN CERTIFICATE' in data and b'BEGIN PRIVATE KEY' in data),
    ('der', lambda data: x509.load_der_x509_certificate(data).public_bytes(
        serialization.Encoding.PEM) == CERT),
    ('key', lambda data: serialization.load_pem_private_key(data, None) is not None),
])
@pytest.mark.parametrize('target', ['certificates/{cert}', 'cas/{ca}'])
def test_other_formats_still_export(fmt, check, target, auth_client, material):
    r = _post(auth_client, f'/api/v2/{target.format(**material)}/export',
              {'format': fmt, 'include_key': True})
    assert r.status_code == 200, r.data[:300]
    assert check(r.data)


def test_converter_pem_and_der_still_work(auth_client, app, material):
    r = _converter('pem')(auth_client, app, material)
    assert r.status_code == 200 and 'BEGIN PRIVATE KEY' in r.get_json()['data']['data']


def test_export_formats_for_follows_the_key():
    from cryptography.hazmat.primitives.asymmetric import ec
    from utils.key_algorithms import export_formats_for
    mldsa_formats = export_formats_for(serialization.load_pem_private_key(SEED, None))
    assert {'pem', 'der', 'pkcs8', 'pkcs7'} <= set(mldsa_formats)
    assert not {'pkcs12', 'pfx', 'jks'} & set(mldsa_formats)
    assert 'pkcs12' in export_formats_for(ec.generate_private_key(ec.SECP256R1()))
    assert 'jks' not in export_formats_for('ML-DSA-44')


# ---------------------------------------------------------------- P7B

@pytest.fixture
def no_openssl(monkeypatch, tmp_path):
    """No openssl binary on PATH: a P7B must still be built."""
    monkeypatch.setenv('PATH', str(tmp_path))


P7B_SITES = {
    'certificate': lambda c, ids: _post(c, f"/api/v2/certificates/{ids['cert']}/export", {'format': 'p7b'}),
    'ca': lambda c, ids: _post(c, f"/api/v2/cas/{ids['ca']}/export", {'format': 'p7b'}),
    'certificates-all': lambda c, ids: _post(c, '/api/v2/certificates/export', {'format': 'p7b'}),
    'cas-all': lambda c, ids: _post(c, '/api/v2/cas/export', {'format': 'p7b'}),
    'certificates-bulk': lambda c, ids: _post(c, '/api/v2/certificates/bulk/export',
                                              {'ids': [ids['cert']], 'format': 'p7b'}),
    'cas-bulk': lambda c, ids: _post(c, '/api/v2/cas/bulk/export', {'ids': [ids['ca']], 'format': 'p7b'}),
}


@pytest.mark.parametrize('site', P7B_SITES)
def test_p7b_is_built_without_openssl(site, no_openssl, auth_client, material):
    r = P7B_SITES[site](auth_client, material)
    assert r.status_code == 200, r.data[:300]
    certs = pkcs7.load_der_pkcs7_certificates(r.data)
    assert x509.load_pem_x509_certificate(CERT) in certs


def test_converter_p7b_is_built_without_openssl(no_openssl, auth_client, app, material):
    r = _converter('pkcs7')(auth_client, app, material)
    assert r.status_code == 200, r.data[:300]
    data = r.get_json()['data']['data'].encode()
    assert pkcs7.load_pem_pkcs7_certificates(data) == [x509.load_pem_x509_certificate(CERT)]
