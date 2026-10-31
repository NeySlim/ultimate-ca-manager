"""ML-DSA keys held by an HSM: the wrapper passes for the pyca key class of its own
parameter set, signs without a digest, and a CA on such a key signs certificates,
CRLs and OCSP responses that verify. The provider here is a stand-in that signs
with a software key through pyca."""
import base64
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import mldsa
from cryptography.x509 import ocsp
from cryptography.x509.oid import NameOID

from models.hsm import HsmKey
from utils import key_algorithms

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')

LEVELS = {
    'ML-DSA-44': (mldsa.MLDSA44PrivateKey, '2.16.840.1.101.3.4.3.17'),
    'ML-DSA-65': (mldsa.MLDSA65PrivateKey, '2.16.840.1.101.3.4.3.18'),
    'ML-DSA-87': (mldsa.MLDSA87PrivateKey, '2.16.840.1.101.3.4.3.19'),
}


class _PycaProvider:
    """Signs as an HSM would, with a software key; records what it was asked."""

    def __init__(self, key):
        self.key, self.calls = key, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def hash_for_key(self, key_identifier, key_algorithm, requested='sha256'):
        return requested

    def delete_key(self, key_identifier):
        return True

    def sign(self, key_identifier, data, algorithm=None, hash_algorithm=None, padding=None):
        self.calls.append((algorithm, hash_algorithm, padding))
        return self.key.sign(data)


def _pem(public_key):
    return public_key.public_bytes(serialization.Encoding.PEM,
                                   serialization.PublicFormat.SubjectPublicKeyInfo).decode()


@contextmanager
def _hsm_mldsa_key(app, label='ML-DSA-65', provider_type='pkcs11'):
    key = LEVELS[label][0].generate()
    with app.app_context():
        from models import db
        from models.hsm import HsmProvider
        tag = f'{label}-{id(key)}'
        provider = HsmProvider(name=f'PQ {tag}', type=provider_type, config='{}')
        db.session.add(provider)
        db.session.commit()
        row = HsmKey(provider_id=provider.id, key_identifier=f'pq-{tag}', label=f'pq-{tag}',
                     algorithm=label, key_type='asymmetric', purpose='signing',
                     public_key_pem=_pem(key.public_key()))
        db.session.add(row)
        db.session.commit()
        key_id, provider_id = row.id, provider.id
    fake = _PycaProvider(key)
    try:
        with patch('services.hsm.HsmService._get_provider_instance', return_value=fake):
            yield key_id, key, fake
    finally:
        with app.app_context():
            from models import CA, Certificate, db
            from models.crl import CRLMetadata
            from models.hsm import HsmProvider
            from models.ocsp import OCSPResponse
            from services.hsm import HsmService
            db.session.rollback()
            for ca in CA.query.filter_by(hsm_key_id=key_id).all():
                CRLMetadata.query.filter_by(ca_id=ca.id).delete()
                OCSPResponse.query.filter_by(ca_id=ca.id).delete()
                Certificate.query.filter_by(caref=ca.refid).delete()
                db.session.delete(ca)
            db.session.query(HsmKey).filter_by(id=key_id).delete()
            db.session.query(HsmProvider).filter_by(id=provider_id).delete()
            db.session.commit()
            HsmService.forget_signing_hash(key_id)


def _self_signed(signing_key, public_key):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'HSM ML-DSA')])
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(public_key)
            .serial_number(1).not_valid_before(now).not_valid_after(now + timedelta(days=1))
            .sign(signing_key, None))


def test_the_model_accepts_the_ml_dsa_labels():
    for label in LEVELS:
        assert label in HsmKey.VALID_ALGORITHMS


@pytest.mark.parametrize('label', sorted(LEVELS))
def test_loaded_wrapper_is_the_pyca_class_of_its_level(app, label):
    from services.hsm.hsm_private_key import is_hsm_private_key, load_hsm_private_key
    with _hsm_mldsa_key(app, label) as (key_id, key, fake), app.app_context():
        wrapper = load_hsm_private_key(key_id)
        assert is_hsm_private_key(wrapper)
        for other, (cls, _oid) in LEVELS.items():
            assert isinstance(wrapper, cls) == (other == label)
        assert key_algorithms.label_for_private_key(wrapper) == label
        assert wrapper.public_key() == key.public_key()


