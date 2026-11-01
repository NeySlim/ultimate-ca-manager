"""The import routes outside smart import cost a PKCS#12 or an encrypted PKCS#8 before
cryptography derives anything from it: too costly answers 400 and no loader runs.
Counted, not timed."""
import base64
import datetime
import io
import json
import shutil
import subprocess
import uuid

import pytest
from asn1crypto import pkcs12 as asn1_pkcs12
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import PrivateFormat, pkcs12
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db
from services.import_service import KeyPasswordError, load_import_private_key, parse_certificate_file
from services.smart_import.parser import MAX_KDF_ITERATIONS, UNINSPECTED_KEY
from tests.conftest import get_json
from tests.test_smart_import_kdf_budget import RIGHT, _key_sealed_in_a_layer, _pkcs12, _with_iterations

COSTLY = f'{MAX_KDF_ITERATIONS + 1} iterations'
GOOD_PWD = 'Sup3rStr0ng!Pass#2026'


@pytest.fixture
def loads(monkeypatch):
    """Every call of a cryptography key or PKCS#12 loader: each one derives keys."""
    calls = []
    for module, name in ((serialization, 'load_pem_private_key'), (serialization, 'load_der_private_key'),
                         (pkcs12, 'load_key_and_certificates')):
        def counted(*args, _real=getattr(module, name), _name=name, **kwargs):
            calls.append(_name)
            return _real(*args, **kwargs)
        monkeypatch.setattr(module, name, counted)
    return calls


def _material(cn):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256()))
    return key, cert


def _costly_mac():
    pfx = asn1_pkcs12.Pfx.load(_pkcs12())
    pfx['mac_data']['iterations'] = MAX_KDF_ITERATIONS + 1
    return pfx.dump(force=True)


def _sealed_der(key, iterations=None):
    der = key.private_bytes(serialization.Encoding.DER, PrivateFormat.PKCS8,
                            serialization.BestAvailableEncryption(RIGHT))
    return der if iterations is None else _with_iterations(der, iterations)


def _pem(der, header=b''):
    return (b'-----BEGIN ENCRYPTED PRIVATE KEY-----\n' + header + base64.encodebytes(der)
            + b'-----END ENCRYPTED PRIVATE KEY-----\n')


def _costly_key_pem():
    return _pem(_sealed_der(ec.generate_private_key(ec.SECP256R1()), MAX_KDF_ITERATIONS + 1))


def _upload(client, url, data, filename, password=RIGHT.decode()):
    return client.post(url, data={'file': (io.BytesIO(data), filename), 'password': password},
                       content_type='multipart/form-data')


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


# ---- PKCS#12 import (certificates and CAs) ------------------------------------

COSTLY_P12 = {'mac': (_costly_mac, 'PKCS#12 MAC'),
              'key-in-layer': (lambda: _key_sealed_in_a_layer('pbes2', MAX_KDF_ITERATIONS + 1), COSTLY)}


@pytest.mark.parametrize('url', ['/api/v2/certificates/import', '/api/v2/cas/import'])
@pytest.mark.parametrize('case', COSTLY_P12)
def test_a_costly_pkcs12_import_is_refused_unloaded(auth_client, loads, url, case):
    build, said = COSTLY_P12[case]
    r = _upload(auth_client, url, build(), 'bundle.p12')
    assert r.status_code == 400, r.data
    assert said in get_json(r)['message']
    assert loads == []


def _openssl_p12(tmp_path, *options, password=RIGHT.decode()):
    key, cert, out = tmp_path / 'k.pem', tmp_path / 'c.pem', tmp_path / 'b.p12'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:P-256',
                    '-nodes', '-keyout', key, '-out', cert, '-subj', f'/CN={uuid.uuid4().hex}.test',
                    '-days', '2'], check=True, capture_output=True)
    subprocess.run(['openssl', 'pkcs12', '-export', *options, '-inkey', key, '-in', cert,
                    '-passout', 'pass:' + password, '-out', out], check=True, capture_output=True)
    return out.read_bytes()


