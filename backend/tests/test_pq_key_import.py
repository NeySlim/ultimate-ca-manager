"""ML-DSA private keys as OpenSSL writes them: the seed-only layout loads, the
default "both" layout is read from its seed once its expanded key is checked
against it, and the seedless layout is refused with a message saying how to
export the key again; the same holds once an encrypted key is opened with its
password. A PKCS#12 holding such a key is refused by name."""
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
BOTH_ENC = fixture_bytes('mldsa65-both-enc.pem')     # PBES2, HMAC-SHA256, AES-256-CBC
PRIV_ENC = fixture_bytes('mldsa65-priv-enc.pem')
ENCRYPTED_BOTH = {'aes256': BOTH_ENC, 'aes128-sha1': fixture_bytes('mldsa65-both-aes128-sha1.pem'),
                  'des3-der': fixture_bytes('mldsa65-both-des3.der')}
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


@pytest.mark.parametrize('variant', ENCRYPTED_BOTH)
def test_encrypted_both_layout_is_read_from_its_seed(variant):
    from utils.key_codec import load_private_key_any
    key = load_private_key_any(ENCRYPTED_BOTH[variant], P12_PASSWORD)
    assert _raw_public(key) == _raw_public(load_mldsa_key())


@pytest.mark.parametrize('variant', ENCRYPTED_BOTH)
def test_encrypted_both_layout_keeps_the_wrong_password_error(variant):
    from utils.key_codec import load_private_key_any
    with pytest.raises(ValueError, match='Incorrect password'):
        load_private_key_any(ENCRYPTED_BOTH[variant], b'wrong')


def test_encrypted_seedless_key_is_refused_with_the_command():
    from utils.algorithm_refusal import UnsupportedForKeyAlgorithm
    from utils.key_codec import load_private_key_any
    with pytest.raises(UnsupportedForKeyAlgorithm, match='output_formats=seed-only'):
        load_private_key_any(PRIV_ENC, P12_PASSWORD)


@pytest.mark.parametrize('layout', ['both', 'seedless'])
def test_unencrypted_der_key_given_a_password_is_still_read(layout):
    from utils.algorithm_refusal import UnsupportedForKeyAlgorithm
    from utils.key_codec import load_private_key_any
    if layout == 'both':
        key = load_private_key_any(_der(BOTH), b'anything')
        assert _raw_public(key) == _raw_public(load_mldsa_key())
    else:
        with pytest.raises(UnsupportedForKeyAlgorithm, match='output_formats=seed-only'):
            load_private_key_any(_der(PRIV), b'anything')


@pytest.mark.parametrize('kind', ['rsa', 'ml-dsa'])
def test_wrong_password_is_not_tried_a_second_time(monkeypatch, kind):
    from utils import key_codec
    calls = []
    monkeypatch.setattr(key_codec, '_decrypt_pkcs8', lambda *a: calls.append(a))
    data = BOTH_ENC
    if kind == 'rsa':
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        while True:  # a wrong key unpads by chance about once in 300 salts: pyca then says otherwise
            data = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.BestAvailableEncryption(b'secret'))
            try:
                serialization.load_pem_private_key(data, b'wrong')
            except ValueError as e:
                if 'Incorrect password' in str(e):
                    break
    with pytest.raises(ValueError, match='Incorrect password'):
        key_codec.load_private_key_any(data, b'wrong')
    assert calls == []


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


def test_import_service_reads_an_encrypted_both_key():
    from services.import_service import parse_certificate_file
    cert, key, _ = parse_certificate_file(CERT + BOTH_ENC, 'bundle.pem', P12_PASSWORD.decode())
    assert _raw_public(key) == cert.public_key().public_bytes_raw()


def test_import_service_refuses_an_encrypted_seedless_key():
    from services.import_service import parse_certificate_file
    from utils.algorithm_refusal import UnsupportedForKeyAlgorithm
    with pytest.raises(UnsupportedForKeyAlgorithm):
        parse_certificate_file(CERT + PRIV_ENC, 'bundle.pem', P12_PASSWORD.decode())


