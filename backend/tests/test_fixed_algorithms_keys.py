"""Keys UCM generates for a requester (#397 follow-up): EST serverkeygen and
mTLS follow the issuing CA's family and strength, bounded by the policies."""
import base64
import json

import pytest
from asn1crypto import cms
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, mldsa, rsa

from models import AuthCertificate, Certificate, db
from models.policy import CertificatePolicy
from services.policy_service import PolicyViolation
from tests.test_est_pq import _post, _serverkeygen_leaf, est_ca  # noqa: F401  (fixture)
from tests.test_policy_algorithms_397 import _drop, _pol, _policy
from utils import key_algorithms
from utils.issuance_defaults import generated_key_algorithm


def _pub(key):
    return key.public_key()


@pytest.mark.parametrize('issuer,classical,expected', [
    (lambda: rsa.generate_private_key(65537, 2048), True, 'RSA-2048'),
    (lambda: rsa.generate_private_key(65537, 4096), True, 'RSA-3072'),
    (lambda: ec.generate_private_key(ec.SECP256R1()), True, 'EC-P256'),
    (lambda: ec.generate_private_key(ec.SECP384R1()), True, 'EC-P384'),
    (lambda: ec.generate_private_key(ec.SECP521R1()), True, 'EC-P384'),
    (lambda: ec.generate_private_key(ec.BrainpoolP384R1()), False, 'EC-P384'),
    (ed25519.Ed25519PrivateKey.generate, True, 'EC-P256'),
    (ed448.Ed448PrivateKey.generate, True, 'EC-P384'),
    (mldsa.MLDSA65PrivateKey.generate, False, 'ML-DSA-65'),
    (mldsa.MLDSA65PrivateKey.generate, True, 'EC-P384'),
    (mldsa.MLDSA44PrivateKey.generate, True, 'EC-P256'),
])
def test_the_key_follows_the_issuer(app, issuer, classical, expected):
    with app.app_context():
        alg = generated_key_algorithm(_pub(issuer()), [], classical_only=classical)
    assert alg.label == expected


def test_a_policy_refusing_the_issuer_match_moves_to_the_closest_allowed(app):
    issuer = _pub(rsa.generate_private_key(65537, 2048))
    with app.app_context():
        both = _pol({'allowed_key_types': ['RSA-3072', 'EC-P384']})
        assert generated_key_algorithm(issuer, [both], classical_only=True).label == 'RSA-3072'
        ec_only = _pol({'allowed_key_types': ['EC-P256']})
        assert generated_key_algorithm(issuer, [ec_only], classical_only=True).label == 'EC-P256'


def test_a_template_type_wins_when_allowed(app):
    issuer = _pub(rsa.generate_private_key(65537, 2048))
    with app.app_context():
        assert generated_key_algorithm(issuer, [], template_key_type='EC-P384').label == 'EC-P384'


def test_nothing_generable_is_a_policy_refusal(app):
    issuer = _pub(rsa.generate_private_key(65537, 2048))
    with app.app_context():
        with pytest.raises(PolicyViolation, match='no key type'):
            generated_key_algorithm(issuer, [_pol({'allowed_key_types': ['ED25519']})])
        pq_only = _pol({'allowed_key_types': ['ML-DSA-65']})
        with pytest.raises(PolicyViolation):
            generated_key_algorithm(issuer, [pq_only], classical_only=True)
        assert generated_key_algorithm(issuer, [pq_only]).label == 'ML-DSA-65'


# EST serverkeygen: est_ca serves the CAs of this module's est_cas
@pytest.fixture
def est_cas(create_ca):
    return {'p384': create_ca(cn='Keys EST P-384 root', keyAlgo='EC-P384', keyType='EC-P384',
                              keySize='secp384r1', hashAlgorithm='sha384'),
            'rsa': create_ca(cn='Keys EST RSA root')}


def _keygen_csr(cn):
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .sign(key, hashes.SHA256())).public_bytes(serialization.Encoding.DER)


def test_serverkeygen_under_a_p384_ca_generates_p384(client, est_ca):
    ca_cert = est_ca('p384')
    r = _post(client, 'serverkeygen', _keygen_csr('keygen-p384.keys.test'))
    assert r.status_code == 200, r.data
    leaf = _serverkeygen_leaf(r)
    assert key_algorithms.label_for_public_key(leaf.public_key()) == 'EC-P384'
    assert isinstance(leaf.signature_hash_algorithm, hashes.SHA384)
    leaf.verify_directly_issued_by(ca_cert)


