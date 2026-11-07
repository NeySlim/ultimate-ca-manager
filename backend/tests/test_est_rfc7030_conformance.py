"""EST behaviour required by RFC 7030 (§3.2.2, §3.2.3, §3.3.2, §4.2.2, §4.2.3),
RFC 8951 §5 and RFC 9908 §3.2/§5.2, beyond the base interoperability tests."""
import base64
import json
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID
from pyasn1.codec.der import decoder as der_decoder
from pyasn1.type import univ

from models import CA, Certificate, db
from models.system_config import SystemConfig
from utils.datetime_utils import utc_now
from tests.test_est_rfc7030 import (  # noqa: F401
    EST_BASE, EST_PASSWORD, _basic_auth, _make_client_certificate, _make_csr, _post_csr,
    _set_config, est_config,
)


@pytest.fixture(autouse=True, scope='module')
def _rows_stay_in_this_module(app):
    with app.app_context():
        last_cert = db.session.query(db.func.max(Certificate.id)).scalar() or 0
        last_ca = db.session.query(db.func.max(CA.id)).scalar() or 0
    yield
    with app.app_context():
        Certificate.query.filter(Certificate.id > last_cert).delete()
        CA.query.filter(CA.id > last_ca).delete()
        db.session.commit()


@pytest.fixture(autouse=True)
def _est_on(app, est_config):
    with app.app_context():
        _set_config('est_enabled', 'true')
    yield


def _pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _issued(response):
    assert response.status_code == 200, response.data
    return pkcs7.load_der_pkcs7_certificates(base64.b64decode(response.data))[0]


def _dns_names(cert):
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return set()
    return set(ext.value.get_values_for_type(x509.DNSName))


@pytest.fixture
def other_ca_leaf(app, create_ca, create_cert):
    """A certificate a CA other than the EST CA issued, as a stored row."""
    def _make(cn):
        ca = create_ca(cn=f'EST other CA {cn}')
        info = create_cert(cn=cn, ca_id=ca['id'])
        with app.app_context():
            row = db.session.get(Certificate, info['id'])
            leaf = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        return info['id'], leaf

    return _make


class TestPresentedCertificateOfAnotherCa:
    """RFC 7030 §3.3.2 → RFC 5280 §6.1.3: a certificate UCM revoked does not
    authenticate, whichever of its CAs issued it."""

    def test_revoked_by_another_ca_cannot_enrol(self, client, auth_client, other_ca_leaf):
        cert_id, leaf = other_ca_leaf('est-other-revoked.example.test')
        r = auth_client.post(f'/api/v2/certificates/{cert_id}/revoke',
                             data=json.dumps({'reason': 'keyCompromise'}),
                             content_type='application/json')
        assert r.status_code == 200, r.data
        csr, _ = _make_csr('www.victim.example.test', san_names=('www.victim.example.test',))
        r = _post_csr(client, 'simpleenroll', csr, client_cert_pem=_pem(leaf))
        assert r.status_code == 403, r.data
        assert b'revoked' in r.data

    def test_revoked_by_another_ca_cannot_use_serverkeygen(self, client, auth_client,
                                                           other_ca_leaf):
        cert_id, leaf = other_ca_leaf('est-other-keygen.example.test')
        r = auth_client.post(f'/api/v2/certificates/{cert_id}/revoke',
                             data=json.dumps({'reason': 'keyCompromise'}),
                             content_type='application/json')
        assert r.status_code == 200, r.data
        csr, _ = _make_csr('keygen-victim.example.test')
        r = _post_csr(client, 'serverkeygen', csr, client_cert_pem=_pem(leaf))
        assert r.status_code == 403, r.data

    def test_expired_record_of_another_ca_cannot_enrol(self, app, client, other_ca_leaf):
        cert_id, leaf = other_ca_leaf('est-other-expired.example.test')
        with app.app_context():
            db.session.get(Certificate, cert_id).valid_to = utc_now() - timedelta(days=1)
            db.session.commit()
        csr, _ = _make_csr('expired-victim.example.test')
        r = _post_csr(client, 'simpleenroll', csr, client_cert_pem=_pem(leaf))
        assert r.status_code == 403, r.data
        assert b'expired' in r.data

    def test_valid_certificate_of_another_ca_still_enrols(self, client, other_ca_leaf):
        _cert_id, leaf = other_ca_leaf('est-other-valid.example.test')
        csr, _ = _make_csr('other-valid-device.example.test')
        assert _post_csr(client, 'simpleenroll', csr,
                         client_cert_pem=_pem(leaf)).status_code == 200

    def test_certificate_of_an_authority_unknown_here_stays_judged_by_tls(self, client):
        _cert, _key, pem = _make_client_certificate('manufacturer-device')
        csr, _ = _make_csr('manufacturer-device.example.test')
        assert _post_csr(client, 'simpleenroll', csr, client_cert_pem=pem).status_code == 200


