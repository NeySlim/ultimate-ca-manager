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
    from models import RevokedSerial
    with app.app_context():
        last_cert = db.session.query(db.func.max(Certificate.id)).scalar() or 0
        last_ca = db.session.query(db.func.max(CA.id)).scalar() or 0
        last_revoked = db.session.query(db.func.max(RevokedSerial.id)).scalar() or 0
    yield
    with app.app_context():
        # Certificate ids are reused once deleted: their revocation records go with them
        RevokedSerial.query.filter(RevokedSerial.id > last_revoked).delete()
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


@pytest.mark.parametrize('field', ['allow_empty_username', 'ignore_challenge_password',
                                   'csrattrs_legacy_encoding'])
@pytest.mark.parametrize('value', ['false', '0', 1, None])
def test_security_flags_take_only_a_boolean(auth_client, field, value):
    """A JSON string "false" is truthy: these flags turn a check off, so they take a boolean only."""
    r = auth_client.patch('/api/v2/est/config', json={field: value})
    assert r.status_code == 400, r.get_json()
    assert auth_client.get('/api/v2/est/config').get_json()['data'][field] is False


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


class TestOtherCaStatuses:
    """Only revocation and validity of another CA's certificate refuse it; a
    superseded or no longer recorded one stays judged by the TLS layer."""

    def test_not_yet_valid_record_of_another_ca_cannot_enrol(self, client, other_ca_leaf,
                                                            monkeypatch):
        _cert_id, leaf = other_ca_leaf('est-other-future.example.test')
        import services.cert.issued_lookup as issued_lookup
        monkeypatch.setattr(issued_lookup, 'utc_now', lambda: utc_now() - timedelta(days=2))
        csr, _ = _make_csr('future-victim.example.test')
        r = _post_csr(client, 'simpleenroll', csr, client_cert_pem=_pem(leaf))
        assert r.status_code == 403, r.data
        assert b'not yet valid' in r.data

    def test_superseded_certificate_of_another_ca_still_enrols(self, app, client, other_ca_leaf):
        cert_id, leaf = other_ca_leaf('est-other-archived.example.test')
        with app.app_context():
            db.session.get(Certificate, cert_id).archived = True
            db.session.commit()
        csr, _ = _make_csr('archived-device.example.test')
        r = _post_csr(client, 'simpleenroll', csr, client_cert_pem=_pem(leaf))
        assert r.status_code == 200, r.data

    def test_unrecorded_certificate_of_another_ca_still_enrols(self, app, client, other_ca_leaf):
        cert_id, leaf = other_ca_leaf('est-other-deleted.example.test')
        with app.app_context():
            db.session.delete(db.session.get(Certificate, cert_id))
            db.session.commit()
        csr, _ = _make_csr('deleted-device.example.test')
        r = _post_csr(client, 'simpleenroll', csr, client_cert_pem=_pem(leaf))
        assert r.status_code == 200, r.data


def test_a_stored_operation_name_in_another_case_is_not_served(app, client, est_config):
    with app.app_context():
        refid = db.session.get(CA, est_config['id']).refid
        _set_config('est_labels', json.dumps({'SimpleEnroll': refid}))
    try:
        assert client.get(f'{EST_BASE}/SimpleEnroll/cacerts').status_code == 404
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key='est_labels').delete()
            db.session.commit()


def test_an_ignored_label_is_not_listed_and_the_config_saves_back(app, auth_client, est_config):
    with app.app_context():
        refid = db.session.get(CA, est_config['id']).refid
        _set_config('est_labels', json.dumps({'SimpleEnroll': refid, 'served': refid}))
    try:
        labels = auth_client.get('/api/v2/est/config').get_json()['data']['labels']
        assert set(labels) == {'served'}
        r = auth_client.patch('/api/v2/est/config', json={'labels': labels})
        assert r.status_code == 200, r.data
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key='est_labels').delete()
            db.session.commit()