@pytest.mark.parametrize('label', sorted(LEVELS))
def test_a_certificate_signed_through_the_hsm_names_and_verifies_its_level(app, label):
    from services.hsm.hsm_private_key import load_hsm_private_key
    with _hsm_mldsa_key(app, label) as (key_id, key, fake), app.app_context():
        cert = _self_signed(load_hsm_private_key(key_id), key.public_key())
    # pyca checks the signature under the OID the wrapper's class named
    cert.verify_directly_issued_by(cert)
    assert cert.signature_algorithm_oid.dotted_string == LEVELS[label][1]
    assert fake.calls == [(label, None, None)]


def test_a_context_is_refused_rather_than_dropped(app):
    from services.hsm.hsm_private_key import load_hsm_private_key
    with _hsm_mldsa_key(app) as (key_id, _key, fake), app.app_context():
        wrapper = load_hsm_private_key(key_id)
        assert wrapper.sign(b'tbs', b'') and wrapper.sign(b'tbs', None)
        with pytest.raises(UnsupportedAlgorithm, match='context'):
            wrapper.sign(b'tbs', b'ctx')
    assert len(fake.calls) == 2


def test_a_signature_from_another_key_is_caught(app):
    from services.hsm.hsm_private_key import load_hsm_private_key
    with _hsm_mldsa_key(app) as (key_id, _key, fake), app.app_context():
        fake.key = mldsa.MLDSA65PrivateKey.generate()
        with pytest.raises(ValueError, match='does not verify'):
            load_hsm_private_key(key_id).sign(b'tbs')


def test_service_sign_passes_no_digest_and_keeps_the_signature(app):
    from services.hsm import HsmService
    with _hsm_mldsa_key(app) as (key_id, key, fake), app.app_context():
        signature = HsmService.sign(key_id, b'payload', 'ML-DSA-65')
        key.public_key().verify(signature, b'payload')
        with pytest.raises(ValueError, match='digest'):
            HsmService.sign(key_id, b'payload', 'ML-DSA-65', hash_algorithm='sha256')
    assert fake.calls == [('ML-DSA-65', None, None)]


def test_storage_and_scheme_of_an_hsm_ml_dsa_signer(app):
    from services import compliance_signer
    from services.hsm.hsm_private_key import load_hsm_private_key
    with _hsm_mldsa_key(app) as (key_id, _key, _fake), app.app_context():
        assert compliance_signer.describe(load_hsm_private_key(key_id)) == ('ml_dsa', 'hsm')


class _GeneratingProvider(_PycaProvider):
    """Generates in software what an HSM would, and says what it was asked."""

    def __init__(self):
        super().__init__(None)
        self.generated = []

    def generate_key(self, label, algorithm, purpose='signing', extractable=False):
        from services.hsm.base_provider import HsmKeyInfo
        self.generated.append(algorithm)
        self.key = LEVELS[algorithm][0].generate()
        return HsmKeyInfo(key_identifier=f'gen-{label}', label=label, algorithm=algorithm,
                          key_type='asymmetric', purpose=purpose,
                          public_key_pem=_pem(self.key.public_key()))


@contextmanager
def _provider_row(app):
    from models import db
    from models.hsm import HsmProvider
    with app.app_context():
        row = HsmProvider(name=f'PQ gen {uuid4()}', type='pkcs11', config='{}')
        db.session.add(row)
        db.session.commit()
        provider_id = row.id
    fake = _GeneratingProvider()
    try:
        with patch('services.hsm.HsmService._get_provider_instance', return_value=fake), app.app_context():
            yield provider_id, fake
    finally:
        with app.app_context():
            db.session.rollback()
            db.session.query(HsmKey).filter_by(provider_id=provider_id).delete()
            db.session.query(HsmProvider).filter_by(id=provider_id).delete()
            db.session.commit()


@pytest.mark.parametrize('label', sorted(LEVELS))
def test_generating_an_ml_dsa_key_stores_its_level(app, label):
    from services.hsm import HsmService
    from services.hsm.hsm_private_key import load_hsm_private_key
    with _provider_row(app) as (provider_id, fake):
        row = HsmService.generate_key(provider_id, f'gen-{label}', label)
        assert (row.algorithm, fake.generated) == (label, [label])
        assert isinstance(load_hsm_private_key(row.id), LEVELS[label][0])


