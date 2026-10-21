"""An HSM key refuses a signature its provider cannot produce.

The providers sign RSA in PKCS#1 v1.5 with SHA-2. Asked for PSS, the wrapper
used to warn and sign v1.5 anyway: the certificate then named RSASSA-PSS over
a v1.5 signature and failed to verify, with no error at issuance.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509.oid import NameOID

from services.hsm.hsm_private_key import HsmECPrivateKey, HsmRSAPrivateKey


def _builder(public_key):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'HSM guard')])
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(public_key)
            .serial_number(1).not_valid_before(now).not_valid_after(now + timedelta(days=1)))


@pytest.fixture
def rsa_key():
    return rsa.generate_private_key(65537, 2048)


def test_pss_request_is_refused_before_reaching_the_hsm(rsa_key):
    wrapper = HsmRSAPrivateKey(1, rsa_key.public_key(), 'RSA-2048')
    pss = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH)
    with patch('services.hsm.HsmService.sign') as hsm_sign:
        with pytest.raises(UnsupportedAlgorithm):
            _builder(rsa_key.public_key()).sign(wrapper, hashes.SHA256(), rsa_padding=pss)
    hsm_sign.assert_not_called()


@pytest.mark.parametrize('digest', [hashes.SHA1(), hashes.SHA224(), hashes.SHA3_256()])
def test_rsa_digest_the_provider_does_not_know_is_refused(rsa_key, digest):
    wrapper = HsmRSAPrivateKey(1, rsa_key.public_key(), 'RSA-2048')
    with patch('services.hsm.HsmService.sign') as hsm_sign:
        with pytest.raises(UnsupportedAlgorithm):
            wrapper.sign(b'tbs', padding.PKCS1v15(), digest)
    hsm_sign.assert_not_called()


@pytest.mark.parametrize('digest', [hashes.SHA1(), hashes.SHA224()])
def test_ec_digest_the_provider_does_not_know_is_refused(digest):
    key = ec.generate_private_key(ec.SECP256R1())
    wrapper = HsmECPrivateKey(1, key.public_key(), 'EC-P256')
    with patch('services.hsm.HsmService.sign') as hsm_sign:
        with pytest.raises(UnsupportedAlgorithm):
            wrapper.sign(b'tbs', ec.ECDSA(digest))
    hsm_sign.assert_not_called()


def test_v15_with_sha384_still_reaches_the_hsm(rsa_key):
    wrapper = HsmRSAPrivateKey(5, rsa_key.public_key(), 'RSA-2048')
    with patch('services.hsm.HsmService.sign', return_value=b'sig') as hsm_sign:
        assert wrapper.sign(b'tbs', padding.PKCS1v15(), hashes.SHA384()) == b'sig'
    hsm_sign.assert_called_once_with(5, b'tbs', 'RSA-2048', hash_algorithm='sha384')