def _csr_with_challenge(cn, password):
    from cryptography.x509.oid import AttributeOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    ).add_attribute(AttributeOID.CHALLENGE_PASSWORD, password).sign(key, hashes.SHA256())


def _csr_with_multi_valued_attribute(cn, with_password):
    """A CSR whose attribute set holds one attribute with two values, which pyca
    refuses to read; re-signed with pyasn1 so the signature stays valid."""
    from pyasn1.codec.der import encoder as der_encoder
    from pyasn1_alt_modules import rfc2986, rfc5280
    from pyasn1.type import char
    from cryptography.hazmat.primitives.asymmetric import padding
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
    if with_password:
        from cryptography.x509.oid import AttributeOID
        builder = builder.add_attribute(AttributeOID.CHALLENGE_PASSWORD, b'A' * 16)
    der = builder.sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.DER)
    req, _ = der_decoder.decode(der, asn1Spec=rfc2986.CertificationRequest())
    info = req['certificationRequestInfo']
    attr = rfc5280.Attribute()
    attr['type'] = univ.ObjectIdentifier('1.3.6.1.4.1.99999.1')
    for i, text in enumerate(('one', 'two')):
        attr['values'][i] = der_encoder.encode(char.UTF8String(text))
    info['attributes'].append(attr)
    tbs = der_encoder.encode(info)
    req['signature'] = univ.BitString.fromOctetString(
        key.sign(tbs, padding.PKCS1v15(), hashes.SHA256()))
    return x509.load_der_x509_csr(der_encoder.encode(req))


def _post_with_binding(client, csr, binding=None):
    body = base64.b64encode(csr.public_bytes(serialization.Encoding.DER))
    kwargs = {'environ_overrides': {'ucm.tls_unique': binding}} if binding is not None else {}
    return client.post(f'{EST_BASE}/simpleenroll', data=body, headers=_basic_auth(),
                       content_type='application/pkcs10', **kwargs)


class TestTlsUniqueLinking:
    """RFC 7030 §3.5: a challengePassword carries the tls-unique value, which
    the server MUST verify when the client includes it."""

    BINDING = bytes(range(12))

    def test_unverifiable_binding_is_refused(self, client):
        csr = _csr_with_challenge('tls-unique-none.example.test', b'A' * 28)
        r = _post_with_binding(client, csr)
        assert r.status_code == 400, r.data
        assert r.mimetype == 'text/plain'
        assert b'tls-unique' in r.data

    def test_wrong_binding_is_refused(self, client):
        csr = _csr_with_challenge('tls-unique-wrong.example.test', b'A' * 16)
        r = _post_with_binding(client, csr, self.BINDING)
        assert r.status_code == 400, r.data
        assert b'does not match' in r.data

    def test_wrong_binding_through_a_trusted_proxy_names_the_proxy(self, client, monkeypatch):
        monkeypatch.setenv('UCM_TRUSTED_PROXIES', '127.0.0.1')
        csr = _csr_with_challenge('tls-unique-proxy.example.test', b'A' * 16)
        r = _post_with_binding(client, csr, self.BINDING)
        assert r.status_code == 400, r.data
        assert b'trusted proxy' in r.data

    def test_wrong_binding_from_a_direct_client_names_no_proxy(self, client, monkeypatch):
        monkeypatch.setenv('UCM_TRUSTED_PROXIES', '192.0.2.1')
        csr = _csr_with_challenge('tls-unique-direct.example.test', b'A' * 16)
        r = _post_with_binding(client, csr, self.BINDING)
        assert r.status_code == 400, r.data
        assert b'proxy' not in r.data

    @pytest.mark.parametrize('with_password', [False, True])
    def test_multi_valued_attribute(self, client, with_password):
        csr = _csr_with_multi_valued_attribute('multi-attr.example.test', with_password)
        r = _post_with_binding(client, csr, self.BINDING)
        if with_password:
            assert r.status_code == 400, r.data
            assert r.mimetype == 'text/plain'
            assert b'several values' in r.data
        else:
            _issued(r)

    def test_this_connection_binding_enrols(self, client):
        csr = _csr_with_challenge('tls-unique-ok.example.test', base64.b64encode(self.BINDING))
        _issued(_post_with_binding(client, csr, self.BINDING))

    def test_binding_is_ignored_when_configured(self, auth_client, client):
        r = auth_client.patch('/api/v2/est/config', json={'ignore_challenge_password': True})
        assert r.status_code == 200, r.get_json()
        try:
            assert auth_client.get('/api/v2/est/config').get_json()['data'][
                'ignore_challenge_password'] is True
            csr = _csr_with_challenge('tls-unique-ignored.example.test', b'a real secret')
            _issued(_post_with_binding(client, csr))
        finally:
            auth_client.patch('/api/v2/est/config', json={'ignore_challenge_password': False})