def test_mtls_enroll_refuses_a_revoked_presented_certificate(app, auth_client, other_ca_leaf):
    cert_id, leaf = other_ca_leaf('mtls-enroll-revoked.example.test')
    r = auth_client.post(f'/api/v2/certificates/{cert_id}/revoke',
                         data=json.dumps({'reason': 'keyCompromise'}),
                         content_type='application/json')
    assert r.status_code == 200, r.data
    from models.auth_certificate import AuthCertificate
    with app.app_context():
        before = AuthCertificate.query.count()
    r = auth_client.post('/api/v2/mtls/enroll', json={},
                         environ_overrides={'peercert': leaf.public_bytes(serialization.Encoding.DER)})
    assert r.status_code == 400, r.get_json()
    assert 'revoked' in r.get_json()['message']
    with app.app_context():
        assert AuthCertificate.query.count() == before


class TestReenrollWithoutSan:
    """RFC 7030 §4.2.2: the renewed certificate keeps the SubjectAltName of the
    certificate being renewed when the CSR omits it."""

    def test_csr_without_san_keeps_the_renewed_certificate_names(self, client, est_config):
        csr, _ = _make_csr('reenroll-nosan', san_names=('dev1.reenroll.example.test',))
        leaf = _issued(_post_csr(client, 'simpleenroll', csr, headers=_basic_auth()))
        assert _dns_names(leaf) == {'dev1.reenroll.example.test'}
        renew_csr, _ = _make_csr('reenroll-nosan')
        renewed = _issued(_post_csr(client, 'simplereenroll', renew_csr,
                                    client_cert_pem=_pem(leaf)))
        assert _dns_names(renewed) == {'dev1.reenroll.example.test'}


class TestCsrAttrsEncoding:
    """RFC 9908 §3.2: an extensionRequest value is one Extensions; an OID asked
    for without a value is listed on its own (§5.2)."""

    def _decoded(self, client):
        r = client.get(f'{EST_BASE}/csrattrs')
        assert r.status_code == 200
        attrs, rest = der_decoder.decode(base64.b64decode(r.data))
        assert rest == b''
        return attrs

    def test_extensions_are_asked_for_as_bare_oids(self, client):
        attrs = self._decoded(client)
        assert all(isinstance(item, univ.ObjectIdentifier) for item in attrs)
        assert {str(item) for item in attrs} == {'2.5.29.15', '2.5.29.17', '2.5.29.37'}

    def test_extension_request_never_holds_bare_oids(self, client):
        from asn1crypto import csr as asn1_csr
        r = client.get(f'{EST_BASE}/csrattrs')
        raw = base64.b64decode(r.data)
        # Every extensionRequest an RFC 9908 decoder meets must parse as Extensions
        attrs, _ = der_decoder.decode(raw)
        from pyasn1.codec.der import encoder as der_encoder
        for item in attrs:
            if isinstance(item, univ.ObjectIdentifier):
                continue
            attribute = asn1_csr.CRIAttribute.load(der_encoder.encode(item))
            attribute['values'].native  # raises on an OID where Extensions belongs

    def test_legacy_encoding_stays_available(self, app, client):
        with app.app_context():
            _set_config('est_csrattrs_legacy_encoding', 'true')
        try:
            attrs = self._decoded(client)
            assert len(attrs) == 1 and str(attrs[0][0]) == '1.2.840.113549.1.9.14'
            assert {str(oid) for oid in attrs[0][1]} == {'2.5.29.15', '2.5.29.17', '2.5.29.37'}
        finally:
            with app.app_context():
                SystemConfig.query.filter_by(key='est_csrattrs_legacy_encoding').delete()
                db.session.commit()

    def test_legacy_encoding_is_a_setting(self, auth_client):
        try:
            r = auth_client.patch('/api/v2/est/config', json={'csrattrs_legacy_encoding': True})
            assert r.status_code == 200, r.get_json()
            assert auth_client.get('/api/v2/est/config').get_json()['data'][
                'csrattrs_legacy_encoding'] is True
        finally:
            auth_client.patch('/api/v2/est/config', json={'csrattrs_legacy_encoding': False})


