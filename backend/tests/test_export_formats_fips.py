"""FIPS mode refuses the export formats built on algorithms outside the
module: the PKCS#12 legacy profile (3DES, SHA-1) and JKS (pyjks). Every
route answers a 400 with the FIPS problem type; modern PKCS#12 stays."""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import fips_mode
from fips_mode import FipsRestricted
from models import db

PASSWORD = 'fips-export-pw-123'
LEGACY_REFUSAL = 'PKCS#12 legacy encryption (3DES/SHA-1) not available in FIPS mode'
JKS_REFUSAL = 'JKS export not available in FIPS mode'


@pytest.fixture
def fips_on(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)


@pytest.fixture
def fips_off(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)


@pytest.fixture(scope='module')
def material(app, create_ca, create_cert):
    """A certificate, a CA and an mTLS enrolment of the certificate by admin."""
    from models import Certificate, User
    from models.auth_certificate import AuthCertificate
    ca = create_ca(cn='FIPS export CA')
    cert = create_cert(cn='fips-export.example.com')
    with app.app_context():
        row = db.session.get(Certificate, cert['id'])
        admin = User.query.filter_by(username='admin').first()
        enrolment = AuthCertificate(
            user_id=admin.id, cert_serial=row.serial_number,
            cert_pem=base64.b64decode(row.crt),
            cert_subject=row.subject or 'CN=fips-export.example.com',
            cert_issuer=row.issuer, cert_fingerprint='', name='fips-export', enabled=True)
        db.session.add(enrolment)
        db.session.commit()
        enrolment_id = enrolment.id
    yield {'ca': ca['id'], 'cert': cert['id'], 'enrolment': enrolment_id}
    with app.app_context():
        stale = db.session.get(AuthCertificate, enrolment_id)
        if stale:
            db.session.delete(stale)
            db.session.commit()


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


def _recover(client, app, cert_id, **extra):
    """Open, approve and collect a key recovery request for ``cert_id``."""
    from models import SystemConfig
    with app.app_context():
        row = SystemConfig.query.filter_by(key='key_recovery_dual_control').first()
        if not row:
            row = SystemConfig(key='key_recovery_dual_control', value='')
            db.session.add(row)
        row.value = 'false'
        db.session.commit()
    r = _post(client, f'/api/v2/certificates/{cert_id}/key-recovery', {'reason': 'fips test'})
    assert r.status_code == 201, r.data
    rid = r.get_json()['data']['id']
    assert _post(client, f'/api/v2/key-recovery/{rid}/approve', {}).status_code == 200
    return _post(client, f'/api/v2/key-recovery/{rid}/recover', {'password': PASSWORD, **extra})


def _converter_input():
    key = rsa.generate_private_key(65537, 2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'fips-convert.test')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    return {
        'pem': cert.public_bytes(serialization.Encoding.PEM).decode(),
        'private_key': key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()).decode(),
        'pkcs12_password': PASSWORD,
    }


def _route(path, fmt):
    """A request builder for an export route taking ``format`` and ``password``."""
    def call(client, app, ids, **extra):
        url = path.format(**ids)
        return _post(client, url, {'format': fmt, 'password': PASSWORD, **extra})
    return call


def _converter(fmt):
    def call(client, app, ids, **extra):
        return _post(client, '/api/v2/tools/convert', {**_converter_input(), 'output_format': fmt, **extra})
    return call


def _key_recovery(client, app, ids, **extra):
    return _recover(client, app, ids['cert'], **extra)


PKCS12_SITES = {
    'certificate-pkcs12': _route('/api/v2/certificates/{cert}/export', 'pkcs12'),
    'certificate-pfx': _route('/api/v2/certificates/{cert}/export', 'pfx'),
    'ca-pkcs12': _route('/api/v2/cas/{ca}/export', 'pkcs12'),
    'ca-pfx': _route('/api/v2/cas/{ca}/export', 'pfx'),
    'user-certificate-pkcs12': _route('/api/v2/user-certificates/{enrolment}/export', 'pkcs12'),
    'user-certificate-pfx': _route('/api/v2/user-certificates/{enrolment}/export', 'pfx'),
    'mtls-download': _route('/api/v2/mtls/certificates/{enrolment}/download', 'pkcs12'),
    'key-recovery': _key_recovery,
}

JKS_SITES = {
    'certificate-jks': _route('/api/v2/certificates/{cert}/export', 'jks'),
    'ca-jks': _route('/api/v2/cas/{ca}/export', 'jks'),
    'user-certificate-jks': _route('/api/v2/user-certificates/{enrolment}/export', 'jks'),
    'converter-jks': _converter('jks'),
}


def _assert_refused(response, message):
    body = response.get_json()
    assert response.status_code == 400, (response.status_code, response.data[:300])
    assert body['type'] == fips_mode.PROBLEM_TYPE, body
    assert body['message'] == message, body


@pytest.mark.parametrize('site', PKCS12_SITES)
def test_legacy_pkcs12_is_refused_in_fips_mode(site, fips_on, auth_client, app, material):
    _assert_refused(PKCS12_SITES[site](auth_client, app, material, legacy=True), LEGACY_REFUSAL)


@pytest.mark.parametrize('site', PKCS12_SITES)
def test_modern_pkcs12_stays_in_fips_mode(site, fips_on, auth_client, app, material):
    r = PKCS12_SITES[site](auth_client, app, material)
    assert r.status_code == 200, r.data[:300]


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('site', PKCS12_SITES)
def test_pkcs12_unchanged_outside_fips_mode(site, legacy, fips_off, auth_client, app, material):
    r = PKCS12_SITES[site](auth_client, app, material, legacy=legacy)
    assert r.status_code == 200, r.data[:300]


@pytest.mark.parametrize('site', JKS_SITES)
def test_jks_is_refused_in_fips_mode(site, fips_on, auth_client, app, material):
    _assert_refused(JKS_SITES[site](auth_client, app, material), JKS_REFUSAL)


@pytest.mark.parametrize('site', JKS_SITES)
def test_jks_unchanged_outside_fips_mode(site, fips_off, auth_client, app, material):
    r = JKS_SITES[site](auth_client, app, material)
    assert r.status_code == 200, r.data[:300]


def test_converter_pkcs12_stays_in_fips_mode(fips_on, auth_client, app, material):
    r = _converter('pkcs12')(auth_client, app, material)
    assert r.status_code == 200, r.data[:300]


# Service helpers no route calls today: they share the same encryption choice.
def _service_exports(material):
    from services.ca.ca_service import CAService
    from services.cert.service import CertificateService
    return {
        'certificate-service': lambda legacy: CertificateService.export_certificate_with_options(
            material['cert'], 'pkcs12', password=PASSWORD, legacy=legacy),
        'ca-service': lambda legacy: CAService.export_ca_with_options(
            material['ca'], 'pkcs12', password=PASSWORD, legacy=legacy),
    }


@pytest.mark.parametrize('site', ['certificate-service', 'ca-service'])
def test_service_layer_refuses_legacy_in_fips_mode(site, fips_on, app, material):
    with app.app_context():
        export = _service_exports(material)[site]
        assert export(False)[:1] == b'\x30'
        with pytest.raises(FipsRestricted, match=r'PKCS#12 legacy encryption'):
            export(True)
