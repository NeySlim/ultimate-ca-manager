"""EST and ML-DSA: simpleenroll under an ML-DSA and an RSA CA, serverkeygen that makes
RSA-2048 whatever the request key, cacerts read by OpenSSL, and the weak-hash diagnosis of an ML-DSA CSR."""
import base64
import subprocess

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs7

from models import CA, SystemConfig, db
from tests.test_acme_pq import OPENSSL, needs_openssl_35, openssl_mldsa_csr
from utils import key_algorithms

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')

EST_BASE = '/.well-known/est'
EST_USER = 'est-pq'
EST_PASSWORD = 'est-pq-password'
_KEYS = ('est_enabled', 'est_ca_refid', 'est_username', 'est_password', 'est_validity_days')


def _set_config(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


@pytest.fixture(scope='module')
def est_cas(create_ca):
    return {'rsa': create_ca(cn='EST PQ RSA root'),
            'mldsa': create_ca(cn='EST PQ ML-DSA-65 root', keyAlgo='ML-DSA', keySize=65)}


@pytest.fixture
def est_ca(app, est_cas):
    """EST enabled on the CA a test names; the previous settings come back afterwards."""
    with app.app_context():
        previous = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None)
                    for k in _KEYS}

    def _use(which):
        with app.app_context():
            ca = db.session.get(CA, est_cas[which]['id'])
            for key, value in (('est_enabled', 'true'), ('est_ca_refid', ca.refid),
                               ('est_username', EST_USER), ('est_password', EST_PASSWORD),
                               ('est_validity_days', '30')):
                _set_config(key, value)
            return x509.load_pem_x509_certificate(base64.b64decode(ca.crt))

    yield _use
    with app.app_context():
        for key, value in previous.items():
            row = SystemConfig.query.filter_by(key=key).first()
            if value is None:
                if row is not None:
                    db.session.delete(row)
            elif row is None:
                db.session.add(SystemConfig(key=key, value=value))
            else:
                row.value = value
        db.session.commit()


def _auth():
    return {'Authorization': 'Basic ' + base64.b64encode(f'{EST_USER}:{EST_PASSWORD}'.encode()).decode()}


def _post(client, path, der):
    return client.post(f'{EST_BASE}/{path}', data=base64.b64encode(der), headers=_auth(),
                       content_type='application/pkcs10')


@needs_openssl_35
@pytest.mark.parametrize('which', ['mldsa', 'rsa'])
def test_simpleenroll_issues_an_mldsa_leaf(client, est_ca, tmp_path, which):
    ca_cert = est_ca(which)
    csr, key = openssl_mldsa_csr(tmp_path, f'est-{which}.pq.example.test')
    r = _post(client, 'simpleenroll', csr.public_bytes(serialization.Encoding.DER))
    assert r.status_code == 200, r.data
    (leaf,) = pkcs7.load_der_pkcs7_certificates(base64.b64decode(r.data))
    assert key_algorithms.label_for_public_key(leaf.public_key()) == 'ML-DSA-44'
    assert leaf.public_key() == key.public_key()
    leaf.verify_directly_issued_by(ca_cert)


@needs_openssl_35
def test_a_tampered_mldsa_request_fails_proof_of_possession(client, est_ca, tmp_path):
    est_ca('rsa')
    csr, _ = openssl_mldsa_csr(tmp_path, 'tampered.pq.example.test')
    der = bytearray(csr.public_bytes(serialization.Encoding.DER))
    der[-1] ^= 0x01
    r = _post(client, 'simpleenroll', bytes(der))
    assert r.status_code == 400
    assert b'proof of possession failed' in r.data


@needs_openssl_35
@pytest.mark.parametrize('which', ['mldsa', 'rsa'])
@pytest.mark.parametrize('tampered', [False, True])
def test_fips_mode_refuses_an_mldsa_request_before_its_signature(client, est_ca, tmp_path,
                                                                 monkeypatch, which, tampered):
    """A FIPS provider without ML-DSA cannot verify the request: the refusal names FIPS, not PoP."""
    import fips_mode
    est_ca(which)
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    csr, _ = openssl_mldsa_csr(tmp_path, f'fips-{which}.pq.example.test')
    der = bytearray(csr.public_bytes(serialization.Encoding.DER))
    if tampered:
        der[-1] ^= 0x01
    r = _post(client, 'simpleenroll', bytes(der))
    assert r.status_code == 400, r.data
    assert r.data == b'ML-DSA-44 keys are not available in FIPS mode'


def test_weak_hash_diagnosis_is_none_for_mldsa(mldsa_csr):
    from utils.csr_diagnostics import weak_csr_hash_algorithm
    assert mldsa_csr.signature_hash_algorithm is None
    assert weak_csr_hash_algorithm(mldsa_csr) is None


def _serverkeygen_leaf(response):
    p7 = response.data.split(b'\r\n\r\n', 1)[1].split(b'\r\n--', 1)[0]
    (leaf,) = pkcs7.load_der_pkcs7_certificates(base64.b64decode(p7))
    return leaf


@needs_openssl_35
@pytest.mark.parametrize('which', ['mldsa', 'rsa'])
def test_serverkeygen_ignores_an_mldsa_request_key(client, est_ca, tmp_path, which):
    """RFC 7030 §4.4.1: the request key is ignored, an ML-DSA one included."""
    est_ca(which)
    cn = f'keygen-{which}.pq.example.test'
    csr, _ = openssl_mldsa_csr(tmp_path, cn)
    r = _post(client, 'serverkeygen', csr.public_bytes(serialization.Encoding.DER))
    assert r.status_code == 200, r.data
    leaf = _serverkeygen_leaf(r)
    assert key_algorithms.label_for_public_key(leaf.public_key()) == 'RSA-2048'
    assert leaf.subject.rfc4514_string() == f'CN={cn}'


def test_serverkeygen_stays_rsa_2048_under_an_mldsa_ca(client, est_ca):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    ca_cert = est_ca('mldsa')
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'keygen.pq.example.test')]))
           .sign(key, hashes.SHA256()))
    r = _post(client, 'serverkeygen', csr.public_bytes(serialization.Encoding.DER))
    assert r.status_code == 200, r.data
    leaf = _serverkeygen_leaf(r)
    assert key_algorithms.label_for_public_key(leaf.public_key()) == 'RSA-2048'
    leaf.verify_directly_issued_by(ca_cert)


@needs_openssl_35
def test_cacerts_of_an_mldsa_ca_reads_with_openssl(client, est_ca, tmp_path):
    ca_cert = est_ca('mldsa')
    r = client.get(f'{EST_BASE}/cacerts')
    assert r.status_code == 200, r.data
    (tmp_path / 'cacerts.p7').write_bytes(base64.b64decode(r.data))
    out = subprocess.run([OPENSSL, 'pkcs7', '-inform', 'DER', '-in', 'cacerts.p7', '-print_certs'],
                         capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    printed = x509.load_pem_x509_certificates(out.stdout.encode())
    assert ca_cert in printed