class TestRefusalReasons:
    """RFC 8951 §5.1: a rejection says why."""

    def test_signing_refusal_names_its_reason(self, app, client, create_ca, est_config):
        nc_ca = create_ca(cn='EST name-constrained CA', nameConstraintsExcluded=[
            {'type': 'dns', 'value': 'blocked.example.test'}])
        with app.app_context():
            _set_config('est_ca_refid', db.session.get(CA, nc_ca['id']).refid)
        try:
            csr, _ = _make_csr('www.blocked.example.test',
                               san_names=('www.blocked.example.test',))
            r = _post_csr(client, 'simpleenroll', csr, headers=_basic_auth())
        finally:
            with app.app_context():
                _set_config('est_ca_refid', db.session.get(CA, est_config['id']).refid)
        assert r.status_code == 400
        assert b'excluded by CA NameConstraints' in r.data

    def test_operator_side_value_error_stays_generic(self, client, monkeypatch):
        from services.ca_service import CAService

        def broken_key(*_args, **_kwargs):
            raise ValueError('Stored private key for CA abc is malformed or encrypted '
                             'with a different KEY_ENCRYPTION_KEY')
        monkeypatch.setattr(CAService, 'sign_csr_from_crypto', broken_key)
        csr, _ = _make_csr('broken-key.example.test')
        r = _post_csr(client, 'simpleenroll', csr, headers=_basic_auth())
        assert r.status_code == 400
        assert b'KEY_ENCRYPTION_KEY' not in r.data

    def test_unexpected_failure_stays_generic(self, client, monkeypatch):
        from services.ca_service import CAService

        def crash(*_args, **_kwargs):
            raise RuntimeError('internal detail')
        monkeypatch.setattr(CAService, 'sign_csr_from_crypto', crash)
        csr, _ = _make_csr('crash.example.test')
        r = _post_csr(client, 'simpleenroll', csr, headers=_basic_auth())
        assert r.status_code == 400
        assert b'internal detail' not in r.data

    def test_rate_limit_is_plain_text(self, client, monkeypatch):
        import security.rate_limiter as rate_limiter

        class Refusing:
            def check_rate_limit(self, ip, path):
                return False, {'retry_after': 7, 'limit': 1}
        monkeypatch.setattr(rate_limiter, 'get_rate_limiter', lambda: Refusing())
        r = client.get(f'{EST_BASE}/cacerts')
        assert r.status_code == 429
        assert r.mimetype == 'text/plain'
        assert r.headers['Retry-After'] == '7'


def test_reenrolment_of_a_certificate_without_san_adds_none(app, client, est_config):
    """RFC 7030 §4.2.2: a renewed certificate that had no SubjectAltName gets none."""
    from services.ca_service import CAService
    csr, _ = _make_csr('reenroll-bare')
    with app.app_context():
        ca = db.session.get(CA, est_config['id'])
        pem, _serial = CAService.sign_csr_from_crypto(
            ca=ca, csr=csr, validity_days=5, source='manual', override_san=[])
        db.session.commit()
    leaf = x509.load_pem_x509_certificate(pem.encode())
    assert _dns_names(leaf) == set()
    renew_csr, _ = _make_csr('reenroll-bare')
    renewed = _issued(_post_csr(client, 'simplereenroll', renew_csr, client_cert_pem=_pem(leaf)))
    with pytest.raises(x509.ExtensionNotFound):
        renewed.extensions.get_extension_for_class(x509.SubjectAlternativeName)


