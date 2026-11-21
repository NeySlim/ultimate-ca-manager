"""Guards, not fixes: the converter route already took `password` before the page asked for it (no server change in that lot).

The converter opens an encrypted private key (pasted or separate) with `password`, and never logs it.
"""
import logging

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

URL = '/api/v2/tools/convert'
SECRET = 'S3cret-conv-pass-xyz'


def _material(password=SECRET):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'rep24b-conv.example.com')])
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
            .sign(key, hashes.SHA256()))
    sealed = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                               serialization.BestAvailableEncryption(password.encode())).decode()
    return cert.public_bytes(serialization.Encoding.PEM).decode(), sealed


def test_separate_encrypted_key_opens_with_the_password(auth_client):
    cert, sealed = _material()
    r = auth_client.post(URL, json={'pem': cert, 'private_key': sealed, 'output_format': 'pem',
                                    'password': SECRET})
    assert r.status_code == 200, r.data[:300]
    assert 'PRIVATE KEY-----' in r.get_json()['data']['data'] and 'ENCRYPTED' not in r.get_json()['data']['data']


def test_pasted_encrypted_pem_opens_with_the_password(auth_client):
    cert, sealed = _material()
    r = auth_client.post(URL, json={'pem': cert + sealed, 'output_format': 'pem', 'password': SECRET})
    assert r.status_code == 200, r.data[:300]
    assert 'ENCRYPTED' not in r.get_json()['data']['data']


def test_a_wrong_password_is_refused_and_not_echoed_or_logged(auth_client, caplog):
    cert, sealed = _material()
    with caplog.at_level(logging.DEBUG):
        r = auth_client.post(URL, json={'pem': cert, 'private_key': sealed, 'output_format': 'pem',
                                        'password': 'not-the-password-123'})
    assert r.status_code == 400, r.data[:300]
    assert 'not-the-password-123' not in r.get_data(as_text=True)
    assert 'not-the-password-123' not in caplog.text and SECRET not in caplog.text


def test_the_right_password_is_not_logged(auth_client, caplog):
    cert, sealed = _material()
    with caplog.at_level(logging.DEBUG):
        auth_client.post(URL, json={'pem': cert, 'private_key': sealed, 'output_format': 'pem',
                                    'password': SECRET})
    assert SECRET not in caplog.text
