"""RSASSA-PSS signatures verify wherever UCM checks a signature.

Chains signed in PSS (AD CS "alternate signature format", German CAs) were
checked in PKCS#1 v1.5 by the smart import and refused by the SCEP parser.
"""
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import asn1crypto.cms
import asn1crypto.core
import asn1crypto.x509
import pytest
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from services.scep.message_parser import verify_cms_signature
from services.smart_import.chain_builder import ChainBuilder
from utils.cert_issuer import certificate_signed_by


def _pss(salt=padding.PSS.DIGEST_LENGTH):
    return padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=salt)


def _cert(subject_key, cn, issuer_key=None, issuer_cn=None, ca=True):
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn or cn)]))
            .public_key(subject_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
            .sign(issuer_key or subject_key, hashes.SHA256(), rsa_padding=_pss()))


@pytest.fixture(scope='module')
def pss_chain():
    root_key = rsa.generate_private_key(65537, 2048)
    leaf_key = rsa.generate_private_key(65537, 2048)
    root = _cert(root_key, 'PSS Root')
    leaf = _cert(leaf_key, 'PSS Leaf', root_key, 'PSS Root', ca=False)
    return root, leaf, leaf_key


@pytest.mark.skipif(not shutil.which('openssl'), reason='openssl not installed')
def test_fixture_chain_verifies_with_openssl(tmp_path, pss_chain):
    root, leaf, _ = pss_chain
    (tmp_path / 'root.pem').write_bytes(root.public_bytes(serialization.Encoding.PEM))
    (tmp_path / 'leaf.pem').write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    out = subprocess.run(['openssl', 'verify', '-CAfile', str(tmp_path / 'root.pem'), str(tmp_path / 'leaf.pem')],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr


def test_cert_issuer_verifies_pss(pss_chain):
    root, leaf, _ = pss_chain
    assert certificate_signed_by(leaf, root)


def test_smart_import_verifies_pss(pss_chain):
    root, leaf, _ = pss_chain
    assert ChainBuilder()._verify_signature(leaf, root.public_key())


def _signed_data(signer_cert, signer_key, content=b'scep payload', salt=32, tamper=False):
    digest = hashes.Hash(hashes.SHA256())
    digest.update(content)
    attrs = asn1crypto.cms.CMSAttributes([
        {'type': 'content_type', 'values': ['data']},
        {'type': 'message_digest', 'values': [digest.finalize()]},
    ])
    to_sign = attrs.dump()
    to_sign = b'\x31' + to_sign[1:]
    signature = signer_key.sign(to_sign, _pss(salt), hashes.SHA256())
    if tamper:
        signature = bytes([signature[0] ^ 1]) + signature[1:]
    cert = asn1crypto.x509.Certificate.load(signer_cert.public_bytes(serialization.Encoding.DER))
    signer_info = asn1crypto.cms.SignerInfo({
        'version': 'v1',
        'sid': asn1crypto.cms.SignerIdentifier({'issuer_and_serial_number': {
            'issuer': cert.issuer, 'serial_number': cert.serial_number}}),
        'digest_algorithm': {'algorithm': 'sha256'},
        'signed_attrs': attrs,
        'signature_algorithm': {'algorithm': 'rsassa_pss', 'parameters': {
            'hash_algorithm': {'algorithm': 'sha256'},
            'mask_gen_algorithm': {'algorithm': 'mgf1', 'parameters': {'algorithm': 'sha256'}},
            'salt_length': salt, 'trailer_field': 'trailer_field_bc'}},
        'signature': signature,
    })
    return asn1crypto.cms.SignedData({
        'version': 'v1', 'digest_algorithms': [{'algorithm': 'sha256'}],
        'encap_content_info': {'content_type': 'data', 'content': content},
        'certificates': [cert], 'signer_infos': [signer_info],
    })



@pytest.mark.parametrize('salt', [32, 64])
def test_scep_accepts_a_pss_signed_message(pss_chain, salt):
    _, leaf, leaf_key = pss_chain
    verify_cms_signature(_signed_data(leaf, leaf_key, salt=salt), leaf)


def test_scep_still_refuses_a_bad_pss_signature(pss_chain):
    _, leaf, leaf_key = pss_chain
    with pytest.raises(InvalidSignature):
        verify_cms_signature(_signed_data(leaf, leaf_key, tamper=True), leaf)