def test_serverkeygen_follows_a_policy_refusing_rsa_2048(app, client, est_ca, est_cas):
    est_ca('rsa')
    pid = _policy(app, 'keys-no-rsa2048', est_cas['rsa']['id'], {'allowed_key_types': ['RSA-3072']})
    try:
        r = _post(client, 'serverkeygen', _keygen_csr('keygen-3072.keys.test'))
        assert r.status_code == 200, r.data
        leaf = _serverkeygen_leaf(r)
        assert key_algorithms.label_for_public_key(leaf.public_key()) == 'RSA-3072'
    finally:
        _drop(app, CertificatePolicy, pid)


def test_cms_key_package_is_signed_by_an_ec_key():
    from utils.est_cms import _signed_private_key
    key = ec.generate_private_key(ec.SECP384R1())
    cert = _cert_for(key)
    pkcs8 = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption())
    signed = cms.SignedData.load(_signed_private_key(key, cert, pkcs8).dump())
    info = signed['signer_infos'][0]
    assert info['signature_algorithm']['algorithm'].native == 'sha384_ecdsa'
    key.public_key().verify(info['signature'].native, pkcs8, ec.ECDSA(hashes.SHA384()))


def _cert_for(key):
    import datetime
    from cryptography.x509.oid import NameOID
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'cms-signer')])
    now = datetime.datetime.now(datetime.timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA384()))


# mTLS: browser keys, never EdDSA nor ML-DSA
def _mtls(app, auth_client, ca_id):
    r = auth_client.post('/api/v2/mtls/certificates', content_type='application/json',
                         data=json.dumps({'ca_id': ca_id, 'name': 'keys mtls', 'validity_days': 30}))
    assert r.status_code == 201, r.data
    data = json.loads(r.data)['data']
    with app.app_context():
        row = db.session.get(Certificate, data['certificate_id'])
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
    return data, cert


def _drop_mtls(app, data):
    _drop(app, AuthCertificate, data['id'])
    _drop(app, Certificate, data['certificate_id'])


def test_mtls_under_a_p384_ca_is_p384_signed_with_sha384(app, auth_client, create_ca):
    ca = create_ca(cn='Keys mTLS P-384 CA', keyAlgo='EC-P384', keyType='EC-P384',
                   keySize='secp384r1', hashAlgorithm='sha384')
    data, cert = _mtls(app, auth_client, ca['id'])
    try:
        assert key_algorithms.label_for_public_key(cert.public_key()) == 'EC-P384'
        assert isinstance(cert.signature_hash_algorithm, hashes.SHA384)
    finally:
        _drop_mtls(app, data)


def test_mtls_under_an_mldsa_ca_gets_a_browser_key(app, auth_client, create_ca):
    ca = create_ca(cn='Keys mTLS ML-DSA CA', keyAlgo='ML-DSA', keySize=65)
    data, cert = _mtls(app, auth_client, ca['id'])
    try:
        assert key_algorithms.label_for_public_key(cert.public_key()) == 'EC-P384'
    finally:
        _drop_mtls(app, data)


def test_mtls_follows_a_policy_refusing_rsa_2048(app, auth_client, create_ca):
    ca = create_ca(cn='Keys mTLS CNSA CA')
    pid = _policy(app, 'keys-mtls-cnsa', ca['id'], {'allowed_key_types': ['EC-P384', 'RSA-4096']})
    try:
        data, cert = _mtls(app, auth_client, ca['id'])
        try:
            assert key_algorithms.label_for_public_key(cert.public_key()) == 'RSA-4096'
        finally:
            _drop_mtls(app, data)
    finally:
        _drop(app, CertificatePolicy, pid)


def test_admin_generated_user_mtls_under_a_p384_ca_is_p384(app, auth_client, create_ca):
    ca = create_ca(cn='Keys user mTLS P-384 CA', keyAlgo='EC-P384', keyType='EC-P384',
                   keySize='secp384r1', hashAlgorithm='sha384')
    r = auth_client.post('/api/v2/users/1/mtls/certificates', content_type='application/json',
                         data=json.dumps({'mode': 'generate', 'ca_id': ca['id'], 'validity_days': 30,
                                          'name': 'keys-user-mtls'}))
    assert r.status_code == 201, r.data
    data = json.loads(r.data)['data']
    try:
        cert = x509.load_pem_x509_certificate(data['certificate'].encode())
        assert key_algorithms.label_for_public_key(cert.public_key()) == 'EC-P384'
    finally:
        _drop(app, AuthCertificate, data['id'])
        _drop(app, Certificate, data['cert_id'])
