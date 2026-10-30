"""ML-DSA private keys as OpenSSL writes them: the seed-only layout loads, the
default "both" layout is read from its seed once its expanded key is checked
against it, and the seedless layout is refused with a message saying how to
export the key again. A PKCS#12 holding such a key is refused by name."""
import base64
import json
import uuid
from contextlib import contextmanager

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import mldsa, rsa

from models import CA, Certificate, db
from tests.conftest import get_json
from tests.pqc_fixtures import P12_PASSWORD, fixture_bytes, load_mldsa_key

SEED = fixture_bytes('mldsa65-seed.pem')
BOTH = fixture_bytes('mldsa65-both.pem')
PRIV = fixture_bytes('mldsa65-priv.pem')
CERT = fixture_bytes('mldsa65-cert.pem')
PROBLEM = 'urn:ucm:problem:unsupported-for-key-algorithm'


def _raw_public(key):
    return key.public_key().public_bytes_raw()


def _der(pem):
    return base64.b64decode(b''.join(line for line in pem.splitlines() if not line.startswith(b'-----')))


def _tampered_both_der():
    """The "both" key with one byte of tr (the hash of the public key) flipped."""
    der = bytearray(_der(BOTH))
    seed = load_mldsa_key().private_bytes_raw()
    at = bytes(der).index(seed) + 32 + 4 + 64
    der[at] ^= 0x01
    return bytes(der)


# ------------------------------------------------------------- the loader

def test_seed_only_key_loads():
    from utils.key_codec import load_private_key_any
    key = load_private_key_any(SEED)
    assert isinstance(key, mldsa.MLDSA65PrivateKey)


@pytest.mark.parametrize('form', ['pem', 'der'])
def test_both_layout_is_read_from_its_seed(form):
    from utils.key_codec import load_private_key_any
    key = load_private_key_any(BOTH if form == 'pem' else _der(BOTH))
    assert isinstance(key, mldsa.MLDSA65PrivateKey)
    assert _raw_public(key) == _raw_public(load_mldsa_key())


def test_both_layout_whose_halves_disagree_is_refused():
    from utils.key_codec import load_private_key_any
    with pytest.raises(ValueError, match='do not match'):
        load_private_key_any(_tampered_both_der())


def test_seedless_key_is_refused_with_the_command():
    from utils.algorithm_refusal import UnsupportedForKeyAlgorithm
    from utils.key_codec import load_private_key_any
    with pytest.raises(UnsupportedForKeyAlgorithm) as caught:
        load_private_key_any(PRIV)
    assert 'ml-dsa.output_formats=seed-only' in str(caught.value)
    assert caught.value.details['key_algorithm'] == 'ML-DSA-65'


def test_classical_keys_are_untouched():
    from utils.key_codec import load_private_key_any
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.BestAvailableEncryption(b'secret'))
    assert load_private_key_any(pem, b'secret').private_numbers() == key.private_numbers()
    with pytest.raises(ValueError):
        load_private_key_any(b'-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n')


def test_normalized_pem_is_the_seed_layout():
    from utils.key_codec import normalize_private_key_pem
    assert normalize_private_key_pem(SEED) == SEED
    repaired = normalize_private_key_pem(BOTH)
    assert _raw_public(serialization.load_pem_private_key(repaired, None)) == \
        _raw_public(load_mldsa_key())


# ------------------------------------------------------------- the callers

def test_import_service_reads_a_both_key_next_to_its_certificate():
    from services.import_service import parse_certificate_file
    cert, key, _ = parse_certificate_file(CERT + BOTH, 'bundle.pem')
    assert isinstance(key, mldsa.MLDSA65PrivateKey)
    assert _raw_public(key) == cert.public_key().public_bytes_raw()


def test_import_service_refuses_a_seedless_key():
    from services.import_service import parse_certificate_file
    from utils.algorithm_refusal import UnsupportedForKeyAlgorithm
    with pytest.raises(UnsupportedForKeyAlgorithm):
        parse_certificate_file(CERT + PRIV, 'bundle.pem')


def test_import_service_refuses_an_ml_dsa_pkcs12_by_name():
    from services.import_service import parse_certificate_file
    from utils.algorithm_refusal import UnsupportedForKeyAlgorithm
    with pytest.raises(UnsupportedForKeyAlgorithm, match='PKCS#12'):
        parse_certificate_file(fixture_bytes('mldsa65.p12'), 'k.p12', P12_PASSWORD.decode())


def test_import_service_still_reports_a_wrong_pkcs12_password():
    from services.import_service import parse_certificate_file
    with pytest.raises(ValueError, match='Invalid password'):
        parse_certificate_file(fixture_bytes('mldsa65.p12'), 'k.p12', 'wrong')