def test_import_service_refuses_a_key_whose_halves_disagree():
    from services.import_service import parse_certificate_file
    from utils.key_codec import MalformedKey
    pem = (b'-----BEGIN PRIVATE KEY-----\n' + base64.encodebytes(_tampered_both_der())
           + b'-----END PRIVATE KEY-----\n')
    with pytest.raises(MalformedKey, match='do not match'):
        parse_certificate_file(CERT + pem, 'bundle.pem')


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


def test_smart_import_reads_an_encrypted_both_key():
    from services.smart_import.parser import SmartParser
    keys = [o for o in SmartParser().parse(BOTH_ENC.decode(), password=P12_PASSWORD.decode())
            if o.type.value == 'private_key']
    assert [(k.key_algorithm, k.is_encrypted) for k in keys] == [('ML-DSA-65', True)]


def test_smart_import_reports_a_key_whose_halves_disagree(auth_client):
    pem = (b'-----BEGIN PRIVATE KEY-----\n' + base64.encodebytes(_tampered_both_der())
           + b'-----END PRIVATE KEY-----\n').decode()
    r = auth_client.post('/api/v2/import/analyze', data=json.dumps({'content': pem}),
                         content_type='application/json')
    assert r.status_code == 200, r.data
    data = get_json(r)['data']
    [key] = [o for o in data['objects'] if o['type'] == 'private_key']
    assert key['is_encrypted'] is False and key['key_algorithm'] != 'unknown (encrypted)'
    assert 'do not match' in key['error']
    assert any('do not match' in e for e in data['validation']['errors'])


def test_smart_import_reads_an_unencrypted_der_key_given_a_password():
    from services.smart_import.parser import SmartParser
    keys = [o for o in SmartParser().parse(_der(BOTH), password='anything')
            if o.type.value == 'private_key']
    assert [k.key_algorithm for k in keys] == ['ML-DSA-65']


@pytest.mark.parametrize('wrapping', ['raw', 'der-key-block'])
def test_smart_import_reports_a_der_key_whose_halves_disagree(wrapping):
    from services.smart_import.parser import SmartParser
    data = _tampered_both_der()
    if wrapping == 'der-key-block':
        data = ('-----BEGIN DER KEY-----\n' + base64.encodebytes(data).decode()
                + '-----END DER KEY-----\n')
    [key] = [o for o in SmartParser().parse(data) if o.type.value == 'private_key']
    assert 'do not match' in key.error


def test_smart_import_execute_refuses_a_key_whose_halves_disagree(app, auth_client):
    pem = (b'-----BEGIN PRIVATE KEY-----\n' + base64.encodebytes(_tampered_both_der())
           + b'-----END PRIVATE KEY-----\n')
    with app.app_context():
        before = (CA.query.count(), Certificate.query.count())
    r = auth_client.post('/api/v2/import/execute', data=json.dumps({'content': (CERT + pem).decode()}),
                         content_type='application/json')
    assert r.status_code == 200, r.data
    data = get_json(r)['data']
    assert data['success'] is False
    assert any('do not match' in e for e in data['errors'])
    with app.app_context():
        assert (CA.query.count(), Certificate.query.count()) == before


def _rsa_leaf_and_encrypted_key(password):
    import datetime
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'enc-rsa-{uuid.uuid4().hex[:8]}')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    sealed = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                               serialization.BestAvailableEncryption(password.encode()))
    return cert.public_bytes(serialization.Encoding.PEM), sealed, key