def test_fips_mode_refuses_an_ml_dsa_key_on_any_provider(app, monkeypatch):
    import fips_mode
    from services.hsm import HsmService
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    with _provider_row(app) as (provider_id, fake):
        with pytest.raises(fips_mode.FipsRestricted, match='ML-DSA-65'):
            HsmService.generate_key(provider_id, 'fips-mldsa', 'ML-DSA-65')
    assert fake.generated == []


def test_a_build_without_ml_dsa_says_so_before_the_hsm_generates(app, monkeypatch):
    from services.hsm import HsmService
    monkeypatch.setattr(key_algorithms, 'mldsa_supported', lambda: False)
    key_algorithms._load()
    try:
        with _provider_row(app) as (provider_id, fake):
            with pytest.raises(ValueError, match='not available on this build'):
                HsmService.generate_key(provider_id, 'old-build', 'ML-DSA-65')
    finally:
        monkeypatch.undo()
        key_algorithms._load()
    assert fake.generated == []


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


def test_a_ca_on_an_hsm_ml_dsa_key_signs_certificate_crl_and_ocsp(app, auth_client, create_cert):
    from models import CA, Certificate, db
    from models.crl import CRLMetadata
    with _hsm_mldsa_key(app, 'ML-DSA-65') as (key_id, key, fake):
        r = _post(auth_client, '/api/v2/cas', {
            'type': 'root', 'commonName': 'HSM ML-DSA-65 root', 'organization': 'T',
            'validityYears': 5, 'hsm_key_id': key_id, 'digest': 'sha384'})
        assert r.status_code in (200, 201), r.get_json()
        ca_id = r.get_json()['data']['id']
        assert 'sha384' in json.dumps(r.get_json().get('meta') or {})
        with app.app_context():
            row = db.session.get(CA, ca_id)
            row.ocsp_enabled = True
            db.session.commit()
            ca_cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        assert ca_cert.public_key() == key.public_key()
        # The key decides: no digest named, and the three signature bits of RFC 9881
        assert ca_cert.signature_hash_algorithm is None
        assert ca_cert.extensions.get_extension_for_class(x509.KeyUsage).value.digital_signature
        assert ca_cert.signature_algorithm_oid.dotted_string == LEVELS['ML-DSA-65'][1]
        ca_cert.verify_directly_issued_by(ca_cert)

        leaf = create_cert(cn='hsm-mldsa-leaf.example.test', ca_id=ca_id)
        with app.app_context():
            leaf_cert = x509.load_pem_x509_certificate(
                base64.b64decode(db.session.get(Certificate, leaf['id']).crt))
        assert leaf_cert.signature_hash_algorithm is None
        leaf_cert.verify_directly_issued_by(ca_cert)

        r = _post(auth_client, f"/api/v2/certificates/{leaf['id']}/revoke", {'reason': 'superseded'})
        assert r.status_code == 200, r.get_json()
        r = auth_client.post(f'/api/v2/crl/{ca_id}/regenerate')
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            crl_row = CRLMetadata.query.filter_by(ca_id=ca_id, is_delta=False).order_by(
                CRLMetadata.crl_number.desc()).first()
            crl = x509.load_pem_x509_crl(crl_row.crl_pem.encode())
        assert crl.signature_algorithm_oid.dotted_string == LEVELS['ML-DSA-65'][1]
        assert crl.is_signature_valid(key.public_key())
        assert crl.get_revoked_certificate_by_serial_number(leaf_cert.serial_number) is not None

        request = ocsp.OCSPRequestBuilder().add_certificate(
            leaf_cert, ca_cert, hashes.SHA1()).build()
        r = auth_client.post('/ocsp', data=request.public_bytes(serialization.Encoding.DER),
                             content_type='application/ocsp-request')
        assert r.status_code == 200
        answer = ocsp.load_der_ocsp_response(r.data)
        assert answer.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
        assert answer.certificate_status == ocsp.OCSPCertStatus.REVOKED
        assert answer.signature_algorithm_oid.dotted_string == LEVELS['ML-DSA-65'][1]
        key.public_key().verify(answer.signature, answer.tbs_response_bytes)
    assert fake.calls and all(c == ('ML-DSA-65', None, None) for c in fake.calls)
