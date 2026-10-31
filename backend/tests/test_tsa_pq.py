"""Timestamps signed with ML-DSA (RFC 9882 SignerInfo inside an RFC 3161 token), the
signer issued and selected through the TSA API, and EdDSA refused with a reason.

`openssl ts -verify` (3.5) cannot check these tokens: its PKCS#7 code verifies through
a digest-then-sign context ML-DSA does not offer. `openssl cms -verify` checks the CMS
signature, and the test checks the RFC 3161 imprint itself."""
import base64
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import pytest
from asn1crypto import core, tsp
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed448, ed25519, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from models import CA, SystemConfig, db
from utils import key_algorithms

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')

OPENSSL = shutil.which('openssl')
TST_INFO_OID = '1.2.840.113549.1.9.16.1.4'


def _openssl_35():
    if not OPENSSL:
        return False
    out = subprocess.run([OPENSSL, 'version'], capture_output=True, text=True).stdout
    m = re.match(r'OpenSSL (\d+)\.(\d+)', out)
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= (3, 5)


needs_openssl_35 = pytest.mark.skipif(not _openssl_35(), reason='needs OpenSSL 3.5 or later')


def _pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def _tsq(data):
    return tsp.TimeStampReq({
        'version': 1, 'cert_req': True,
        'message_imprint': {'hash_algorithm': {'algorithm': 'sha256'},
                            'hashed_message': hashlib.sha256(data).digest()},
    }).dump()


def _self_signed_signer(key):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'PQ TSA signer')])
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
               .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
               .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True))
    return builder.sign(key, hashes.SHA256() if key_algorithms.needs_digest(key) else None)


def _signer_info(token_der):
    token = tsp.TimeStampResp.load(token_der)['time_stamp_token']
    return token['content'], token['content']['signer_infos'][0]


def _assert_rfc9882(response_der, cert, label):
    """RFC 9882 §3.3 shape: SHA-512 digest, the parameter set's OID without parameters,
    a pure signature over the DER SignedAttrs, and the ESSCertIDv2 still SHA-256."""
    signed_data, signer_info = _signer_info(response_der)
    tst_info_der = signed_data['encap_content_info']['content'].contents
    sha512 = core.ObjectIdentifier('2.16.840.1.101.3.4.2.3').dump()
    assert signer_info['digest_algorithm'].dump() == b'\x30' + bytes([len(sha512)]) + sha512
    assert [a.dump() for a in signed_data['digest_algorithms']] == [b'\x30' + bytes([len(sha512)]) + sha512]
    algorithm = signer_info['signature_algorithm']
    assert algorithm['algorithm'].dotted == key_algorithms.get(label).oid
    oid = core.ObjectIdentifier(key_algorithms.get(label).oid).dump()
    assert algorithm.dump() == b'\x30' + bytes([len(oid)]) + oid   # parameters absent, not NULL
    attrs = {a['type'].native: a['values'][0] for a in signer_info['signed_attrs']}
    assert attrs['message_digest'].native == hashlib.sha512(tst_info_der).digest()
    ess = attrs['signing_certificate_v2']['certs'][0]
    assert ess['hash_algorithm']['algorithm'].native == 'sha256'
    assert ess['cert_hash'].native == hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).digest()
    cert.public_key().verify(signer_info['signature'].native, signer_info['signed_attrs'].untag().dump())


