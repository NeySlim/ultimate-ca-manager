"""A CA imported without its key is attached to the key an HSM still holds (#458)."""
import base64
import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509.oid import NameOID

from models import db, CA
from services.hsm.base_provider import HsmConnectionError, HsmKeyInfo
from tests.optional_backends import needs

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

DIGESTS = {'sha256': hashes.SHA256(), 'sha384': hashes.SHA384(), 'sha512': hashes.SHA512()}


def _pub_pem(key):
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def _label(key):
    if isinstance(key, rsa.RSAPrivateKey):
        return f'RSA-{key.key_size}'
    if isinstance(key, ec.EllipticCurvePrivateKey):
        return {'secp256r1': 'EC-P256', 'secp384r1': 'EC-P384'}[key.curve.name]
    from utils import key_algorithms
    return key_algorithms.label_for_private_key(key)


class _Token:
    """A provider over software keys; *signer* signs in place of the listed key when given."""

    SIGNS_PSS = True

    def __init__(self, keys, signer=None, unreachable=False, with_pem=True):
        self.keys, self.signer, self.unreachable, self.with_pem = keys, signer, unreachable, with_pem

    def __enter__(self):
        if self.unreachable:
            raise HsmConnectionError('token is down')
        return self

    def __exit__(self, *exc):
        return False

    def list_keys(self):
        self.list_errors = []
        return [HsmKeyInfo(key_identifier=kid, label=f'label-{kid}', algorithm=_label(key),
                           key_type='asymmetric', purpose='signing',
                           public_key_pem=_pub_pem(key) if self.with_pem else None)
                for kid, key in self.keys.items()]

    def get_public_key(self, key_identifier):
        return _pub_pem(self.keys[key_identifier])

    def hash_for_key(self, key_identifier, key_algorithm, requested='sha256'):
        return requested

    def sign(self, key_identifier, data, algorithm=None, hash_algorithm=None, padding=None):
        key = self.signer or self.keys[key_identifier]
        if isinstance(key, rsa.RSAPrivateKey):
            digest = DIGESTS[hash_algorithm]
            from cryptography.hazmat.primitives.asymmetric import padding as pad
            scheme = (pad.PSS(mgf=pad.MGF1(digest), salt_length=digest.digest_size)
                      if padding == 'pss' else pad.PKCS1v15())
            return key.sign(data, scheme, digest)
        if isinstance(key, ec.EllipticCurvePrivateKey):
            return key.sign(data, ec.ECDSA(DIGESTS[hash_algorithm]))
        return key.sign(data)


def _keyless_ca(app, key, cn):
    """A CA record holding only its certificate, as importing an exported CA certificate leaves it."""
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    digest = hashes.SHA256() if isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)) else None
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                                         key_encipherment=False, data_encipherment=False, key_agreement=False,
                                         key_cert_sign=True, crl_sign=True, encipher_only=False,
                                         decipher_only=False), critical=True)
            .sign(key, digest))
    with app.app_context():
        row = CA(refid=str(uuid.uuid4()), descr=cn, serial=0, prv=None,
                 crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
                 subject=name.rfc4514_string(), issuer=name.rfc4514_string(),
                 serial_number=str(cert.serial_number), imported_from='import')
        db.session.add(row)
        db.session.commit()
        return row.id, cert


@pytest.fixture
def provider(app):
    """Factory: an HSM provider row of *type*; its key rows and the CAs bound to them go after the test."""
    made = []

    def make(provider_type='pkcs11'):
        from models.hsm import HsmProvider
        with app.app_context():
            row = HsmProvider(name=f'attach-{uuid.uuid4().hex[:8]}', type=provider_type, config='{}')
            db.session.add(row)
            db.session.commit()
            made.append(row.id)
            return row.id

    yield make
    from models.hsm import HsmKey, HsmProvider
    with app.app_context():
        for provider_id in made:
            key_ids = [k.id for k in HsmKey.query.filter_by(provider_id=provider_id)]
            if key_ids:
                CA.query.filter(CA.hsm_key_id.in_(key_ids)).update({'hsm_key_id': None}, synchronize_session=False)
                HsmKey.query.filter(HsmKey.id.in_(key_ids)).delete(synchronize_session=False)
            db.session.query(HsmProvider).filter_by(id=provider_id).delete()
        db.session.commit()


def _token(token):
    return patch('services.hsm.HsmService._get_provider_instance', return_value=token)


def _list(client, ca_id, provider_id, headers=None):
    return client.get(f'/api/v2/cas/{ca_id}/hsm-keys?provider_id={provider_id}', headers=headers or {})