@pytest.fixture
def revoked_sub_ca_leaves(app, auth_client, create_ca, create_cert):
    """Under a sub-CA UCM then revokes: a stored leaf and one minted with its key."""
    from services.hsm.ca_key_loader import get_ca_signing_key

    def _make(tag):
        root = create_ca(cn=f'EST chain root {tag}')
        sub = create_ca(cn=f'EST chain sub {tag}', type='intermediate', parentCAId=root['id'])
        info = create_cert(cn=f'stored-{tag}.example.test', ca_id=sub['id'])
        with app.app_context():
            sub_row = db.session.get(CA, sub['id'])
            sub_cert = x509.load_pem_x509_certificate(base64.b64decode(sub_row.crt))
            stored = x509.load_pem_x509_certificate(
                base64.b64decode(db.session.get(Certificate, info['id']).crt))
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            now = utc_now()
            minted = x509.CertificateBuilder().subject_name(x509.Name(
                [x509.NameAttribute(NameOID.COMMON_NAME, f'minted-{tag}.example.test')])
            ).issuer_name(sub_cert.subject).public_key(key.public_key()).serial_number(
                x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5)
            ).not_valid_after(now + timedelta(days=30)).sign(
                get_ca_signing_key(sub_row), hashes.SHA256())
        r = auth_client.post(f"/api/v2/cas/{sub['id']}/revoke",
                             data=json.dumps({'reason': 'keyCompromise'}),
                             content_type='application/json')
        assert r.status_code == 200, r.data
        return stored, minted

    return _make


class TestPresentedCertificateUnderARevokedCa:
    """RFC 5280 §6.1.3(a)(3): every certificate of the path is checked, so a
    leaf whose issuing CA UCM revoked does not authenticate."""

    @pytest.mark.parametrize('which', [0, 1], ids=['stored', 'minted'])
    def test_cannot_enrol(self, client, revoked_sub_ca_leaves, which):
        leaf = revoked_sub_ca_leaves(f'enrol{which}')[which]
        csr, _ = _make_csr('www.chain-victim.example.test',
                           san_names=('www.chain-victim.example.test',))
        r = _post_csr(client, 'simpleenroll', csr, client_cert_pem=_pem(leaf))
        assert r.status_code == 403, r.data
        assert b'issuer has been revoked' in r.data

    def test_cannot_use_serverkeygen(self, client, revoked_sub_ca_leaves):
        leaf = revoked_sub_ca_leaves('keygen')[1]
        csr, _ = _make_csr('keygen-chain-victim.example.test')
        r = _post_csr(client, 'serverkeygen', csr, client_cert_pem=_pem(leaf))
        assert r.status_code == 403, r.data

    @pytest.mark.parametrize('which', [0, 1], ids=['stored', 'minted'])
    def test_cannot_be_enrolled_for_mtls(self, app, auth_client, revoked_sub_ca_leaves, which):
        leaf = revoked_sub_ca_leaves(f'mtls{which}')[which]
        r = auth_client.post('/api/v2/mtls/enroll', json={}, environ_overrides={
            'peercert': leaf.public_bytes(serialization.Encoding.DER)})
        assert r.status_code == 400, r.get_json()
        assert 'issuer has been revoked' in r.get_json()['message']


