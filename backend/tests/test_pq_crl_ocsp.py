"""CRLs and OCSP responses of ML-DSA CAs: signed without a digest, under the OID
of the CA key's own parameter set, and accepted by OpenSSL 3.5 (not pyca alone)."""
import base64
import hashlib
import json
import logging
import re
import shutil
import subprocess

import pytest
from asn1crypto import core as asn1_core, ocsp as asn1_ocsp
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from models import CA, Certificate, SystemConfig, db
from models.crl import CRLMetadata
from utils import key_algorithms

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')

OPENSSL = shutil.which('openssl')
MLDSA65_OID = '2.16.840.1.101.3.4.3.18'


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


def _openssl(tmp_path, *args, **files):
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    return subprocess.run([OPENSSL, *args], capture_output=True, text=True, cwd=tmp_path)


def _row_cert(row):
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


@pytest.fixture(scope='module')
def mldsa65_ca(create_ca):
    return create_ca(cn='PQ CRL OCSP ML-DSA-65 root', keyAlgo='ML-DSA', keySize=65)


@pytest.fixture(scope='module')
def rsa_ca(create_ca):
    return create_ca(cn='PQ CRL OCSP RSA root')


# ---- CRL ------------------------------------------------------------------------

def _latest_crl(ca_id):
    row = CRLMetadata.query.filter_by(ca_id=ca_id, is_delta=False).order_by(
        CRLMetadata.crl_number.desc()).first()
    return x509.load_pem_x509_crl(row.crl_pem.encode())


def test_crl_signature_hash_is_none_for_a_digestless_ca(app, mldsa65_ca, rsa_ca):
    from services.crl.generation import _crl_signature_hash
    with app.app_context():
        assert _crl_signature_hash(db.session.get(CA, mldsa65_ca['id'])) is None
        assert _crl_signature_hash(db.session.get(CA, rsa_ca['id'])).name == 'sha256'


def test_crl_config_names_no_digest_for_an_ml_dsa_ca(auth_client, mldsa65_ca):
    r = auth_client.get(f"/api/v2/crl/{mldsa65_ca['id']}/config")
    assert r.status_code == 200
    assert r.get_json()['data']['crl_digest'] is None
    r = auth_client.get(f"/api/v2/cas/{mldsa65_ca['id']}")
    assert r.get_json()['data']['crl_digest'] is None


@pytest.mark.parametrize('empty', ['', None])
def test_crl_config_accepts_an_empty_digest_for_an_ml_dsa_ca(auth_client, mldsa65_ca, empty):
    r = _post(auth_client, f"/api/v2/crl/{mldsa65_ca['id']}/config", {'digest': empty, 'validity_days': 3})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['crl_digest'] is None
    assert r.get_json()['data']['crl_validity_days'] == 3


def test_crl_config_refuses_to_impose_a_digest_on_an_ml_dsa_ca(app, auth_client, mldsa65_ca):
    r = _post(auth_client, f"/api/v2/crl/{mldsa65_ca['id']}/config", {'digest': 'sha384'})
    assert r.status_code == 400
    assert 'ML-DSA-65' in r.get_json()['message']
    assert 'without a separate digest' in r.get_json()['message']
    with app.app_context():
        assert db.session.get(CA, mldsa65_ca['id']).crl_digest is None


def test_crl_config_still_refuses_an_empty_digest_for_an_rsa_ca(auth_client, rsa_ca):
    r = _post(auth_client, f"/api/v2/crl/{rsa_ca['id']}/config", {'digest': ''})
    assert r.status_code == 400


