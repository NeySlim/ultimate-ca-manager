"""Converter: the output password encrypts the key a PEM output carries, and a DER key is refused with one."""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

URL = '/api/v2/tools/convert'
PASSWORD = 'Out-Pass-12345'


@pytest.fixture(scope='module')
def material():
    key = rsa.generate_private_key(65537, 2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'convert-out.test')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    return {
        'cert': cert.public_bytes(serialization.Encoding.PEM).decode(),
        'key': key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption()).decode(),
    }


def _convert(client, body):
    return client.post(URL, data=json.dumps(body), content_type='application/json')


def _pem_key_only(material, **extra):
    return {'pem': material['key'], 'output_format': 'pem', **extra}


@pytest.mark.parametrize('name', ['output_password', 'pkcs12_password'])
def test_pem_output_with_a_password_encrypts_the_key(auth_client, material, name):
    r = _convert(auth_client, _pem_key_only(material, **{name: PASSWORD}))
    assert r.status_code == 200, r.data
    out = r.get_json()['data']['data']
    assert 'BEGIN ENCRYPTED PRIVATE KEY' in out
    serialization.load_pem_private_key(out.encode(), password=PASSWORD.encode())


def test_pem_output_without_a_password_stays_clear(auth_client, material):
    r = _convert(auth_client, _pem_key_only(material))
    assert r.status_code == 200, r.data
    out = r.get_json()['data']['data']
    assert 'BEGIN PRIVATE KEY' in out and 'ENCRYPTED' not in out


def test_pem_output_refuses_a_password_the_export_rule_refuses(auth_client, material):
    r = _convert(auth_client, _pem_key_only(material, output_password='short'))
    assert r.status_code == 400, r.data


def test_pem_output_of_a_certificate_alone_ignores_the_password(auth_client, material):
    r = _convert(auth_client, {'pem': material['cert'], 'output_format': 'pem', 'output_password': PASSWORD})
    assert r.status_code == 200, r.data
    assert 'BEGIN CERTIFICATE' in r.get_json()['data']['data']


def test_der_output_that_carries_a_key_refuses_a_password(auth_client, material):
    r = _convert(auth_client, {'pem': material['key'], 'output_format': 'der', 'output_password': PASSWORD})
    assert r.status_code == 400, r.data
    assert 'output_password' in r.get_json()['message']


def test_der_output_of_a_certificate_ignores_the_password(auth_client, material):
    r = _convert(auth_client, {'pem': material['cert'], 'output_format': 'der', 'output_password': PASSWORD})
    assert r.status_code == 200, r.data
    base64.b64decode(r.get_json()['data']['data'])


def test_the_two_names_must_agree(auth_client, material):
    r = _convert(auth_client, _pem_key_only(material, output_password=PASSWORD, pkcs12_password='Another-Pass-9'))
    assert r.status_code == 400, r.data


def test_pkcs12_accepts_the_neutral_name(auth_client, material):
    r = _convert(auth_client, {'pem': material['cert'], 'private_key': material['key'],
                               'output_format': 'pkcs12', 'output_password': PASSWORD})
    assert r.status_code == 200, r.data