def test_smart_import_keeps_the_repaired_key():
    from services.smart_import.parser import SmartParser
    keys = [o for o in SmartParser().parse(BOTH.decode()) if o.type.value == 'private_key']
    assert [k.key_algorithm for k in keys] == ['ML-DSA-65']
    reloaded = serialization.load_pem_private_key(keys[0].raw_pem.encode(), None)
    assert _raw_public(reloaded) == _raw_public(load_mldsa_key())


def test_smart_import_refuses_a_seedless_key():
    from services.smart_import.parser import SmartParser
    from utils.algorithm_refusal import UnsupportedForKeyAlgorithm
    with pytest.raises(UnsupportedForKeyAlgorithm):
        SmartParser().parse(PRIV.decode())


def test_smart_import_refuses_an_ml_dsa_pkcs12():
    from services.smart_import.parser import SmartParser
    from utils.algorithm_refusal import UnsupportedForKeyAlgorithm
    with pytest.raises(UnsupportedForKeyAlgorithm):
        SmartParser().parse(fixture_bytes('mldsa65.p12'), password=P12_PASSWORD.decode())


@contextmanager
def _keyless_rows(app):
    """A certificate row and a CA row holding the ML-DSA fixture certificate, no key."""
    tag = uuid.uuid4().hex[:8]
    crt = base64.b64encode(CERT).decode()
    subject = x509.load_pem_x509_certificate(CERT).subject.rfc4514_string()
    with app.app_context():
        cert = Certificate(refid=f'pq-key-{tag}', descr=f'pq-key-{tag}', crt=crt,
                           subject=subject, issuer=subject)
        ca = CA(refid=f'pq-key-ca-{tag}', descr=f'pq-key-ca-{tag}', serial=0, crt=crt,
                subject=subject, issuer=subject, imported_from='manual')
        csr = Certificate(refid=f'pq-key-csr-{tag}', descr=f'pq-key-csr-{tag}',
                          csr=base64.b64encode(fixture_bytes('mldsa65-csr.pem')).decode(),
                          subject=subject)
        db.session.add_all([cert, ca, csr])
        db.session.commit()
        ids = {'certificate': (cert.id, f'/api/v2/certificates/{cert.id}/key', Certificate),
               'ca': (ca.id, f'/api/v2/cas/{ca.id}/key', CA),
               'csr': (csr.id, f'/api/v2/csrs/{csr.id}/key', Certificate)}
    try:
        yield ids
    finally:
        with app.app_context():
            db.session.rollback()
            Certificate.query.filter(Certificate.refid.in_(
                [f'pq-key-{tag}', f'pq-key-csr-{tag}'])).delete(synchronize_session=False)
            CA.query.filter_by(refid=f'pq-key-ca-{tag}').delete()
            db.session.commit()


def _post(client, url, key):
    return client.post(url, data=json.dumps({'key': key.decode()}), content_type='application/json')


@pytest.mark.parametrize('target', ['certificate', 'ca', 'csr'])
def test_key_upload_accepts_the_both_layout(app, auth_client, target):
    with _keyless_rows(app) as rows:
        row_id, url, model = rows[target]
        r = _post(auth_client, url, BOTH)
        assert r.status_code in (200, 201), r.data
        with app.app_context():
            from utils.key_codec import load_pem_bytes
            row = db.session.get(model, row_id)
            stored = serialization.load_pem_private_key(load_pem_bytes(row.prv), None)
            assert _raw_public(stored) == _raw_public(load_mldsa_key())


@pytest.mark.parametrize('target', ['certificate', 'ca', 'csr'])
def test_key_upload_refuses_a_seedless_key_with_its_reason(app, auth_client, target):
    with _keyless_rows(app) as rows:
        _, url, _ = rows[target]
        r = _post(auth_client, url, PRIV)
        assert r.status_code == 400, r.data
        body = get_json(r)
        assert body['type'] == PROBLEM
        assert body['details']['reason'] == 'unsupported_for_key_algorithm'
        assert 'seed-only' in body['message']


def test_key_matcher_matches_a_both_key(auth_client):
    r = auth_client.post('/api/v2/tools/match-keys', data=json.dumps(
        {'certificate': CERT.decode(), 'private_key': BOTH.decode()}), content_type='application/json')
    assert r.status_code == 200, r.data
    data = get_json(r)['data']
    assert data['matches'] and not data['mismatches']
    assert {'type': 'private_key', 'key_type': 'ML-DSA-65', 'valid': True} in data['items']
