"""enroll-import takes what the account page sends for a binary .cer: BASE64:<DER>."""
import base64

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from tests.test_mtls_serial_per_issuer import same_serial  # noqa: F401

URL = '/api/v2/mtls/enroll-import'


def _der(pem):
    return x509.load_pem_x509_certificate(pem.encode()).public_bytes(serialization.Encoding.DER)


def test_a_der_file_sent_with_the_base64_prefix_is_enrolled(auth_client, same_serial):  # noqa: F811
    _serial, pem, _ = same_serial
    r = auth_client.post(URL, json={'password': 'changeme123', 'pem': 'BASE64:' + base64.b64encode(_der(pem)).decode()})
    assert r.status_code == 201, r.get_json()


def test_pem_is_still_enrolled(auth_client, same_serial):  # noqa: F811
    _serial, pem, _ = same_serial
    assert auth_client.post(URL, json={'password': 'changeme123', 'pem': pem}).status_code == 201


@pytest.mark.parametrize('pem', [
    'BASE64:not base64 at all!',
    'BASE64:' + base64.b64encode(b'not a certificate').decode(),
    'BASE64:',
    'garbage',
])
def test_an_unreadable_file_is_a_clear_400(auth_client, pem):
    r = auth_client.post(URL, json={'password': 'changeme123', 'pem': pem})
    assert r.status_code == 400
    assert 'certificate' in r.get_json()['message'].lower()
