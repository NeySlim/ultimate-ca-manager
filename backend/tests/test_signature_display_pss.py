"""PSS signatures and Brainpool keys are named and scored like their peers.

A PSS signature showed as "rsassaPss" with no hash and scored as unknown;
a Brainpool key scored as an unrated curve whatever its size.
"""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509.oid import NameOID

from models.ca import CA
from models.certificate import Certificate
from services.compliance_service import _score_key_strength, _score_signature
from utils.cert_extensions import parse_certificate_info
from utils.signature_label import signature_algorithm_label

NAME = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'PSS display')])


def _cert(key, salt=32, digest=hashes.SHA256()):
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(NAME).issuer_name(NAME).public_key(key.public_key())
               .serial_number(1).not_valid_before(now).not_valid_after(now + timedelta(days=1)))
    if isinstance(key, rsa.RSAPrivateKey):
        return builder.sign(key, digest, rsa_padding=padding.PSS(mgf=padding.MGF1(digest), salt_length=salt))
    return builder.sign(key, digest)


@pytest.fixture(scope='module')
def pss_cert():
    return _cert(rsa.generate_private_key(65537, 2048))


def _b64(cert):
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


def test_label_names_hash_and_salt(pss_cert):
    assert signature_algorithm_label(pss_cert) == 'RSASSA-PSS SHA-256 (salt 32)'
    key = rsa.generate_private_key(65537, 2048)
    assert signature_algorithm_label(_cert(key, salt=48, digest=hashes.SHA384())) == 'RSASSA-PSS SHA-384 (salt 48)'


def test_label_leaves_other_algorithms_alone():
    assert signature_algorithm_label(_cert(ec.generate_private_key(ec.SECP256R1()))) == 'ecdsa-with-SHA256'


def test_models_and_parsers_show_the_label(pss_cert):
    assert Certificate(crt=_b64(pss_cert)).signature_algorithm == 'RSASSA-PSS SHA-256 (salt 32)'
    assert CA(crt=_b64(pss_cert)).hash_algorithm == 'RSASSA-PSS SHA-256 (salt 32)'
    info = parse_certificate_info(pss_cert.public_bytes(serialization.Encoding.PEM))
    assert info['signature_algorithm'] == 'RSASSA-PSS SHA-256 (salt 32)'


def test_decoder_tool_shows_the_label(auth_client, pss_cert):
    r = auth_client.post('/api/v2/tools/decode-cert', content_type='application/json',
                         data=json.dumps({'pem': pss_cert.public_bytes(serialization.Encoding.PEM).decode()}))
    assert r.status_code == 200, r.data
    assert json.loads(r.data)['data']['signature_algorithm'] == 'RSASSA-PSS SHA-256 (salt 32)'


def test_pss_signature_scores_by_its_hash():
    assert _score_signature({'signature_algorithm': 'RSASSA-PSS SHA-256 (salt 32)'})['score'] == 22


@pytest.mark.parametrize('curve, points', [
    ('brainpoolP256r1', 25), ('brainpoolP384r1', 30), ('brainpoolP512r1', 30),
])
def test_brainpool_key_scores_like_its_size(curve, points):
    assert _score_key_strength({'key_algorithm': f'EC {curve}'})['score'] == points