def _attach(client, ca_id, provider_id, key_identifier, headers=None):
    return client.post(f'/api/v2/cas/{ca_id}/hsm-key', data=json.dumps(
        {'provider_id': provider_id, 'key_identifier': key_identifier}),
        content_type='application/json', headers=headers or {})


def _message(r):
    body = json.loads(r.data)
    return body.get('message') or body.get('error') or ''


def _bound_key(app, ca_id):
    with app.app_context():
        return db.session.get(CA, ca_id).hsm_key_id


def _signs(app, auth_client, ca_id, ca_cert):
    """The CA issues a certificate and a CRL that its certificate's public key verifies."""
    r = auth_client.post('/api/v2/certificates', data=json.dumps({
        'cn': f'leaf-{uuid.uuid4().hex[:6]}.example.com', 'ca_id': ca_id, 'validity_days': 30,
        'key_type': 'RSA 2048', 'cert_type': 'server'}), content_type='application/json')
    assert r.status_code in (200, 201), r.data
    from models import Certificate
    with app.app_context():
        leaf = db.session.get(Certificate, json.loads(r.data)['data']['id'])
        leaf_cert = x509.load_pem_x509_certificate(base64.b64decode(leaf.crt))
    leaf_cert.verify_directly_issued_by(ca_cert)
    r = auth_client.post(f'/api/v2/crl/{ca_id}/regenerate')
    assert r.status_code == 200, r.data
    from models import CRLMetadata
    with app.app_context():
        row = CRLMetadata.query.filter_by(ca_id=ca_id).order_by(CRLMetadata.crl_number.desc()).first()
        crl = x509.load_der_x509_crl(row.crl_der)
    assert crl.issuer == ca_cert.subject
    assert crl.is_signature_valid(ca_cert.public_key())


def _mldsa_key():
    from utils import key_algorithms
    if not key_algorithms.mldsa_supported():
        pytest.skip('ML-DSA not available in this cryptography build')
    return key_algorithms.get('ML-DSA-65').generate()


class TestListing:
    def test_only_the_keys_of_the_certificate_are_listed(self, app, auth_client, provider):
        key = ec.generate_private_key(ec.SECP384R1())
        ca_id, _ = _keyless_ca(app, key, 'Listing CA')
        provider_id = provider()
        token = _Token({'ours': key, 'other-ec': ec.generate_private_key(ec.SECP384R1()),
                        'other-rsa': rsa.generate_private_key(65537, 2048)}, with_pem=False)
        with _token(token):
            r = _list(auth_client, ca_id, provider_id)
        assert r.status_code == 200, r.data
        keys = json.loads(r.data)['data']['keys']
        assert [(k['key_identifier'], k['label'], k['algorithm'], k['held_by']) for k in keys] == [
            ('ours', 'label-ours', 'EC-P384', None)]

    def test_an_unreachable_provider_is_refused(self, app, auth_client, provider):
        key = ec.generate_private_key(ec.SECP256R1())
        ca_id, _ = _keyless_ca(app, key, 'Unreachable Listing CA')
        provider_id = provider()
        with _token(_Token({'ours': key}, unreachable=True)):
            r = _list(auth_client, ca_id, provider_id)
        assert r.status_code == 502, r.data
        assert _message(r) == 'The HSM provider could not be reached'

    def test_an_unknown_provider_is_not_found(self, app, auth_client):
        ca_id, _ = _keyless_ca(app, ec.generate_private_key(ec.SECP256R1()), 'No Provider CA')
        assert _list(auth_client, ca_id, 999999).status_code == 404