def _cms_verify(tmp_path, response_der, data, ca_pem):
    """`openssl cms -verify` on the token, then the RFC 3161 imprint against *data*."""
    token = tsp.TimeStampResp.load(response_der)['time_stamp_token']
    (tmp_path / 'token.der').write_bytes(token.dump())
    (tmp_path / 'ca.pem').write_bytes(ca_pem)
    out = subprocess.run([OPENSSL, 'cms', '-verify', '-inform', 'DER', '-in', 'token.der',
                          '-CAfile', 'ca.pem', '-purpose', 'any', '-out', 'tst.der'],
                         capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    info = tsp.TSTInfo.load((tmp_path / 'tst.der').read_bytes())
    assert info['message_imprint']['hashed_message'].native == hashlib.sha256(data).digest()


@pytest.mark.parametrize('label', ['ML-DSA-65', 'ML-DSA-87'])
def test_mldsa_token_is_an_rfc_9882_signer_info(label):
    from services.tsa_service import TSAService
    key = key_algorithms.generate(label)
    cert = _self_signed_signer(key)
    der, status = TSAService(cert, key).process_request(_tsq(b'pq timestamp'))
    assert status == 200
    assert tsp.TimeStampResp.load(der)['status']['status'].native == 'granted'
    _assert_rfc9882(der, cert, label)


@needs_openssl_35
def test_openssl_cms_verifies_a_self_signed_mldsa_token(tmp_path):
    from services.tsa_service import TSAService
    key = key_algorithms.generate('ML-DSA-65')
    cert = _self_signed_signer(key)
    data = b'checked by openssl'
    der, _ = TSAService(cert, key).process_request(_tsq(data))
    _cms_verify(tmp_path, der, data, _pem(cert))


@pytest.mark.parametrize('make', [ed25519.Ed25519PrivateKey.generate, ed448.Ed448PrivateKey.generate],
                         ids=['ed25519', 'ed448'])
def test_eddsa_signer_is_refused_with_its_reason(make):
    from services.tsa_service import TSAService, tsa_signer_key_problem
    key = make()
    problem = tsa_signer_key_problem(key.public_key())
    assert problem and 'RSA, ECDSA or ML-DSA' in problem and 'EdDSA' in problem
    with pytest.raises(ValueError, match='RSA, ECDSA or ML-DSA'):
        TSAService(_self_signed_signer(key), key)._build_signed_response(b'\x30\x00', True, 'sha256')


def test_rsa_and_mldsa_signers_have_no_problem():
    from services.tsa_service import tsa_signer_key_problem
    assert tsa_signer_key_problem(rsa.generate_private_key(65537, 2048).public_key()) is None
    assert tsa_signer_key_problem(key_algorithms.generate('ML-DSA-65').public_key()) is None


# ---- issued and selected through the API -----------------------------------------

@pytest.fixture(scope='module')
def rsa_ca(create_ca):
    return create_ca(cn='PQ TSA RSA root')


@pytest.fixture(scope='module')
def mldsa_ca(create_ca):
    return create_ca(cn='PQ TSA ML-DSA-65 root', keyAlgo='ML-DSA', keySize=65)


def _ca_pem(app, ca):
    with app.app_context():
        return base64.b64decode(db.session.get(CA, ca['id']).crt)


def _issue(auth_client, ca, **body):
    return auth_client.post('/api/v2/tsa/signer-certificate', content_type='application/json',
                            data=json.dumps({'ca_id': ca['id'], **body}))


@pytest.fixture
def tsa_settings(app):
    keys = ('tsa_enabled', 'tsa_signer_cert_refid', 'tsa_ca_refid')
    with app.app_context():
        saved = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None) for k in keys}
    yield
    with app.app_context():
        SystemConfig.query.filter(SystemConfig.key.in_(keys)).delete(synchronize_session=False)
        db.session.add_all(SystemConfig(key=k, value=v) for k, v in saved.items() if v is not None)
        db.session.commit()


def _enable(app, **values):
    with app.app_context():
        for key, value in {'tsa_enabled': 'true', **values}.items():
            row = SystemConfig.query.filter_by(key=key).first() or SystemConfig(key=key)
            row.value = value
            db.session.add(row)
        db.session.commit()


@pytest.mark.parametrize('ca_fixture,key_size', [('rsa_ca', '65'), ('mldsa_ca', '87')])
def test_issued_mldsa_signer_is_offered_selected_and_signs(
        request, app, client, auth_client, tsa_settings, tmp_path, ca_fixture, key_size):
    ca = request.getfixturevalue(ca_fixture)
    r = _issue(auth_client, ca, cn=f'pq-tsa-signer-{key_size}', key_type='ml-dsa',
               key_size=key_size, select=True)
    assert r.status_code == 200, r.get_json()
    issued = r.get_json()['data']
    assert issued['selected'] is True and issued['signer']['usable'] is True
    cert = x509.load_pem_x509_certificate(issued['certificate']['pem'].encode())
    assert key_algorithms.label_for_public_key(cert.public_key()) == f'ML-DSA-{key_size}'

    candidates = auth_client.get('/api/v2/tsa/signer-candidates').get_json()['data']
    assert issued['certificate']['refid'] in {c['refid'] for c in candidates}
    r = auth_client.patch('/api/v2/tsa/config', content_type='application/json',
                          data=json.dumps({'signer_cert_refid': issued['certificate']['refid']}))
    assert r.status_code == 200, r.get_json()

    _enable(app)
    data = b'issued pq signer'
    resp = client.post('/tsa', data=_tsq(data), content_type='application/timestamp-query')
    assert resp.status_code == 200
    _assert_rfc9882(resp.data, cert, f'ML-DSA-{key_size}')
    if _openssl_35():
        _cms_verify(tmp_path, resp.data, data, _ca_pem(app, ca))


def test_mldsa_ca_signs_timestamps_itself(app, client, auth_client, mldsa_ca, tsa_settings):
    _enable(app, tsa_signer_cert_refid='')
    r = auth_client.patch('/api/v2/tsa/config', content_type='application/json',
                          data=json.dumps({'ca_refid': mldsa_ca['refid']}))
    assert r.status_code == 200, r.get_json()
    resp = client.post('/tsa', data=_tsq(b'ca signer'), content_type='application/timestamp-query')
    assert resp.status_code == 200
    ca_cert = x509.load_pem_x509_certificate(_ca_pem(app, mldsa_ca))
    _assert_rfc9882(resp.data, ca_cert, 'ML-DSA-65')


@pytest.mark.parametrize('key_type', ['ed25519', 'ed448'])
def test_eddsa_signer_issuance_is_refused(auth_client, rsa_ca, key_type):
    r = _issue(auth_client, rsa_ca, key_type=key_type, key_size='')
    assert r.status_code == 400
