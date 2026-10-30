"""ML-DSA CA chains: pure and mixed hierarchies, external-CSR CAs whose CSR
OpenSSL 3.5 verifies, and a renewal that keeps the key."""
import base64
import json
import re
import shutil
import subprocess

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, mldsa, rsa

from models import CA, Certificate, db
from services.ca.ca_service import CAService
from services.trust_store import TrustStoreService
from utils import key_algorithms

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')

OPENSSL = shutil.which('openssl')


def _openssl_35():
    if not OPENSSL:
        return False
    out = subprocess.run([OPENSSL, 'version'], capture_output=True, text=True).stdout
    m = re.match(r'OpenSSL (\d+)\.(\d+)', out)
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= (3, 5)


needs_openssl_35 = pytest.mark.skipif(not _openssl_35(), reason='needs OpenSSL 3.5 or later')


def _post(client, url, body):
    return client.post(url, content_type='application/json', data=json.dumps(body))


def _pem(obj):
    return obj.public_bytes(serialization.Encoding.PEM)


def _spki(key):
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def _row_cert(row):
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


def _ca(app, auth_client, label, parent=None, **extra):
    body = {'type': 'intermediate' if parent else 'root', 'commonName': f'Chain {label} under {parent}',
            'keyAlgo': label, 'validityYears': 3, **extra}
    if parent:
        body['parentCAId'] = parent
    r = _post(auth_client, '/api/v2/cas', body)
    assert r.status_code == 201, r.get_json()
    ca_id = r.get_json()['data']['id']
    with app.app_context():
        return ca_id, _row_cert(db.session.get(CA, ca_id))


def _openssl_verify(tmp_path, leaf, root, *inters):
    if not _openssl_35():
        return
    (tmp_path / 'root.pem').write_bytes(_pem(root))
    (tmp_path / 'leaf.pem').write_bytes(_pem(leaf))
    args = [OPENSSL, 'verify', '-CAfile', 'root.pem']
    if inters:
        (tmp_path / 'inter.pem').write_bytes(b''.join(_pem(c) for c in inters))
        args += ['-untrusted', 'inter.pem']
    out = subprocess.run([*args, 'leaf.pem'], capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr


def test_ml_dsa_87_root_65_intermediate_ec_leaf(app, auth_client, tmp_path):
    root_id, root = _ca(app, auth_client, 'ML-DSA-87')
    sub_id, sub = _ca(app, auth_client, 'ML-DSA-65', parent=root_id)
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': 'ec-under-mldsa.example.test', 'ca_id': sub_id, 'key_type': 'ec', 'key_size': '256',
        'validity_days': 30})
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        leaf = _row_cert(db.session.get(Certificate, r.get_json()['data']['id']))
    assert isinstance(root.public_key(), mldsa.MLDSA87PublicKey)
    assert isinstance(sub.public_key(), mldsa.MLDSA65PublicKey)
    assert isinstance(leaf.public_key(), ec.EllipticCurvePublicKey)
    assert sub.signature_hash_algorithm is None and leaf.signature_hash_algorithm is None
    sub.verify_directly_issued_by(root)
    leaf.verify_directly_issued_by(sub)
    _openssl_verify(tmp_path, leaf, root, sub)


def test_ml_dsa_intermediate_under_rsa_root(app, auth_client, tmp_path):
    root_id, root = _ca(app, auth_client, 'RSA-3072')
    sub_id, sub = _ca(app, auth_client, 'ML-DSA-65', parent=root_id)
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': 'rsa-under-mldsa.example.test', 'ca_id': sub_id, 'validity_days': 30})
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        leaf = _row_cert(db.session.get(Certificate, r.get_json()['data']['id']))
    assert isinstance(sub.public_key(), mldsa.MLDSA65PublicKey)
    assert sub.signature_hash_algorithm is not None    # signed by the RSA root
    assert isinstance(leaf.public_key(), rsa.RSAPublicKey)
    sub.verify_directly_issued_by(root)
    leaf.verify_directly_issued_by(sub)
    _openssl_verify(tmp_path, leaf, root, sub)


def _notices(r):
    return (r.get_json().get('meta') or {}).get('notices') or []


def test_digest_of_an_intermediate_follows_the_signing_parent(app, auth_client):
    # An RSA parent signs the ML-DSA child: the requested digest applies, no notice
    root_id, _root = _ca(app, auth_client, 'RSA-3072')
    r = _post(auth_client, '/api/v2/cas', {'type': 'intermediate', 'parentCAId': root_id,
                                           'commonName': 'ML-DSA sub sha384', 'keyAlgo': 'ML-DSA-65',
                                           'digest': 'sha384', 'validityYears': 2})
    assert r.status_code == 201, r.get_json()
    assert not any('ignored' in n for n in _notices(r)), _notices(r)
    with app.app_context():
        sub = _row_cert(db.session.get(CA, r.get_json()['data']['id']))
    assert sub.signature_hash_algorithm.name == 'sha384'

    # An ML-DSA parent signs the RSA child: the digest is ignored and the notice names the parent key
    mldsa_root_id, mldsa_root = _ca(app, auth_client, 'ML-DSA-65')
    r = _post(auth_client, '/api/v2/cas', {'type': 'intermediate', 'parentCAId': mldsa_root_id,
                                           'commonName': 'RSA sub sha384', 'keyAlgo': 'RSA-3072',
                                           'digest': 'sha384', 'validityYears': 2})
    assert r.status_code == 201, r.get_json()
    assert any('sha384 ignored' in n and 'ML-DSA-65' in n for n in _notices(r)), _notices(r)
    with app.app_context():
        sub = _row_cert(db.session.get(CA, r.get_json()['data']['id']))
    assert sub.signature_hash_algorithm is None
    sub.verify_directly_issued_by(mldsa_root)


