"""The OpenSSL-made post-quantum fixtures hold what their names say, read without openssl."""
import base64
import hashlib

import pytest
from asn1crypto import cms
from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import mldsa
from cryptography.hazmat.primitives.serialization import pkcs12

from tests.pqc_fixtures import P12_PASSWORD, fixture_bytes, load_mldsa_key

MLDSA65_OID = '2.16.840.1.101.3.4.3.18'
SLHDSA_SHA2_128S_OID = '2.16.840.1.101.3.4.3.20'
SHA512_OID = '2.16.840.1.101.3.4.2.3'


def test_the_fixture_key_is_seed_only_ml_dsa_65(mldsa_key):
    assert isinstance(mldsa_key, mldsa.MLDSA65PrivateKey)
    assert len(fixture_bytes('mldsa65-seed.pem')) == 128
    assert load_mldsa_key() is not mldsa_key  # each call loads a fresh object


@pytest.mark.parametrize('name', ['mldsa65-both.pem', 'mldsa65-priv.pem'])
def test_pyca_refuses_the_other_openssl_layouts(name):
    with pytest.raises(ValueError):
        serialization.load_pem_private_key(fixture_bytes(name), None)


def test_the_openssl_csr_is_signed_by_the_fixture_key(mldsa_key, mldsa_csr):
    assert mldsa_csr.is_signature_valid
    assert mldsa_csr.signature_algorithm_oid.dotted_string == MLDSA65_OID
    assert mldsa_csr.signature_hash_algorithm is None
    assert mldsa_csr.public_key() == mldsa_key.public_key()


def test_the_openssl_certificate_is_self_signed_by_the_fixture_key(mldsa_key):
    cert = x509.load_pem_x509_certificate(fixture_bytes('mldsa65-cert.pem'))
    cert.verify_directly_issued_by(cert)
    assert cert.public_key() == mldsa_key.public_key()


def test_the_openssl_pkcs12_holds_a_key_pyca_cannot_read():
    # OpenSSL writes the "both" layout inside the PKCS#12
    with pytest.raises(ValueError):
        pkcs12.load_key_and_certificates(fixture_bytes('mldsa65.p12'), P12_PASSWORD)


def test_the_cms_is_signed_with_ml_dsa_65_over_sha512(mldsa_key):
    signed = cms.ContentInfo.load(fixture_bytes('mldsa65-signed.cms'))['content']
    content = signed['encap_content_info']['content'].native
    assert content == fixture_bytes('cms-content.txt')
    signer = signed['signer_infos'][0]
    assert signer['digest_algorithm']['algorithm'].dotted == SHA512_OID
    assert signer['signature_algorithm']['algorithm'].dotted == MLDSA65_OID
    attrs = signer['signed_attrs']
    digest = next(a['values'][0].native for a in attrs if a['type'].dotted == '1.2.840.113549.1.9.4')
    assert digest == hashlib.sha512(content).digest()
    # The signature covers the attributes encoded as a SET (RFC 5652 §5.4)
    mldsa_key.public_key().verify(signer['signature'].native, b'\x31' + attrs.dump()[1:])


def test_the_slh_dsa_certificate_is_read_but_its_key_is_not():
    cert = x509.load_pem_x509_certificate(fixture_bytes('slhdsa-sha2-128s-cert.pem'))
    assert cert.signature_algorithm_oid.dotted_string == SLHDSA_SHA2_128S_OID
    assert cert.public_key_algorithm_oid.dotted_string == SLHDSA_SHA2_128S_OID
    with pytest.raises(UnsupportedAlgorithm):
        cert.public_key()


def test_the_ca_row_signs_with_the_fixture_key(mldsa_ca, mldsa_key):
    from models import CA
    from services.crl.generation import _crl_signature_hash
    from services.hsm.ca_key_loader import get_ca_signing_key
    from utils.signing_hash import signing_hash_for
    row = CA.query.filter_by(refid=mldsa_ca.refid).one()
    assert row.has_private_key and row.is_root
    key = get_ca_signing_key(row)
    assert isinstance(key, mldsa.MLDSA65PrivateKey)
    cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
    assert key.public_key() == mldsa_key.public_key() == cert.public_key()
    assert signing_hash_for(key, _crl_signature_hash(row)) is None


def test_the_fixture_ca_takes_its_crls_with_it(app):
    from models import CRLMetadata
    from services.crl import CRLService
    from tests.pqc_fixtures import mldsa_ca_row
    with mldsa_ca_row(app) as ca:
        ca_id = ca.id
        CRLService.generate_crl(ca_id)
        assert CRLMetadata.query.filter_by(ca_id=ca_id).count() == 1
    with app.app_context():
        assert CRLMetadata.query.filter_by(ca_id=ca_id).count() == 0