@pytest.mark.skipif(shutil.which('openssl') is None, reason='openssl CLI not available')
@pytest.mark.parametrize('options', [[], ['-legacy']], ids=['default', 'legacy'])
def test_openssl_pkcs12_still_imports(tmp_path, loads, options):
    cert, key, kind = parse_certificate_file(_openssl_p12(tmp_path, *options), 'b.p12', RIGHT.decode())
    assert kind == 'pkcs12' and cert is not None and key is not None
    assert loads == ['load_key_and_certificates']
    with pytest.raises(KeyPasswordError, match='Invalid password for PKCS12 file'):
        parse_certificate_file(_openssl_p12(tmp_path, *options), 'b.p12', 'wrong')


def test_a_pkcs12_import_still_lands(app, auth_client):
    key, cert = _material(f'kdf-import-{uuid.uuid4().hex[:8]}.test')
    p12 = pkcs12.serialize_key_and_certificates(b'k', key, cert, None,
                                                serialization.BestAvailableEncryption(RIGHT))
    subject = cert.subject.rfc4514_string()
    try:
        r = _upload(auth_client, '/api/v2/certificates/import', p12, 'leaf.pfx')
        assert r.status_code in (200, 201), r.data
    finally:
        with app.app_context():
            Certificate.query.filter_by(subject=subject).delete()
            db.session.commit()


# ---- encrypted PKCS#8 with a password (import and key upload routes) ----------

@pytest.mark.parametrize('url', ['/api/v2/certificates/import', '/api/v2/cas/import'])
def test_a_costly_key_beside_an_imported_certificate_is_refused_unloaded(auth_client, loads, url):
    key, cert = _material('kdf-pem.test')
    sealed = _pem(_sealed_der(key, MAX_KDF_ITERATIONS + 1))
    pem = cert.public_bytes(serialization.Encoding.PEM) + sealed
    r = auth_client.post(url, data={'pem_content': pem.decode(), 'password': RIGHT.decode()})
    assert r.status_code == 400, r.data
    assert COSTLY in get_json(r)['message']
    assert loads == []


def test_a_costly_key_upload_is_refused_unloaded(app, auth_client, loads):
    key, cert = _material(f'kdf-key-{uuid.uuid4().hex[:8]}.test')
    crt = base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()
    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        row = CA(refid=f'kdf-ca-{tag}', descr=f'kdf-ca-{tag}', serial=0, crt=crt,
                 subject=cert.subject.rfc4514_string(), issuer=cert.issuer.rfc4514_string(),
                 imported_from='manual')
        db.session.add(row)
        db.session.commit()
        ca_id = row.id
    try:
        sealed = _pem(_sealed_der(key, MAX_KDF_ITERATIONS + 1)).decode()
        r = _post(auth_client, f'/api/v2/cas/{ca_id}/key', {'key': sealed, 'passphrase': RIGHT.decode()})
        assert r.status_code == 400, r.data
        assert COSTLY in get_json(r)['message']
        assert loads == []
        r = _post(auth_client, f'/api/v2/cas/{ca_id}/key',
                  {'key': _pem(_sealed_der(key)).decode(), 'passphrase': RIGHT.decode()})
        assert r.status_code in (200, 201), r.data
    finally:
        with app.app_context():
            CA.query.filter_by(refid=f'kdf-ca-{tag}').delete()
            db.session.commit()


@pytest.mark.parametrize('variant', ['header', 'two-blocks', 'not-pkcs8'])
def test_an_encrypted_key_that_cannot_be_inspected_is_not_tried(loads, variant):
    der = _sealed_der(ec.generate_private_key(ec.SECP256R1()), MAX_KDF_ITERATIONS + 1)
    data = {'header': _pem(der, b'Comment: hidden from a strict reader\n\n'),
            'two-blocks': _pem(_sealed_der(ec.generate_private_key(ec.SECP256R1()))) + _pem(der),
            'not-pkcs8': _pem(b'\x30\x03\x02\x01\x00')}[variant]
    with pytest.raises(KeyPasswordError, match=UNINSPECTED_KEY):
        load_import_private_key(data, RIGHT)
    assert loads == []