@needs_openssl_35
def test_ml_dsa_crl_verifies_with_openssl(app, auth_client, create_cert, mldsa65_ca, tmp_path, caplog):
    leaf = create_cert(cn='pq-crl-revoked.example.test', ca_id=mldsa65_ca['id'])
    r = _post(auth_client, f"/api/v2/certificates/{leaf['id']}/revoke", {'reason': 'keyCompromise'})
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        # A digest stored before the CA could refuse it is ignored, and said so
        db.session.get(CA, mldsa65_ca['id']).crl_digest = 'sha384'
        db.session.commit()
    try:
        with caplog.at_level(logging.INFO, logger='services.crl.generation'):
            r = auth_client.post(f"/api/v2/crl/{mldsa65_ca['id']}/regenerate")
        assert r.status_code == 200, r.get_json()
        assert any('sha384 ignored' in m and 'ML-DSA-65' in m for m in caplog.messages), caplog.messages
        with app.app_context():
            crl = _latest_crl(mldsa65_ca['id'])
            ca_cert = _row_cert(db.session.get(CA, mldsa65_ca['id']))
    finally:
        with app.app_context():
            db.session.get(CA, mldsa65_ca['id']).crl_digest = None
            db.session.commit()
    assert crl.signature_algorithm_oid.dotted_string == MLDSA65_OID
    assert crl.signature_hash_algorithm is None
    assert len(list(crl)) >= 1
    out = _openssl(tmp_path, 'crl', '-in', 'crl.pem', '-CAfile', 'ca.pem', '-noout', '-verify',
                   **{'crl.pem': _pem(crl), 'ca.pem': _pem(ca_cert)})
    assert out.returncode == 0 and 'verify OK' in out.stdout + out.stderr, out.stdout + out.stderr


@needs_openssl_35
def test_ml_dsa_delta_crl_verifies_with_openssl(app, auth_client, mldsa65_ca, tmp_path):
    from services.crl import CRLService
    with app.app_context():
        row = db.session.get(CA, mldsa65_ca['id'])
        row.delta_crl_enabled = True
        db.session.commit()
        try:
            CRLService.generate_crl(mldsa65_ca['id'])
            delta = CRLService.generate_delta_crl(mldsa65_ca['id'])
        finally:
            db.session.get(CA, mldsa65_ca['id']).delta_crl_enabled = False
            db.session.commit()
        crl = x509.load_pem_x509_crl(delta.crl_pem.encode())
        ca_cert = _row_cert(db.session.get(CA, mldsa65_ca['id']))
    assert crl.signature_algorithm_oid.dotted_string == MLDSA65_OID
    out = _openssl(tmp_path, 'crl', '-in', 'crl.pem', '-CAfile', 'ca.pem', '-noout', '-verify',
                   **{'crl.pem': _pem(crl), 'ca.pem': _pem(ca_cert)})
    assert out.returncode == 0 and 'verify OK' in out.stdout + out.stderr, out.stdout + out.stderr


@needs_openssl_35
def test_trust_store_crl_of_an_ml_dsa_key_ignores_the_digest(app, mldsa65_ca, tmp_path):
    from services.hsm.ca_key_loader import get_ca_signing_key
    from services.trust_store import TrustStoreService
    with app.app_context():
        row = db.session.get(CA, mldsa65_ca['id'])
        ca_cert, key = _row_cert(row), get_ca_signing_key(row)
    pem = TrustStoreService.generate_crl(ca_cert, key, [], digest='sha512')
    crl = x509.load_pem_x509_crl(pem)
    assert crl.signature_algorithm_oid.dotted_string == MLDSA65_OID
    out = _openssl(tmp_path, 'crl', '-in', 'crl.pem', '-CAfile', 'ca.pem', '-noout', '-verify',
                   **{'crl.pem': pem, 'ca.pem': _pem(ca_cert)})
    assert out.returncode == 0, out.stdout + out.stderr


# ---- OCSP -----------------------------------------------------------------------

class _SPKI(asn1_core.Sequence):
    """SubjectPublicKeyInfo read without interpreting its algorithm."""
    _fields = [('algorithm', asn1_core.Any), ('public_key', asn1_core.BitString)]


def _bit_string(cert):
    """Contents of the subjectPublicKey BIT STRING (RFC 6960 keyHash input), from the DER."""
    tbs = asn1_core.Sequence.load(cert.tbs_certificate_bytes)
    # version [0], serial, signature, issuer, validity, subject, subjectPublicKeyInfo
    return _SPKI.load(tbs[6].dump())['public_key'].contents[1:]