@pytest.mark.parametrize('kind', ['ml-dsa-both', 'rsa'])
def test_smart_import_execute_keeps_an_encrypted_key(app, auth_client, kind):
    if kind == 'rsa':
        cert, sealed, key = _rsa_leaf_and_encrypted_key(P12_PASSWORD.decode())
        expected = key.public_key().public_numbers()
    else:
        cert, sealed, expected = CERT, BOTH_ENC, _raw_public(load_mldsa_key())
    r = auth_client.post('/api/v2/import/execute', data=json.dumps({
        'content': (cert + sealed).decode(), 'password': P12_PASSWORD.decode(),
        'options': {'skip_duplicates': False}}), content_type='application/json')
    assert r.status_code == 200, r.data
    data = get_json(r)['data']
    ids = data['imported_ids']
    with app.app_context():
        from utils.key_codec import load_pem_bytes
        rows = ([db.session.get(CA, i) for i in ids.get('cas', [])]
                + [db.session.get(Certificate, i) for i in ids.get('certificates', [])])
        try:
            assert data['success'] is True, data
            assert data['keys_matched'] == 1, data
            [row] = rows
            assert row.prv, 'the key was dropped'
            stored = serialization.load_pem_private_key(load_pem_bytes(row.prv), None)
            got = (stored.public_key().public_numbers() if kind == 'rsa' else _raw_public(stored))
            assert got == expected
        finally:
            for row in rows:
                db.session.delete(row)
            db.session.commit()


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


def _post(client, url, key, passphrase=None):
    body = {'key': key.decode(), **({'passphrase': passphrase} if passphrase else {})}
    return client.post(url, data=json.dumps(body), content_type='application/json')


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
def test_key_upload_accepts_an_encrypted_both_key(app, auth_client, target):
    with _keyless_rows(app) as rows:
        row_id, url, model = rows[target]
        r = _post(auth_client, url, BOTH_ENC, P12_PASSWORD.decode())
        assert r.status_code in (200, 201), r.data
        with app.app_context():
            from utils.key_codec import load_pem_bytes
            stored = serialization.load_pem_private_key(
                load_pem_bytes(db.session.get(model, row_id).prv), None)
            assert _raw_public(stored) == _raw_public(load_mldsa_key())


@pytest.mark.parametrize('target', ['certificate', 'ca', 'csr'])
@pytest.mark.parametrize('encrypted', [False, True], ids=['plain', 'encrypted'])
def test_key_upload_refuses_a_seedless_key_with_its_reason(app, auth_client, target, encrypted):
    with _keyless_rows(app) as rows:
        _, url, _ = rows[target]
        r = _post(auth_client, url, *((PRIV_ENC, P12_PASSWORD.decode()) if encrypted else (PRIV,)))
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


def _import(client, key, password):
    return client.post('/api/v2/certificates/import', data={
        'pem_content': (CERT + key).decode(), 'password': password, 'name': f'pq-enc-{uuid.uuid4().hex[:8]}'})


def test_certificate_import_keeps_an_encrypted_both_key(app, auth_client):
    r = _import(auth_client, BOTH_ENC, P12_PASSWORD.decode())
    assert r.status_code in (200, 201), r.data
    refid = get_json(r)['data']['refid']
    with app.app_context():
        from utils.key_codec import load_pem_bytes
        row = CA.query.filter_by(refid=refid).first() or Certificate.query.filter_by(refid=refid).first()
        try:
            assert row.prv, 'the key was dropped'
            stored = serialization.load_pem_private_key(load_pem_bytes(row.prv), None)
            assert _raw_public(stored) == _raw_public(load_mldsa_key())
        finally:
            db.session.delete(row)
            db.session.commit()


def test_certificate_import_refuses_an_encrypted_seedless_key(auth_client):
    r = _import(auth_client, PRIV_ENC, P12_PASSWORD.decode())
    assert r.status_code == 400, r.data
    assert get_json(r)['type'] == PROBLEM


@pytest.mark.parametrize('path', ['/api/v2/certificates/import', '/api/v2/cas/import'])
def test_import_routes_name_a_key_whose_halves_disagree(auth_client, path):
    pem = (b'-----BEGIN PRIVATE KEY-----\n' + base64.encodebytes(_tampered_both_der())
           + b'-----END PRIVATE KEY-----\n')
    r = auth_client.post(path, data={'pem_content': (CERT + pem).decode(),
                                     'name': f'pq-bad-{uuid.uuid4().hex[:8]}'})
    assert r.status_code == 400, r.data
    assert 'do not match' in get_json(r)['message']


# ------------------------------------------- a password for a key that has none

