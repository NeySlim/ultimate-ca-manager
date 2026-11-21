"""import/analyze hands back the PEM of each certificate and key only when asked (CertificateInput)."""
import base64
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

URL = '/api/v2/import/analyze'


def _material():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'rep24b.example.com')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
            .sign(key, hashes.SHA256()))
    return key, cert


def _pems(key, cert):
    return (cert.public_bytes(serialization.Encoding.PEM).decode(),
            key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode())


def _by_type(objects):
    return {o['type']: o for o in objects}


def test_pem_text_returns_cert_and_key_pem_on_request(auth_client):
    key, cert = _material()
    cert_pem, key_pem = _pems(key, cert)
    r = auth_client.post(URL, json={'content': cert_pem + key_pem, 'include_pem': True})
    assert r.status_code == 200, r.data[:300]
    objs = _by_type(r.get_json()['data']['objects'])
    assert objs['certificate']['pem'].strip() == cert_pem.strip()
    assert objs['private_key']['pem'].strip() == key_pem.strip()


def test_pkcs12_with_password_returns_pem_on_request(auth_client):
    key, cert = _material()
    p12 = pkcs12.serialize_key_and_certificates(
        b'x', key, cert, None, serialization.BestAvailableEncryption(b'pw-123'))
    r = auth_client.post(URL, json={
        'content': base64.b64encode(p12).decode(), 'password': 'pw-123', 'include_pem': True})
    assert r.status_code == 200, r.data[:300]
    objs = _by_type(r.get_json()['data']['objects'])
    assert objs['certificate']['pem'].startswith('-----BEGIN CERTIFICATE-----')
    assert 'PRIVATE KEY-----' in objs['private_key']['pem']


def test_no_pem_without_the_flag(auth_client):
    key, cert = _material()
    cert_pem, key_pem = _pems(key, cert)
    r = auth_client.post(URL, json={'content': cert_pem + key_pem})
    assert r.status_code == 200
    assert all('pem' not in o for o in r.get_json()['data']['objects'])


def test_a_sealed_key_gets_no_pem_until_the_password_opens_it(auth_client):
    key, _ = _material()
    sealed = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                               serialization.BestAvailableEncryption(b'pw-123')).decode()

    def keys(body):
        r = auth_client.post(URL, json={'content': sealed, 'include_pem': True, **body})
        assert r.status_code == 200, r.data[:300]
        return r.get_json()['data']['objects']

    for body in ({}, {'password': 'wrong'}):
        (obj,) = keys(body)
        assert obj['is_encrypted'] is True and 'pem' not in obj
    (obj,) = keys({'password': 'pw-123'})
    assert 'ENCRYPTED' not in obj['pem'] and 'PRIVATE KEY-----' in obj['pem']