def _openssl_scrypt(key):
    plain = key.private_bytes(serialization.Encoding.PEM, PrivateFormat.PKCS8, serialization.NoEncryption())
    return subprocess.run(['openssl', 'pkcs8', '-topk8', '-scrypt', '-passout', 'pass:' + RIGHT.decode()],
                          input=plain, check=True, capture_output=True).stdout


@pytest.mark.parametrize('form', ['pkcs8', 'scrypt', 'traditional'])
def test_affordable_encrypted_keys_still_open(form):
    key = ec.generate_private_key(ec.SECP256R1())
    if form == 'pkcs8':
        pem = _pem(_sealed_der(key))
    elif form == 'scrypt':
        if shutil.which('openssl') is None:
            pytest.skip('openssl CLI not available')
        pem = _openssl_scrypt(key)
        assert b'ENCRYPTED PRIVATE KEY' in pem
    else:
        pem = key.private_bytes(serialization.Encoding.PEM, PrivateFormat.TraditionalOpenSSL,
                                serialization.BestAvailableEncryption(RIGHT))
        assert b'DEK-Info' in pem
    assert load_import_private_key(pem, RIGHT).private_numbers() == key.private_numbers()
    with pytest.raises(KeyPasswordError, match='Invalid password'):
        load_import_private_key(pem, b'wrong')


# ---- tools: certificate decoder, key matcher ------------------------------------

def test_the_decoder_costs_a_pkcs12_it_opens_without_a_password(auth_client, loads):
    r = _post(auth_client, '/api/v2/tools/decode-cert', {'pem': 'BASE64:' + base64.b64encode(_costly_mac()).decode()})
    assert r.status_code == 400, r.data
    assert 'PKCS#12 MAC' in get_json(r)['message']
    assert loads == []


@pytest.mark.skipif(shutil.which('openssl') is None, reason='openssl CLI not available')
@pytest.mark.parametrize('options', [[], ['-legacy']], ids=['default', 'legacy'])
def test_the_decoder_still_reads_an_openssl_pkcs12_without_password(tmp_path, auth_client, options):
    p12 = _openssl_p12(tmp_path, *options, password='')
    r = _post(auth_client, '/api/v2/tools/decode-cert', {'pem': 'BASE64:' + base64.b64encode(p12).decode()})
    assert r.status_code == 200, r.data


def test_the_key_matcher_costs_an_encrypted_key(auth_client, loads):
    key, cert = _material('kdf-match.test')
    body = {'certificate': cert.public_bytes(serialization.Encoding.PEM).decode(),
            'private_key': _pem(_sealed_der(key, MAX_KDF_ITERATIONS + 1)).decode(), 'password': RIGHT.decode()}
    r = _post(auth_client, '/api/v2/tools/match-keys', body)
    assert r.status_code == 400, r.data
    assert COSTLY in get_json(r)['message']
    assert loads == []
    for private_key in (_pem(_sealed_der(key)).decode(), 'BASE64:' + base64.b64encode(_sealed_der(key)).decode()):
        r = _post(auth_client, '/api/v2/tools/match-keys', {**body, 'private_key': private_key})
        assert r.status_code == 200 and get_json(r)['data']['all_match'], r.data


# ---- restoring an offline CA from its exported key file -------------------------

def test_restoring_a_ca_from_a_costly_key_file_is_refused_unloaded(auth_client, create_ca, loads):
    ca = create_ca()
    export = _post(auth_client, f'/api/v2/cas/{ca["id"]}/offline', {'password': GOOD_PWD, 'mode': 'file_exported'})
    assert export.status_code == 200, export.data
    der = base64.b64decode(b''.join(export.data.split(b'\n')[1:-2]))
    loads.clear()

    def restore(data):
        return auth_client.post(f'/api/v2/cas/{ca["id"]}/restore', content_type='multipart/form-data',
                                data={'password': GOOD_PWD, 'key_file': (io.BytesIO(data), 'ca.key')})
    r = restore(_pem(_with_iterations(der, MAX_KDF_ITERATIONS + 1)))
    assert r.status_code == 400, r.data
    assert COSTLY in get_json(r)['message']
    assert loads == []
    r = restore(export.data)
    assert r.status_code == 200, r.data
    assert get_json(r)['data']['offline'] is False
