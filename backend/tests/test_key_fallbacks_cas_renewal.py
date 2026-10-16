"""No key request silently becomes RSA-2048: CA creation, the CA detail view,
in-place renewal and the Microsoft CA rekey all keep or refuse the algorithm
they were given."""

import base64
import json
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed25519, rsa
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db
from utils.key_codec import load_pem_bytes

CAS = '/api/v2/cas'


@pytest.fixture
def created(auth_client):
    """Ids of the CAs and certificates a test creates, deleted afterwards."""
    ids = {'cas': [], 'certs': []}
    yield ids
    for cert_id in ids['certs']:
        auth_client.post(f'/api/v2/certificates/{cert_id}/revoke', data=json.dumps(
            {'reason': 'cessationOfOperation'}), content_type='application/json')
        assert auth_client.delete(f'/api/v2/certificates/{cert_id}').status_code in (200, 204)
    for ca_id in reversed(ids['cas']):
        assert auth_client.delete(f'{CAS}/{ca_id}').status_code in (200, 204)


def _post_ca(auth_client, created, cn, **key_fields):
    body = {'type': 'root', 'commonName': cn, 'organization': 'Key Test', 'country': 'US',
            'validityYears': 2, **key_fields}
    r = auth_client.post(CAS, data=json.dumps(body), content_type='application/json')
    if r.status_code in (200, 201):
        created['cas'].append(r.get_json()['data']['id'])
    return r


def _ca_public_key(app, ca_id):
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        return x509.load_pem_x509_certificate(base64.b64decode(ca.crt)).public_key()


class TestCreateCaKey:
    @pytest.mark.parametrize('algo, size, curve', [
        ('EC', 'secp384r1', 'secp384r1'),
        ('ec', 'secp521r1', 'secp521r1'),
        ('ECDSA', 'prime256v1', 'secp256r1'),
        ('ecdsa', 'P-384', 'secp384r1'),
    ])
    def test_ec_spellings_give_the_requested_curve(self, app, auth_client, created, algo, size, curve):
        r = _post_ca(auth_client, created, f'EC {algo} {size} CA', keyAlgo=algo, keySize=size)
        assert r.status_code == 201, r.get_json()
        key = _ca_public_key(app, r.get_json()['data']['id'])
        assert isinstance(key, ec.EllipticCurvePublicKey) and key.curve.name == curve

    @pytest.mark.parametrize('size', [4096, '4096'])
    def test_lowercase_rsa_keeps_its_size(self, app, auth_client, created, size):
        r = _post_ca(auth_client, created, f'rsa {size!r} CA', keyAlgo='rsa', keySize=size)
        assert r.status_code == 201, r.get_json()
        key = _ca_public_key(app, r.get_json()['data']['id'])
        assert isinstance(key, rsa.RSAPublicKey) and key.key_size == 4096

    def test_key_type_alias_is_honoured(self, app, auth_client, created):
        r = _post_ca(auth_client, created, 'keyType EC CA', keyType='EC', keySize='secp384r1')
        assert r.status_code == 201, r.get_json()
        key = _ca_public_key(app, r.get_json()['data']['id'])
        assert isinstance(key, ec.EllipticCurvePublicKey) and key.curve.name == 'secp384r1'

    @pytest.mark.parametrize('fields, family, size', [
        ({'keyType': 'RSA-4096'}, 'RSA', 4096),
        ({'keyType': 'EC-P384'}, 'EC', 384),
        ({'keyAlgo': 'ec-p521'}, 'EC', 521),
    ])
    def test_a_full_key_label_names_size_and_curve(self, app, auth_client, created, fields, family, size):
        # Scripts sent keyType 'RSA-2048'-style labels; they no longer fall back to RSA-2048
        r = _post_ca(auth_client, created, f'Label {family} {size} CA', **fields)
        assert r.status_code == 201, r.get_json()
        key = _ca_public_key(app, r.get_json()['data']['id'])
        assert key.key_size == size
        assert isinstance(key, rsa.RSAPublicKey if family == 'RSA' else ec.EllipticCurvePublicKey)

    @pytest.mark.parametrize('fields', [
        {'keyAlgo': 'Ed25519'},
        {'keyAlgo': 'DSA', 'keySize': 2048},
        {'keyAlgo': 'magic'},
        {'keyAlgo': 'RSA', 'keySize': 1024},
        {'keyAlgo': 'RSA', 'keySize': 'secp384r1'},
        {'keyAlgo': 'EC', 'keySize': 'secp256k1'},
        {'keyAlgo': 'EC', 'keySize': 2048},
        {'keyType': 'Ed25519'},
        {'keySize': 4096},
        {'keyAlgo': 'RSA', 'keyType': 'EC'},
    ])
    def test_unusable_requests_are_refused(self, auth_client, created, fields):
        r = _post_ca(auth_client, created, 'Refused key CA', **fields)
        assert r.status_code == 400, r.get_json()
        assert re.search(r'keyAlgo|keySize|key size|curve', r.get_json()['message']), r.get_json()

    def test_no_key_field_keeps_the_documented_default(self, app, auth_client, created):
        r = _post_ca(auth_client, created, 'Default key CA')
        assert r.status_code == 201, r.get_json()
        key = _ca_public_key(app, r.get_json()['data']['id'])
        assert isinstance(key, rsa.RSAPublicKey) and key.key_size == 2048