def _rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.parametrize('encoding', ['pem', 'der'])
def test_unencrypted_rsa_key_given_a_password_is_still_read(encoding):
    from utils.key_codec import load_private_key_any
    key = _rsa_key()
    enc = serialization.Encoding.PEM if encoding == 'pem' else serialization.Encoding.DER
    data = key.private_bytes(enc, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    loaded = load_private_key_any(data, password=b'not-needed')
    assert loaded.public_key().public_numbers() == key.public_key().public_numbers()


@pytest.mark.parametrize('encoding', ['pem', 'der'])
def test_seed_only_ml_dsa_key_given_a_password_is_still_read(encoding):
    from utils.key_codec import load_private_key_any
    data = SEED if encoding == 'pem' else _der(SEED)
    assert _raw_public(load_private_key_any(data, password=b'not-needed')) == _raw_public(load_mldsa_key())


def test_encrypted_key_without_a_password_still_asks_for_one():
    from utils.key_codec import load_private_key_any
    sealed = _rsa_key().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.BestAvailableEncryption(b'secret'))
    with pytest.raises(TypeError):
        load_private_key_any(sealed, password=None)


# ------------------------------------------- the "both" check: rho, tr and length

def _both_with_expanded(transform):
    """The "both" fixture with its expanded key passed through *transform*, re-encoded."""
    from pyasn1.codec.der import decoder, encoder
    from pyasn1.type import univ
    from pyasn1_modules import rfc5958
    info, _ = decoder.decode(_der(BOTH), asn1Spec=rfc5958.OneAsymmetricKey())
    both, _ = decoder.decode(bytes(info['privateKey']))
    inner = univ.Sequence()
    inner.setComponentByPosition(0, univ.OctetString(bytes(both[0])))
    inner.setComponentByPosition(1, univ.OctetString(transform(bytes(both[1]))))
    info['privateKey'] = encoder.encode(inner)
    return encoder.encode(info)


@pytest.mark.parametrize('transform', [lambda e: e + b'\x00', lambda e: e[:-1]], ids=['longer', 'shorter'])
def test_both_layout_with_an_expanded_key_of_the_wrong_length_is_refused(transform):
    from utils.key_codec import MalformedKey, load_private_key_any
    with pytest.raises(MalformedKey, match='4032'):
        load_private_key_any(_both_with_expanded(transform))


def test_both_layout_rebuilt_unchanged_still_loads():
    from utils.key_codec import load_private_key_any
    assert _raw_public(load_private_key_any(_both_with_expanded(lambda e: e))) == _raw_public(load_mldsa_key())


# ------------------------------------------- tampered keys are named, not "invalid"

def _tampered_both_pem():
    return (b'-----BEGIN PRIVATE KEY-----\n' + base64.encodebytes(_tampered_both_der())
            + b'-----END PRIVATE KEY-----\n')


@pytest.mark.parametrize('target', ['certificate', 'ca', 'csr'])
def test_key_upload_names_a_key_whose_halves_disagree(app, auth_client, target):
    with _keyless_rows(app) as rows:
        _, url, _ = rows[target]
        r = _post(auth_client, url, _tampered_both_pem())
        assert r.status_code == 400, r.data
        assert 'do not match' in get_json(r)['message']


def test_key_matcher_names_a_key_whose_halves_disagree(auth_client):
    r = auth_client.post('/api/v2/tools/match-keys', data=json.dumps(
        {'certificate': CERT.decode(), 'private_key': _tampered_both_pem().decode()}),
        content_type='application/json')
    assert r.status_code == 200, r.data
    [item] = [i for i in get_json(r)['data']['items'] if i['type'] == 'private_key']
    assert item['valid'] is False and 'do not match' in item['error']


@pytest.mark.parametrize('field', ['pem', 'private_key'])
def test_converter_refuses_a_key_whose_halves_disagree(auth_client, field):
    body = ({'pem': (CERT + _tampered_both_pem()).decode()} if field == 'pem'
            else {'pem': CERT.decode(), 'private_key': _tampered_both_pem().decode()})
    r = auth_client.post('/api/v2/tools/convert', data=json.dumps({**body, 'output_format': 'pem'}),
                         content_type='application/json')
    assert r.status_code == 400, r.data
    message = get_json(r)['message']
    assert message.startswith('Private key cannot be used') and 'do not match' in message