class TestAttach:
    @pytest.mark.parametrize('make_key', [
        lambda: rsa.generate_private_key(65537, 2048),
        lambda: ec.generate_private_key(ec.SECP256R1()),
        lambda: ec.generate_private_key(ec.SECP384R1()),
    ], ids=['rsa-2048', 'ec-p256', 'ec-p384'])
    def test_the_attached_ca_signs_certificates_and_crls(self, app, auth_client, provider, make_key):
        key = make_key()
        ca_id, cert = _keyless_ca(app, key, f'Attach CA {uuid.uuid4().hex[:6]}')
        provider_id = provider()
        token = _Token({'k1': key, 'decoy': rsa.generate_private_key(65537, 2048)})
        with _token(token):
            r = _attach(auth_client, ca_id, provider_id, 'k1')
            assert r.status_code == 200, r.data
            body = json.loads(r.data)['data']
            assert body['uses_hsm'] is True and body['has_private_key'] is True
            assert body['certificate_only'] is False
            _signs(app, auth_client, ca_id, cert)
        from models.hsm import HsmKey
        from models.audit_log import AuditLog
        with app.app_context():
            row = db.session.get(HsmKey, _bound_key(app, ca_id))
            assert (row.provider_id, row.key_identifier, row.label) == (provider_id, 'k1', 'label-k1')
            entry = AuditLog.query.filter_by(action='ca_hsm_key_attached', resource_id=str(ca_id)).one()
            assert 'label-k1' in entry.details

    def test_an_ml_dsa_key_is_attached_on_a_provider_that_signs_it(self, app, auth_client, provider):
        from services.hsm import HsmService
        if HsmService.algorithm_refusal('openbao', 'ML-DSA-65'):
            pytest.skip('no registered provider signs ML-DSA here')
        key = _mldsa_key()
        ca_id, cert = _keyless_ca(app, key, 'ML-DSA Attach CA')
        provider_id = provider('openbao')
        with _token(_Token({'pq': key})):
            r = _attach(auth_client, ca_id, provider_id, 'pq')
            assert r.status_code == 200, r.data
            _signs(app, auth_client, ca_id, cert)

    def test_a_key_that_does_not_match_the_certificate_is_refused(self, app, auth_client, provider):
        key = rsa.generate_private_key(65537, 2048)
        ca_id, _ = _keyless_ca(app, key, 'Mismatch CA')
        provider_id = provider()
        with _token(_Token({'ours': key, 'theirs': rsa.generate_private_key(65537, 2048)})):
            r = _attach(auth_client, ca_id, provider_id, 'theirs')
        assert r.status_code == 400, r.data
        assert _message(r) == 'HSM key does not match the CA certificate'
        assert _bound_key(app, ca_id) is None

    def test_a_token_that_signs_with_another_key_is_refused(self, app, auth_client, provider):
        key = ec.generate_private_key(ec.SECP256R1())
        ca_id, _ = _keyless_ca(app, key, 'Wrong Signer CA')
        provider_id = provider()
        with _token(_Token({'ours': key}, signer=ec.generate_private_key(ec.SECP256R1()))):
            r = _attach(auth_client, ca_id, provider_id, 'ours')
        assert r.status_code == 400, r.data
        assert _message(r) == 'The HSM key did not produce a signature the CA certificate verifies'
        assert _bound_key(app, ca_id) is None

    def test_an_unreachable_provider_is_refused(self, app, auth_client, provider):
        key = ec.generate_private_key(ec.SECP256R1())
        ca_id, _ = _keyless_ca(app, key, 'Unreachable Attach CA')
        provider_id = provider()
        with _token(_Token({'ours': key}, unreachable=True)):
            r = _attach(auth_client, ca_id, provider_id, 'ours')
        assert r.status_code == 502, r.data
        assert _bound_key(app, ca_id) is None

    def test_a_key_absent_from_the_token_is_not_found(self, app, auth_client, provider):
        key = ec.generate_private_key(ec.SECP256R1())
        ca_id, _ = _keyless_ca(app, key, 'Absent Key CA')
        provider_id = provider()
        with _token(_Token({'ours': key})):
            r = _attach(auth_client, ca_id, provider_id, 'gone')
        assert r.status_code == 404, r.data

    def test_a_ca_that_has_a_key_is_refused(self, app, auth_client, provider, create_ca):
        full = create_ca(cn=f'Keyed CA {uuid.uuid4().hex[:6]}')
        provider_id = provider()
        with _token(_Token({'ours': ec.generate_private_key(ec.SECP256R1())})):
            r = _attach(auth_client, full['id'], provider_id, 'ours')
            assert r.status_code == 400, r.data
            assert _message(r) == 'CA already has a private key'
            r = _list(auth_client, full['id'], provider_id)
            assert r.status_code == 400, r.data

    def test_a_key_held_by_another_ca_is_shown_and_refused(self, app, auth_client, provider):
        key = ec.generate_private_key(ec.SECP256R1())
        first, _ = _keyless_ca(app, key, 'First Holder CA')
        second, _ = _keyless_ca(app, key, 'Second Holder CA')
        provider_id = provider()
        with _token(_Token({'ours': key})):
            assert _attach(auth_client, first, provider_id, 'ours').status_code == 200
            r = _list(auth_client, second, provider_id)
            assert [k['held_by'] for k in json.loads(r.data)['data']['keys']] == ["X.509 CA 'First Holder CA'"]
            r = _attach(auth_client, second, provider_id, 'ours')
        assert r.status_code == 409, r.data
        assert _bound_key(app, second) is None

    def test_write_cas_and_read_hsm_are_both_needed(self, app, auth_client, provider, viewer_client):
        key = ec.generate_private_key(ec.SECP256R1())
        ca_id, _ = _keyless_ca(app, key, 'Permission CA')
        provider_id = provider()
        made = []
        try:
            r = auth_client.post('/api/v2/account/apikeys', json={
                'name': 'attach-no-hsm', 'permissions': ['read:cas', 'write:cas']})
            assert r.status_code == 201, r.data
            made.append(r.get_json()['data']['id'])
            headers = {'X-API-Key': r.get_json()['data']['key']}
            with _token(_Token({'ours': key})):
                assert _attach(viewer_client, ca_id, provider_id, 'ours').status_code == 403
                r = _attach(app.test_client(), ca_id, provider_id, 'ours', headers=headers)
                assert r.status_code == 403, r.data
                assert _message(r) == 'Attaching an HSM key to a CA requires the read:hsm permission'
                assert _list(app.test_client(), ca_id, provider_id, headers=headers).status_code == 403
        finally:
            for key_id in made:
                auth_client.delete(f'/api/v2/account/apikeys/{key_id}')
        assert _bound_key(app, ca_id) is None


