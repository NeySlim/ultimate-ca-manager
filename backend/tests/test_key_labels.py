"""Key labels follow the actual algorithm: CA key_type and compliance key strength."""
import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from models.ca import CA
from services.compliance_service import _score_key_strength


def _self_signed_b64(key):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Label CA')])
    now = datetime.now(timezone.utc)
    digest = None if isinstance(key, (ed25519.Ed25519PrivateKey, ed448.Ed448PrivateKey)) \
        else hashes.SHA256()
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now).not_valid_after(now + timedelta(days=1))
            .sign(key, digest))
    return base64.b64encode(cert.public_bytes(Encoding.PEM)).decode()


@pytest.mark.parametrize('make_key, expected', [
    (lambda: ed25519.Ed25519PrivateKey.generate(), 'Ed25519'),
    (lambda: ed448.Ed448PrivateKey.generate(), 'Ed448'),
    (lambda: rsa.generate_private_key(65537, 2048), 'RSA 2048'),
    (lambda: ec.generate_private_key(ec.SECP256R1()), 'EC secp256r1'),
    (lambda: ec.generate_private_key(ec.SECP384R1()), 'EC secp384r1'),
    (lambda: ec.generate_private_key(ec.SECP256K1()), 'EC secp256k1'),
])
def test_ca_key_type_names_the_algorithm(make_key, expected):
    assert CA(crt=_self_signed_b64(make_key())).key_type == expected


def _certificate_dict(key_type, key_size=0):
    """The fields Certificate.to_dict hands the scorer ("EC secp256r1" gives key_size 0)."""
    return {'key_type': key_type, 'key_algo': key_type,
            'key_algorithm': key_type.split()[0], 'key_size': key_size}


@pytest.mark.parametrize('key_type, key_size, score, reason', [
    ('EC secp256r1', 0, 25, 'ECDSA P-256'),
    ('EC secp384r1', 0, 30, 'ECDSA P-384'),
    ('EC secp521r1', 0, 30, 'ECDSA P-521'),
    ('RSA 2048', 2048, 20, 'RSA 2048'),
    ('RSA 4096', 4096, 30, 'RSA 4096'),
    ('Ed25519', 0, 30, 'ED25519'),
    ('Ed448', 0, 30, 'ED448'),
])
def test_registered_keys_keep_their_points(key_type, key_size, score, reason):
    result = _score_key_strength(_certificate_dict(key_type, key_size))
    assert (result['score'], result['reason']) == (score, reason)


@pytest.mark.parametrize('spelling', ['EC P-256', 'ECDSA P-384', 'EC prime256v1'])
def test_other_spellings_of_registered_curves(spelling):
    result = _score_key_strength({'key_type': spelling})
    assert result['reason'] in ('ECDSA P-256', 'ECDSA P-384')


def test_size_only_ec_keys_keep_their_points():
    assert _score_key_strength({'key_algorithm': 'EC', 'key_size': 256})['reason'] == 'ECDSA P-256'
    assert _score_key_strength({'key_algorithm': 'EC', 'key_size': 384})['score'] == 30


@pytest.mark.parametrize('key_type, key_size, score', [
    ('EC secp256k1', 0, 15), ('EC secp256k1', 256, 15),
    # Brainpool scores like the NIST curve of its size, under its own name
    ('EC brainpoolP512r1', 512, 30), ('EC brainpoolP384r1', 384, 30),
])
def test_unregistered_curves_are_not_labelled_as_nist(key_type, key_size, score):
    result = _score_key_strength(_certificate_dict(key_type, key_size))
    curve = key_type.split()[1]
    assert result['reason'] == f'ECDSA {curve}'
    assert 'P-' not in result['reason']
    assert result['score'] == score