def _enable_ocsp(app, ca_id):
    with app.app_context():
        db.session.get(CA, ca_id).ocsp_enabled = True
        db.session.commit()


def _cert_of(app, model, row_id):
    with app.app_context():
        return _row_cert(db.session.get(model, row_id))


def _leaves(app, auth_client, create_cert, ca_id, tag):
    good = create_cert(cn=f'pq-ocsp-good-{tag}.example.test', ca_id=ca_id)
    revoked = create_cert(cn=f'pq-ocsp-revoked-{tag}.example.test', ca_id=ca_id)
    r = _post(auth_client, f"/api/v2/certificates/{revoked['id']}/revoke", {'reason': 'superseded'})
    assert r.status_code == 200, r.get_json()
    return _cert_of(app, Certificate, good['id']), _cert_of(app, Certificate, revoked['id'])


def _ask(client, tmp_path, ca_cert, *leaves):
    """An OpenSSL-built request (nonce, SHA-1 CertIDs) for *leaves*, answered by /ocsp."""
    files = {'ca.pem': _pem(ca_cert), **{f'leaf{i}.pem': _pem(c) for i, c in enumerate(leaves)}}
    certs = [a for i in range(len(leaves)) for a in ('-cert', f'leaf{i}.pem')]
    out = _openssl(tmp_path, 'ocsp', '-issuer', 'ca.pem', *certs, '-reqout', 'q.der', **files)
    assert out.returncode == 0, out.stderr
    r = client.post('/ocsp', data=(tmp_path / 'q.der').read_bytes(),
                    content_type='application/ocsp-request')
    assert r.status_code == 200
    (tmp_path / 'r.der').write_bytes(r.data)
    return r.data, certs


def _openssl_ocsp_verify(tmp_path, certs, signer, *trust):
    """``openssl ocsp``: the answer carries the request's nonce and its signature verifies under
    *signer* (``-VAfile``, or *trust*); then the status of each certificate, read by OpenSSL."""
    trust = trust or ('-VAfile', 'signer.pem')
    out = _openssl(tmp_path, 'ocsp', '-respin', 'r.der', '-reqin', 'q.der', *trust,
                   **{'signer.pem': _pem(signer)})
    assert out.returncode == 0 and 'Response verify OK' in out.stdout + out.stderr, out.stdout + out.stderr
    # -cert builds a request of its own, with a nonce of its own: no nonce check on this pass
    out = _openssl(tmp_path, 'ocsp', '-respin', 'r.der', '-issuer', 'ca.pem', *certs, *trust, '-no_nonce')
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout


def _basic(der):
    response = asn1_ocsp.OCSPResponse.load(der)
    assert response['response_status'].native == 'successful'
    return response['response_bytes']['response'].parsed


# One CertID takes pyca's builder, two take the hand-built multi-response
@needs_openssl_35
@pytest.mark.parametrize('count', [1, 2])
def test_ml_dsa_ca_answers_and_openssl_verifies(app, client, auth_client, create_cert, mldsa65_ca,
                                               tmp_path, count):
    _enable_ocsp(app, mldsa65_ca['id'])
    ca_cert = _cert_of(app, CA, mldsa65_ca['id'])
    good, revoked = _leaves(app, auth_client, create_cert, mldsa65_ca['id'], f'ca{count}')
    der, certs = _ask(client, tmp_path, ca_cert, *(good, revoked)[:count])
    # RFC 9881: the parameter set's own OID, parameters absent
    assert _basic(der)['signature_algorithm'].dump() == bytes.fromhex('300b0609608648016503040312')
    text = _openssl_ocsp_verify(tmp_path, certs, ca_cert)
    assert 'leaf0.pem: good' in text
    if count == 2:
        assert 'leaf1.pem: revoked' in text