# ---- external-CSR CA ------------------------------------------------------------

def _external_ca(auth_client, **extra):
    r = _post(auth_client, '/api/v2/cas', {'type': 'external', 'commonName': 'PQ external CA',
                                           'keyAlgo': 'ML-DSA', 'keySize': 65, **extra})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _ca_csr(auth_client, ca_id):
    r = auth_client.get(f'/api/v2/cas/{ca_id}/csr')
    assert r.status_code == 200
    return r.data


@needs_openssl_35
def test_external_ml_dsa_ca_csr_verifies_with_openssl(auth_client, tmp_path):
    ca_id = _external_ca(auth_client)['data']['id']
    pem = _ca_csr(auth_client, ca_id)
    csr = x509.load_pem_x509_csr(pem)
    assert isinstance(csr.public_key(), mldsa.MLDSA65PublicKey) and csr.is_signature_valid
    (tmp_path / 'ca.csr').write_bytes(pem)
    out = subprocess.run([OPENSSL, 'req', '-verify', '-noout', '-in', 'ca.csr'],
                         capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0 and 'verify OK' in (out.stdout + out.stderr), out.stdout + out.stderr


def test_external_ml_dsa_ca_digest_is_ignored_with_a_notice(auth_client):
    body = _external_ca(auth_client, hashAlgorithm='sha512')
    assert any('sha512' in n and 'ignored' in n for n in (body.get('meta') or {}).get('notices') or [])
    csr = x509.load_pem_x509_csr(_ca_csr(auth_client, body['data']['id']))
    assert csr.signature_hash_algorithm is None and csr.is_signature_valid


def test_external_ml_dsa_ca_installed_then_renewed_keeps_its_key(app, auth_client, tmp_path):
    ca_id = _external_ca(auth_client)['data']['id']
    first = x509.load_pem_x509_csr(_ca_csr(auth_client, ca_id))
    # The external signer is another UCM CA: an ML-DSA-87 root
    root_id, root = _ca(app, auth_client, 'ML-DSA-87')
    with app.app_context():
        root_row = db.session.get(CA, root_id)
        from services.hsm.ca_key_loader import get_ca_signing_key
        signed = TrustStoreService.sign_csr(_pem(first), root, get_ca_signing_key(root_row),
                                            validity_days=365, cert_type='intermediate_ca')
    r = _post(auth_client, f'/api/v2/cas/{ca_id}/certificate', {'pem_content': signed.decode()})
    assert r.status_code == 200, r.get_json()

    r = _post(auth_client, f'/api/v2/cas/{ca_id}/renew-csr', {'digest': 'sha384'})
    assert r.status_code == 200, r.get_json()
    assert any('sha384' in n and 'ignored' in n for n in (r.get_json().get('meta') or {}).get('notices') or [])
    renewed = x509.load_pem_x509_csr(_ca_csr(auth_client, ca_id))
    assert renewed.is_signature_valid and renewed.signature_hash_algorithm is None
    assert _spki(renewed.public_key()) == _spki(first.public_key())
    with app.app_context():
        installed = _row_cert(db.session.get(CA, ca_id))
    assert _spki(installed.public_key()) == _spki(first.public_key())
    installed.verify_directly_issued_by(root)
    _openssl_verify(tmp_path, installed, root)


def test_renew_csr_still_refuses_an_unknown_digest(auth_client):
    ca_id = _external_ca(auth_client)['data']['id']
    r = _post(auth_client, f'/api/v2/cas/{ca_id}/renew-csr', {'digest': 'md5'})
    assert r.status_code == 400


def test_regenerate_ca_csr_signs_ml_dsa_without_a_digest(app):
    """CAService entry point, the digest left to the key."""
    ca_id = None
    with app.app_context():
        ca = CAService.create_external_ca(descr='PQ regen', dn={'CN': 'PQ regen'}, key_type='ml-dsa-44',
                                          digest=None)
        ca_id = ca.id
        pem = CAService.regenerate_ca_csr(db.session.get(CA, ca_id))
    csr = x509.load_pem_x509_csr(pem)
    assert isinstance(csr.public_key(), mldsa.MLDSA44PublicKey) and csr.is_signature_valid