class TestPlainTextErrors:
    """RFC 8951 §5: an error carries a human-readable plain-text message."""

    def test_unreadable_csr_is_explained_in_plain_text(self, client):
        r = client.post(f'{EST_BASE}/simpleenroll', data=b'!!!not base64!!!',
                        headers=_basic_auth(), content_type='application/pkcs10')
        assert r.status_code == 400
        assert r.mimetype == 'text/plain'
        assert b'base64' in r.data

    def test_der_that_is_not_a_csr_is_explained(self, client):
        r = client.post(f'{EST_BASE}/simpleenroll', data=base64.b64encode(b'\x30\x03\x02\x01\x01'),
                        headers=_basic_auth(), content_type='application/pkcs10')
        assert r.status_code == 400
        assert r.mimetype == 'text/plain'
        assert b'PKCS#10' in r.data

    def test_authentication_failure_is_plain_text(self, client):
        csr, _ = _make_csr()
        r = _post_csr(client, 'simpleenroll', csr)
        assert r.status_code == 401
        assert r.mimetype == 'text/plain'


class TestOperationNamesAreNotLabels:
    """RFC 7030 §3.2.2: a CA label MUST NOT be an operation path segment."""

    @pytest.mark.parametrize('label', ['simpleenroll', 'CACERTS', 'fullcmc', 'csrattrs'])
    def test_api_refuses_an_operation_name(self, auth_client, est_config, label):
        with auth_client.application.app_context():
            refid = db.session.get(CA, est_config['id']).refid
        r = auth_client.patch('/api/v2/est/config', json={'labels': {label: refid}})
        assert r.status_code == 400, r.get_json()

    def test_a_stored_operation_name_is_not_served(self, app, client, est_config):
        with app.app_context():
            refid = db.session.get(CA, est_config['id']).refid
            _set_config('est_labels', json.dumps({'simpleenroll': refid}))
        try:
            assert client.get(f'{EST_BASE}/simpleenroll/cacerts').status_code == 404
        finally:
            with app.app_context():
                SystemConfig.query.filter_by(key='est_labels').delete()
                db.session.commit()


class TestBasicWithoutUsername:
    """RFC 7030 §3.2.3: a client MAY send an empty username with a password."""

    def _token(self, username, password):
        return {'Authorization': 'Basic ' + base64.b64encode(
            f'{username}:{password}'.encode()).decode()}

    def test_empty_username_refused_unless_allowed(self, client):
        csr, _ = _make_csr('password-only.example.test')
        assert _post_csr(client, 'simpleenroll', csr,
                         headers=self._token('', EST_PASSWORD)).status_code == 401

    def test_empty_username_accepted_when_allowed(self, app, client, auth_client):
        r = auth_client.patch('/api/v2/est/config', json={'allow_empty_username': True})
        assert r.status_code == 200, r.get_json()
        try:
            assert auth_client.get('/api/v2/est/config').get_json()['data'][
                'allow_empty_username'] is True
            csr, _ = _make_csr('password-only.example.test')
            assert _post_csr(client, 'simpleenroll', csr,
                             headers=self._token('', EST_PASSWORD)).status_code == 200
            assert _post_csr(client, 'simpleenroll', csr,
                             headers=self._token('', 'wrong')).status_code == 401
            # The configured username keeps working
            assert _post_csr(client, 'simpleenroll', csr, headers=_basic_auth()).status_code == 200
        finally:
            auth_client.patch('/api/v2/est/config', json={'allow_empty_username': False})


def test_a_key_revoked_as_compromised_is_not_certified_again(client, auth_client, other_ca_leaf,
                                                             app):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'compromised-first.example.test')])
    ).sign(key, hashes.SHA256())
    first = _issued(_post_csr(client, 'simpleenroll', csr, headers=_basic_auth()))
    with app.app_context():
        row = Certificate.query.filter_by(serial_number=str(first.serial_number)).first()
        cert_id = row.id
    r = auth_client.post(f'/api/v2/certificates/{cert_id}/revoke',
                         data=json.dumps({'reason': 'keyCompromise'}),
                         content_type='application/json')
    assert r.status_code == 200, r.data
    reuse = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'compromised-reuse.example.test')])
    ).sign(key, hashes.SHA256())
    r = _post_csr(client, 'simpleenroll', reuse, headers=_basic_auth())
    assert r.status_code == 400, r.data
    assert b'compromised' in r.data
