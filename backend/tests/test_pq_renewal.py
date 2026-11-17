"""Renewal and re-key of ML-DSA certificates: the new key is of the same level,
MS CA re-keys reach ML-DSA through the registry, and a delegated OCSP responder
keeps its key across an RSA / ML-DSA issuer boundary."""
import base64
import json
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import mldsa, rsa

import fips_mode
from models import CA, Certificate, db
from utils import key_algorithms
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')

LEVELS = {'44': (mldsa.MLDSA44PrivateKey, mldsa.MLDSA44PublicKey),
          '65': (mldsa.MLDSA65PrivateKey, mldsa.MLDSA65PublicKey),
          '87': (mldsa.MLDSA87PrivateKey, mldsa.MLDSA87PublicKey)}


def _post(client, url, body):
    return client.post(url, content_type='application/json', data=json.dumps(body))


def _spki(key):
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def _row_cert(row):
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


@pytest.mark.parametrize('level', sorted(LEVELS))
def test_generate_like_keeps_the_level(level):
    from services.cert.renewal import _generate_like
    private_class, public_class = LEVELS[level]
    new = _generate_like(private_class.generate().public_key())
    assert isinstance(new, private_class)


def test_check_key_accepts_ml_dsa_and_fips_refuses_it(monkeypatch):
    from services.cert.renewal import RenewalError, _check_key
    public = mldsa.MLDSA87PrivateKey.generate().public_key()
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
    _check_key(public, rekey=True)
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    with pytest.raises(RenewalError, match='FIPS'):
        _check_key(public, rekey=True)


@pytest.mark.parametrize('level', sorted(LEVELS))
def test_api_renewal_rekeys_at_the_same_level(app, auth_client, create_ca, level):
    ca = create_ca(cn=f'PQ renewal CA {level}')
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': f'renew-mldsa{level}.example.test', 'ca_id': ca['id'], 'key_type': 'ml-dsa',
        'key_size': int(level), 'validity_days': 30})
    assert r.status_code == 201, r.get_json()
    cert_id = r.get_json()['data']['id']
    with app.app_context():
        before = _row_cert(db.session.get(Certificate, cert_id))
    r = _post(auth_client, f'/api/v2/certificates/{cert_id}/renew', {})
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        after = _row_cert(db.session.get(Certificate, r.get_json()['data']['id']))
        ca_cert = _row_cert(db.session.get(CA, ca['id']))
    assert isinstance(after.public_key(), LEVELS[level][1])
    assert _spki(after.public_key()) != _spki(before.public_key())
    after.verify_directly_issued_by(ca_cert)


@pytest.mark.parametrize('level', sorted(LEVELS))
def test_msca_rekey_key_type_reaches_ml_dsa(level):
    from api.v2.msca import _rekey_key_type
    from services.trust_store import TrustStoreService
    key_type = _rekey_key_type(LEVELS[level][0].generate().public_key())
    assert key_type == f'ml-dsa-{level}'
    assert isinstance(TrustStoreService.generate_private_key(key_type), LEVELS[level][0])


def test_msca_rekey_still_refuses_what_no_generator_makes():
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from api.v2.msca import _rekey_key_type
    with pytest.raises(ValueError, match='ML-DSA-65'):
        _rekey_key_type(ed25519.Ed25519PrivateKey.generate().public_key())


def test_tsa_signer_key_algo_label_names_ml_dsa():
    from services.tsa_signer_cert import _key_algo_label
    assert _key_algo_label(mldsa.MLDSA65PrivateKey.generate().public_key()) == 'ML-DSA-65'


# ---- delegated OCSP responder ---------------------------------------------------

def _responder(app, auth_client, ca_id, key_type, key_size, cn):
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': cn, 'ca_id': ca_id, 'key_type': key_type, 'key_size': key_size,
        'validity_days': 90, 'cert_type': 'custom', 'extra_ekus': ['OCSPSigning']})
    assert r.status_code == 201, r.get_json()
    cert_id = r.get_json()['data']['id']
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        row.valid_from = utc_now() - timedelta(days=85)
        row.valid_to = utc_now() + timedelta(days=5)
        db.session.commit()
    return cert_id


@pytest.mark.parametrize('issuer,responder', [('RSA-2048', ('ml-dsa', 65)), ('ML-DSA-87', ('rsa', 2048)),
                                              ('ML-DSA-44', ('ml-dsa', 87))])
def test_ocsp_responder_renewal_keeps_the_key(app, auth_client, issuer, responder):
    r = _post(auth_client, '/api/v2/cas', {'type': 'root', 'commonName': f'OCSP PQ {issuer} {responder}',
                                           'keyAlgo': issuer, 'validityYears': 2})
    assert r.status_code == 201, r.get_json()
    ca_id = r.get_json()['data']['id']
    cert_id = _responder(app, auth_client, ca_id, *responder, cn=f'ocsp-{issuer}-{responder[1]}.test')
    with app.app_context():
        from services.ocsp_responder_renewal import _renew_responder_cert
        ca = db.session.get(CA, ca_id)
        old = db.session.get(Certificate, cert_id)
        old_cert = _row_cert(old)
        new = _renew_responder_cert(ca, old)
        db.session.commit()
        new_cert = _row_cert(new)
        ca_cert = _row_cert(ca)
        assert new.key_algo == old.key_algo
    assert new_cert.serial_number != old_cert.serial_number
    assert _spki(new_cert.public_key()) == _spki(old_cert.public_key())
    new_cert.verify_directly_issued_by(ca_cert)
    if issuer.startswith('ML-DSA'):
        assert new_cert.signature_hash_algorithm is None