class TestMtlsUnderARevokedCaAboveTheIssuer:
    """RFC 5280 §6.1.3(a)(3): a CA revoked above the leaf's issuer closes the
    mTLS login and /enroll-import, as it closes /enroll."""

    @pytest.fixture
    def chain(self, app, auth_client, create_ca, create_cert):
        from models.auth_certificate import AuthCertificate
        with app.app_context():
            last = db.session.query(db.func.max(AuthCertificate.id)).scalar() or 0
        root = create_ca(cn='mTLS chain root')
        mid = create_ca(cn='mTLS chain L1', type='intermediate', parentCAId=root['id'])
        low = create_ca(cn='mTLS chain L2', type='intermediate', parentCAId=mid['id'])

        def leaf(cn):
            info = create_cert(cn=cn, ca_id=low['id'])
            with app.app_context():
                return base64.b64decode(db.session.get(Certificate, info['id']).crt).decode()

        def revoke_l1():
            r = auth_client.post(f"/api/v2/cas/{mid['id']}/revoke",
                                 data=json.dumps({'reason': 'cACompromise'}),
                                 content_type='application/json')
            assert r.status_code == 200, r.data
        yield leaf, revoke_l1
        with app.app_context():  # an admin enrolment would change later mTLS settings tests
            AuthCertificate.query.filter(AuthCertificate.id > last).delete()
            db.session.commit()

    def test_login_is_refused(self, app, auth_client, chain):
        leaf, revoke_l1 = chain
        pem = leaf('mtls-chain-login@example.test')
        r = auth_client.post('/api/v2/mtls/enroll-import', json={'pem': pem, 'name': 'chain'})
        assert r.status_code == 201, r.get_json()
        der = x509.load_pem_x509_certificate(pem.encode()).public_bytes(serialization.Encoding.DER)
        login = app.test_client()
        assert login.post('/api/v2/auth/login/mtls', environ_overrides={'peercert': der}).status_code == 200
        revoke_l1()
        r = app.test_client().post('/api/v2/auth/login/mtls', environ_overrides={'peercert': der})
        assert r.status_code == 401, r.get_json()

    def test_enroll_import_is_refused(self, auth_client, chain):
        leaf, revoke_l1 = chain
        pem = leaf('mtls-chain-import@example.test')
        revoke_l1()
        r = auth_client.post('/api/v2/mtls/enroll-import', json={'pem': pem, 'name': 'chain'})
        assert r.status_code == 400, r.get_json()
        assert 'issuer has been revoked' in r.get_json()['message']


def test_serverkeygen_verifies_the_tls_unique_binding(client):
    """RFC 7030 §3.5 and §4.4.1: serverkeygen checks the CSR's tls-unique too."""
    csr = _csr_with_challenge('keygen-tls-unique.example.test', b'A' * 16)
    body = base64.b64encode(csr.public_bytes(serialization.Encoding.DER))
    r = client.post(f'{EST_BASE}/serverkeygen', data=body, headers=_basic_auth(),
                    content_type='application/pkcs10',
                    environ_overrides={'ucm.tls_unique': bytes(range(12))})
    assert r.status_code == 400, r.data
    assert b'does not match' in r.data


@pytest.mark.parametrize('path', ['fullcmc', 'arbitrary-label/fullcmc'])
def test_fullcmc_is_not_implemented(client, path):
    """RFC 7030 §3.2.2: Full CMC is optional; its absence is answered 501, not 405 HTML."""
    r = client.post(f'{EST_BASE}/{path}', data=b'MAo=', content_type='application/pkcs7-mime')
    assert r.status_code == 501, r.data
    assert r.mimetype == 'text/plain'


def test_reenroll_without_certificate_offers_no_basic(client):
    """RFC 7030 §3.2.3: WWW-Authenticate offers Basic; simplereenroll takes none."""
    csr, _ = _make_csr('reenroll-no-cert.example.test')
    r = _post_csr(client, 'simplereenroll', csr, headers=_basic_auth())
    assert r.status_code == 403, r.data
    assert 'WWW-Authenticate' not in r.headers
    assert r.mimetype == 'text/plain'
