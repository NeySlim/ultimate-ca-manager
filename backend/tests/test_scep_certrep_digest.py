"""The CertRep signature follows the signer key and the client's digest, never a fixed SHA-256 (#397)."""
import datetime as dt

import asn1crypto.cms
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import NameOID

from services.scep import response_builder
from services.scep.message_parser import verify_cms_signature

KEYS = {
    'rsa': lambda: rsa.generate_private_key(65537, 2048),
    'p384': lambda: ec.generate_private_key(ec.SECP384R1()),
    'p521': lambda: ec.generate_private_key(ec.SECP521R1()),
    'ed25519': lambda: ed25519.Ed25519PrivateKey.generate(),
}


def _ca(key):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'CertRep digest CA')])
    now = dt.datetime.now(dt.timezone.utc)
    algo = None if isinstance(key, ed25519.Ed25519PrivateKey) else hashes.SHA512()
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + dt.timedelta(days=1)).sign(key, algo))
    return cert


def _reply(kind, request_digest=None):
    key = KEYS[kind]()
    cert = _ca(key)
    der = response_builder.build_cert_rep(
        response_builder.STATUS_PENDING, b'', 'txn', b'n' * 16, key, cert,
        request_digest=request_digest)
    signed = asn1crypto.cms.ContentInfo.load(der)['content']
    verify_cms_signature(signed, cert)
    info = signed['signer_infos'][0]
    return info['digest_algorithm']['algorithm'].native, info['signature_algorithm']['algorithm'].native


@pytest.mark.parametrize('kind,request_digest,expected', [
    ('rsa', 'sha256', 'sha256'),
    ('rsa', None, 'sha256'),
    ('rsa', 'sha512', 'sha512'),
    ('rsa', 'sha1', 'sha256'),
    ('p384', 'sha256', 'sha384'),
    ('p384', None, 'sha384'),
    ('p384', 'sha512', 'sha512'),
    ('p521', 'sha256', 'sha512'),
])
def test_certrep_digest_follows_key_and_request(kind, request_digest, expected):
    assert _reply(kind, request_digest)[0] == expected


@pytest.mark.parametrize('request_digest', [None, 'sha256', 'sha384'])
def test_ed25519_certrep_is_rfc8419(request_digest):
    digest, signature = _reply('ed25519', request_digest)
    assert (digest, signature) == ('sha512', 'ed25519')


def test_service_reply_for_a_p384_ca_is_sha384_whatever_the_request(app, create_ca):
    from services.scep.scep_service import SCEPService
    from tests.test_scep_rfc8894_operations import _build_request, _client_identity, _load_ca_material
    ca_data = create_ca(cn='CertRep P-384 CA', keyAlgo='EC-P384', keyType='EC-P384',
                       keySize='secp384r1', hashAlgorithm='sha384')
    with app.app_context():
        ca, ca_cert, _ = _load_ca_material(ca_data['id'])
        client_cert, client_key = _client_identity()
        # The request is a SHA-256 one that cannot be decrypted by an EC CA: an error reply
        request = _build_request(ca_cert, client_cert, client_key, 19, b'csr', b'n' * 16,
                                 recipient_cert=client_cert)
        response, status = SCEPService(ca.refid).process_pkcs_req(request, '127.0.0.1')
    assert status == 200
    info = asn1crypto.cms.ContentInfo.load(response)['content']['signer_infos'][0]
    assert info['digest_algorithm']['algorithm'].native == 'sha384'


def test_certrep_of_an_hsm_key_with_a_fixed_hash_names_the_hash_it_signed(monkeypatch):
    """A provider that signs ES256 only: a SHA-512 request must not name SHA-512 in the SignerInfo."""
    from services.hsm import HsmService
    from services.hsm.hsm_private_key import HsmECPrivateKey
    software = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(HsmService, 'signing_hash', staticmethod(lambda *a, **k: 'sha256'))
    monkeypatch.setattr(HsmService, 'sign', staticmethod(
        lambda key_id, data, algo, hash_algorithm=None: software.sign(data, ec.ECDSA(hashes.SHA256()))))
    key = HsmECPrivateKey(1, software.public_key(), 'EC-P256')
    cert = _ca(software)
    der = response_builder.build_cert_rep(
        response_builder.STATUS_PENDING, b'', 'txn', b'n' * 16, key, cert, request_digest='sha512')
    signed = asn1crypto.cms.ContentInfo.load(der)['content']
    assert signed['signer_infos'][0]['digest_algorithm']['algorithm'].native == 'sha256'
    verify_cms_signature(signed, cert)