def _delegate(app, auth_client, ca_id, key_type, key_size, cn):
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': cn, 'ca_id': ca_id, 'key_type': key_type, 'key_size': key_size,
        'validity_days': 60, 'cert_type': 'custom', 'extra_ekus': ['OCSPSigning']})
    assert r.status_code == 201, r.get_json()
    cert_id = r.get_json()['data']['id']
    r = _post(auth_client, f'/api/v2/cas/{ca_id}/ocsp-responder', {'certificate_id': cert_id})
    assert r.status_code == 200, r.get_json()
    return cert_id, _cert_of(app, Certificate, cert_id)


def _undelegate(app, ca_id):
    with app.app_context():
        SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca_id}').delete()
        db.session.commit()


@needs_openssl_35
@pytest.mark.parametrize('issuer,responder', [('rsa', ('ml-dsa', 65)), ('mldsa', ('rsa', 2048))])
@pytest.mark.parametrize('count', [1, 2])
def test_delegated_responder_across_rsa_and_ml_dsa(app, client, auth_client, create_cert, mldsa65_ca,
                                                   rsa_ca, tmp_path, issuer, responder, count):
    ca_id = (mldsa65_ca if issuer == 'mldsa' else rsa_ca)['id']
    _enable_ocsp(app, ca_id)
    ca_cert = _cert_of(app, CA, ca_id)
    _, signer = _delegate(app, auth_client, ca_id, *responder, cn=f'pq-responder-{issuer}-{count}.test')
    try:
        good, revoked = _leaves(app, auth_client, create_cert, ca_id, f'{issuer}{count}')
        der, certs = _ask(client, tmp_path, ca_cert, *(good, revoked)[:count])
        assert len(_basic(der)['certs']) == 1
        text = _openssl_ocsp_verify(tmp_path, certs, signer)
        assert 'leaf0.pem: good' in text
        # The responder certificate also chains to the CA under OpenSSL's own rules
        _openssl_ocsp_verify(tmp_path, certs, signer, '-CAfile', 'ca.pem')
    finally:
        _undelegate(app, ca_id)


def test_fips_names_the_ml_dsa_responder_key_as_unapproved(app, auth_client, rsa_ca, monkeypatch):
    """The ML-DSA key loads (refuse_eddsa_key leaves it alone) and is then refused as unapproved."""
    import fips_mode
    from services.ocsp_service import OCSPService
    cert_id, _ = _delegate(app, auth_client, rsa_ca['id'], 'ml-dsa', 65, 'pq-responder-fips.test')
    try:
        with app.app_context():
            ca, row = db.session.get(CA, rsa_ca['id']), db.session.get(Certificate, cert_id)
            monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
            assert OCSPService().check_delegated_responder(ca, row) == 'key is not approved in FIPS mode'
    finally:
        monkeypatch.undo()
        _undelegate(app, rsa_ca['id'])


def test_issuer_key_hash_of_an_ml_dsa_ca_is_over_the_bit_string(app, mldsa65_ca):
    from api.ocsp_routes import _find_ca_by_issuer_hash
    ca_cert = _cert_of(app, CA, mldsa65_ca['id'])
    bits = _bit_string(ca_cert)
    assert len(bits) == 1952  # ML-DSA-65 public key, FIPS 204 table 2
    name_hash = hashlib.sha1(ca_cert.subject.public_bytes()).digest()
    with app.app_context():
        found = _find_ca_by_issuer_hash(name_hash, hashlib.sha1(bits).digest(), hashes.SHA1())
        assert found is not None and found.id == mldsa65_ca['id']


def test_unknown_serial_answer_hashes_the_bit_string(app, mldsa65_ca):
    from services.ocsp_service import OCSPService
    ca_cert = _cert_of(app, CA, mldsa65_ca['id'])
    with app.app_context():
        der, status = OCSPService().generate_response(
            db.session.get(CA, mldsa65_ca['id']), 0x7E57AB1E5EED, hash_algorithm=hashes.SHA256())
    assert status == 'unknown'
    cert_id = _basic(der)['tbs_response_data']['responses'][0]['cert_id']
    assert cert_id['issuer_key_hash'].native == hashlib.sha256(_bit_string(ca_cert)).digest()
