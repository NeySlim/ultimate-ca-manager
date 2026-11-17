"""FIPS mode refuses PKCS#12 import: the module has no PKCS12KDF, so every
read fails as a wrong password. Each import route answers a 400 with the FIPS
problem type and a message naming PEM and PKCS#8; other binary input stays."""
import base64
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

import fips_mode
from utils.pkcs12_import import REFUSAL, looks_like_pkcs12

PASSWORD = 'fips-import-pw-123'


@pytest.fixture
def fips_on(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)


@pytest.fixture
def fips_off(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)


def _material(cn, ca=False, password=PASSWORD):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    enc = (serialization.BestAvailableEncryption(password.encode()) if password
           else serialization.NoEncryption())
    return cert, pkcs12.serialize_key_and_certificates(cn.encode(), key, cert, None, enc)


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


def _upload(client, url, p12, filename='bundle.p12'):
    return client.post(url, data={'file': (io.BytesIO(p12), filename), 'password': PASSWORD},
                       content_type='multipart/form-data')


def _assert_refused(r):
    body = r.get_json()
    assert r.status_code == 400, (r.status_code, r.data[:300])
    assert body['type'] == fips_mode.PROBLEM_TYPE, body
    assert body['message'] == REFUSAL, body


def _pseudo_pem(p12):
    return '-----BEGIN PKCS12-----\n' + base64.encodebytes(p12).decode() + '-----END PKCS12-----\n'


SITES = {
    'decoder': lambda c, p12, cn: _post(c, '/api/v2/tools/decode-cert',
                                        {'pem': 'BASE64:' + base64.b64encode(p12).decode()}),
    'converter': lambda c, p12, cn: _post(c, '/api/v2/tools/convert',
                                          {'pem': 'BASE64:' + base64.b64encode(p12).decode(),
                                           'password': PASSWORD, 'output_format': 'pem'}),
    'ca-import': lambda c, p12, cn: _upload(c, '/api/v2/cas/import', p12),
    'certificate-import': lambda c, p12, cn: _upload(c, '/api/v2/certificates/import', p12, 'leaf.pfx'),
    'smart-analyze-base64': lambda c, p12, cn: _post(c, '/api/v2/import/analyze',
                                                     {'content': base64.b64encode(p12).decode(),
                                                      'password': PASSWORD}),
    'smart-analyze-wrapped': lambda c, p12, cn: _post(c, '/api/v2/import/analyze',
                                                      {'content': _pseudo_pem(p12), 'password': PASSWORD}),
    'smart-execute': lambda c, p12, cn: _post(c, '/api/v2/import/execute',
                                              {'content': base64.b64encode(p12).decode(),
                                               'password': PASSWORD,
                                               'options': {'description_prefix': cn + ' '}}),
}


@pytest.mark.parametrize('site', SITES)
def test_pkcs12_import_is_refused_in_fips_mode(site, fips_on, auth_client):
    # The decoder passes no password: give it an archive it could read otherwise
    _, p12 = _material(f'fips-p12-{site}.test', ca=site == 'ca-import',
                       password=None if site == 'decoder' else PASSWORD)
    _assert_refused(SITES[site](auth_client, p12, site))


@pytest.mark.parametrize('site', SITES)
def test_pkcs12_import_unchanged_outside_fips_mode(site, fips_off, auth_client):
    _, p12 = _material(f'std-p12-{site}.test', ca=site == 'ca-import',
                       password=None if site == 'decoder' else PASSWORD)
    r = SITES[site](auth_client, p12, site)
    assert r.status_code in (200, 201), (r.status_code, r.data[:300])
    body = r.get_json()
    if site.startswith('smart-analyze'):
        assert body['data']['objects'], body
    if site == 'smart-execute':
        assert body['data']['success'] is True, body


def test_der_certificate_still_decodes_in_fips_mode(fips_on, auth_client):
    cert, _ = _material('fips-der.test')
    der = cert.public_bytes(serialization.Encoding.DER)
    r = _post(auth_client, '/api/v2/tools/decode-cert', {'pem': 'BASE64:' + base64.b64encode(der).decode()})
    assert r.status_code == 200, r.data[:300]
    r = _post(auth_client, '/api/v2/import/analyze', {'content': base64.b64encode(der).decode()})
    assert r.status_code == 200, r.data[:300]
    assert r.get_json()['data']['objects']


def test_pkcs12_shape_detection():
    cert, p12 = _material('shape.test')
    key = ec.generate_private_key(ec.SECP256R1())
    assert looks_like_pkcs12(p12)
    assert looks_like_pkcs12(_material('shape2.test', password=None)[1])
    assert not looks_like_pkcs12(cert.public_bytes(serialization.Encoding.DER))
    assert not looks_like_pkcs12(key.private_bytes(serialization.Encoding.DER,
                                                   serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()))
    assert not looks_like_pkcs12(b'\x30\x03\x02\x01\x03')
    assert not looks_like_pkcs12('not bytes')