class TestCaDetailKey:
    def test_rsa_4096_reports_its_size(self, auth_client, created):
        ca_id = _post_ca(auth_client, created, 'Detail RSA CA', keyAlgo='RSA', keySize=4096).get_json()['data']['id']
        data = auth_client.get(f'{CAS}/{ca_id}').get_json()['data']
        assert (data['keyAlgo'], data['keySize']) == ('RSA', 4096)

    def test_p384_reports_ec(self, auth_client, created):
        ca_id = _post_ca(auth_client, created, 'Detail EC CA', keyAlgo='ECDSA',
                         keySize='secp384r1').get_json()['data']['id']
        data = auth_client.get(f'{CAS}/{ca_id}').get_json()['data']
        assert (data['keyAlgo'], data['keySize']) == ('EC', 384)


def _signed_leaf(app, ca_id, key, cn):
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        ca_cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
        ca_key = serialization.load_pem_private_key(load_pem_bytes(ca.prv, context='test'), None)
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .issuer_name(ca_cert.subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    return cert.public_bytes(serialization.Encoding.PEM) + key_pem


class TestRenewalKeepsTheFamily:
    def test_dsa_certificate_is_refused_and_left_intact(self, app, auth_client, created):
        ca_id = _post_ca(auth_client, created, 'DSA renewal CA').get_json()['data']['id']
        pem = _signed_leaf(app, ca_id, dsa.generate_private_key(2048), 'dsa-renew.example.test')
        r = auth_client.post('/api/v2/certificates/import',
                             data={'pem_content': pem.decode(), 'name': 'dsa-renew'},
                             content_type='multipart/form-data')
        assert r.status_code in (200, 201), r.get_json()
        cert_id = r.get_json()['data']['id']
        created['certs'].append(cert_id)
        with app.app_context():
            row = db.session.get(Certificate, cert_id)
            assert row.prv, 'the import must keep the key for the renewal to be attempted'
            before = (row.crt, row.prv, row.serial_number, row.valid_to)

        r = auth_client.post(f'/api/v2/certificates/{cert_id}/renew',
                             data=json.dumps({}), content_type='application/json')
        assert r.status_code == 400, r.get_json()
        assert 'cannot be regenerated' in r.get_json()['message'], r.get_json()
        with app.app_context():
            db.session.expire_all()
            row = db.session.get(Certificate, cert_id)
            assert (row.crt, row.prv, row.serial_number, row.valid_to) == before


class TestMscaRekey:
    @staticmethod
    def _row(key, cn='rekey.example.test'):
        now = datetime.now(timezone.utc)
        issuer_key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        cert = (
            x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + timedelta(days=30))
            .sign(issuer_key, hashes.SHA256())
        )
        return SimpleNamespace(
            crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
            csr=None, prv=None, san_dns=json.dumps([cn]), san_ip=None, san_email=None,
            san_uri=None, san_upn_list=[])

    @pytest.mark.parametrize('key, check', [
        (ec.generate_private_key(ec.SECP384R1()),
         lambda k: isinstance(k, ec.EllipticCurvePublicKey) and k.curve.name == 'secp384r1'),
        (ec.generate_private_key(ec.SECP521R1()),
         lambda k: isinstance(k, ec.EllipticCurvePublicKey) and k.curve.name == 'secp521r1'),
        (rsa.generate_private_key(65537, 3072),
         lambda k: isinstance(k, rsa.RSAPublicKey) and k.key_size == 3072),
    ], ids=['P-384', 'P-521', 'RSA-3072'])
    def test_rekey_reproduces_the_original_key(self, app, key, check):
        from api.v2.msca import _generate_rekey_csr
        row = self._row(key)
        with app.app_context():
            csr_pem = _generate_rekey_csr(row)
        assert check(x509.load_pem_x509_csr(csr_pem.encode()).public_key())
        assert row.prv

    @pytest.mark.parametrize('key', [
        ed25519.Ed25519PrivateKey.generate(),
        ec.generate_private_key(ec.SECP256K1()),
    ], ids=['Ed25519', 'secp256k1'])
    def test_unreproducible_key_is_refused(self, app, key):
        from api.v2.msca import _generate_rekey_csr
        row = self._row(key)
        with app.app_context(), pytest.raises(ValueError, match='Cannot rekey'):
            _generate_rekey_csr(row)
        assert row.csr is None and row.prv is None