SOFTHSM_MODULES = ('/usr/lib/softhsm/libsofthsm2.so', '/usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so',
                   '/usr/lib64/pkcs11/libsofthsm2.so', '/usr/local/lib/softhsm/libsofthsm2.so')
SOFTHSM_MODULE = next((m for m in SOFTHSM_MODULES if os.path.exists(m)), None)
try:
    import pkcs11
    HAS_PKCS11 = True
except ImportError:
    HAS_PKCS11 = False


@needs('softhsm', HAS_PKCS11 and SOFTHSM_MODULE and shutil.which('softhsm2-util'),
       reason='SoftHSM or python-pkcs11 not installed')
@pytest.mark.parametrize('algorithm', ['EC-P384', 'RSA-3072'])
def test_a_softhsm_key_is_attached_back_to_its_reimported_ca(app, auth_client, tmp_path, monkeypatch, algorithm):
    """The issue's path: a CA on a token key is deleted, its certificate imported, the key attached again."""
    (tmp_path / 'tokens').mkdir()
    conf = tmp_path / 'softhsm2.conf'
    conf.write_text(f'directories.tokendir = {tmp_path / "tokens"}\nobjectstore.backend = file\nlog.level = ERROR\n')
    monkeypatch.setenv('SOFTHSM2_CONF', str(conf))
    subprocess.run(['softhsm2-util', '--init-token', '--free', '--label', 'ucm458', '--pin', '1234',
                    '--so-pin', '5678'], check=True, capture_output=True)
    pkcs11.unload(SOFTHSM_MODULE)  # the library reads SOFTHSM2_CONF once, when loaded
    from models.hsm import HsmKey, HsmProvider
    from services.hsm import HsmService
    try:
        with app.app_context():
            row = HsmProvider(name=f'softhsm-458-{algorithm}', type='pkcs11', config='{}')
            row.set_config({'module_path': SOFTHSM_MODULE, 'token_label': 'ucm458', 'user_pin': '1234'})
            db.session.add(row)
            db.session.commit()
            provider_id = row.id
            generated = HsmService.generate_key(provider_id, f'ca-458-{algorithm}', algorithm)
            key_identifier, key_row_id = generated.key_identifier, generated.id
        r = auth_client.post('/api/v2/cas', json={'commonName': f'HSM 458 {algorithm}', 'descr': f'HSM 458 {algorithm}',
                                                  'validityYears': 1, 'hsm_key_id': key_row_id})
        assert r.status_code == 201, r.data
        created = r.get_json()['data']
        with app.app_context():
            cert_pem = base64.b64decode(db.session.get(CA, created['id']).crt)
        assert auth_client.delete(f"/api/v2/cas/{created['id']}").status_code in (200, 204)
        r = auth_client.post('/api/v2/cas/import', data={'pem_content': cert_pem.decode()},
                             content_type='multipart/form-data')
        assert r.status_code in (200, 201), r.data
        ca_id = r.get_json()['data']['id']
        assert r.get_json()['data']['certificate_only'] is True
        r = _list(auth_client, ca_id, provider_id)
        assert r.status_code == 200, r.data
        assert [k['key_identifier'] for k in r.get_json()['data']['keys']] == [key_identifier]
        r = _attach(auth_client, ca_id, provider_id, key_identifier)
        assert r.status_code == 200, r.data
        _signs(app, auth_client, ca_id, x509.load_pem_x509_certificate(cert_pem))
    finally:
        with app.app_context():
            ids = [k.id for k in HsmKey.query.join(HsmProvider).filter(HsmProvider.name == f'softhsm-458-{algorithm}')]
            if ids:
                CA.query.filter(CA.hsm_key_id.in_(ids)).update({'hsm_key_id': None}, synchronize_session=False)
                HsmKey.query.filter(HsmKey.id.in_(ids)).delete(synchronize_session=False)
            HsmProvider.query.filter_by(name=f'softhsm-458-{algorithm}').delete()
            db.session.commit()
        pkcs11.unload(SOFTHSM_MODULE)
