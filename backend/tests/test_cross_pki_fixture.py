"""The cross-signed PKI fixture builds what its name says, as OpenSSL sees it."""
import pytest
from cryptography.hazmat.primitives import hashes

from tests.fixtures.cross_pki import build_cross_pki, openssl_verify


@pytest.fixture(scope='module')
def pki():
    return build_cross_pki()


def test_leaf_validates_under_root_b(pki):
    ok, out = openssl_verify(pki.leaf, [pki.root_b], [pki.int_b])
    assert ok, out


def test_leaf_validates_under_root_a_through_the_cross_certificate(pki):
    ok, out = openssl_verify(pki.leaf, [pki.root_a], [pki.int_b, pki.cross_b])
    assert ok, out


def test_leaf_fails_under_root_a_without_the_cross_certificate(pki):
    ok, _ = openssl_verify(pki.leaf, [pki.root_a], [pki.int_b])
    assert not ok


def test_cross_certificate_shares_subject_and_key_with_root_b(pki):
    assert pki.cross_b.subject == pki.root_b.subject
    assert pki.cross_b.public_key().public_numbers() == pki.root_b.public_key().public_numbers()
    assert pki.cross_b.issuer == pki.root_a.subject
    assert pki.cross_b.fingerprint(hashes.SHA256()) != pki.root_b.fingerprint(hashes.SHA256())
